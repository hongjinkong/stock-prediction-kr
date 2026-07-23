# =====================================================================
# 🔬 [견고성 검증] 여러 종목에 A+B 파이프라인 재적용 → Test AUC 일관성 확인
#   * NVDA용 PatchTST 하이퍼파라미터 재사용, 종목마다 threshold는 라벨균형으로 자동선택
#   * 사용법(노트북 새 셀):  exec(open('robustness_check.py', encoding='utf-8').read())
# =====================================================================
import time
from sklearn.calibration import CalibratedClassifierCV


def _calibrate(est, Xc, yc, method='isotonic'):
    try:
        from sklearn.frozen import FrozenEstimator
        c = CalibratedClassifierCV(FrozenEstimator(est), method=method)
    except ImportError:
        c = CalibratedClassifierCV(est, method=method, cv='prefit')
    c.fit(Xc, yc)
    return c


def _pick_threshold(df_m):
    best, gap = THRESHOLD_CANDIDATES[0], 1.0
    for t in THRESHOLD_CANDIDATES:
        f = add_features(df_m, threshold=t)
        n = len(f); ts = n - int(n * TEST_RATIO) - int(n * VAL_RATIO)
        ur = f['Label'].values[:ts].mean()
        if abs(ur - 0.5) < gap:
            gap, best = abs(ur - 0.5), t
    return best


def run_ticker(ticker, peers, epochs=120):
    dfr, _ = fetch_us_data(ticker, START_DATE, END_DATE)
    dfm = dfr.join(df_ext, how='left').ffill().dropna()
    thr = _pick_threshold(dfm)
    (dff, fcols, sc, sel, Xtr, ytr, Xvl, yvl, Xte, yte,
     Xtrf, Xvlf, Xtef) = preprocess(dfm, thr)
    if len(np.unique(yvl)) < 2 or len(np.unique(yte)) < 2:
        return None

    # 피어 풀링 (시퀀스 + flat + 가중치)
    n = len(dff); tsz = n - int(n * TEST_RATIO) - int(n * VAL_RATIO)
    wt = sample_weights_uniqueness(dff['Future_Return'].values[:tsz], PRED_DAYS)[SEQ_LEN:]
    pXf, pY, pW = [Xtrf], [ytr], [wt]
    sX, sY, sW = [Xtr], [ytr], [wt]
    for p in peers:
        try:
            pr, _ = fetch_us_data(p, START_DATE, END_DATE)
            pm = pr.join(df_ext, how='left').ffill().dropna()
            pf = add_features(pm, threshold=thr)
            Xp = pd.DataFrame(np.where(np.isinf(pf[fcols].values), np.nan, pf[fcols].values),
                              columns=fcols).ffill().values
            yp, frp = pf['Label'].values, pf['Future_Return'].values
            npr = len(Xp); tspp = npr - int(npr * TEST_RATIO) - int(npr * VAL_RATIO)
            Xps = sel.transform(sc.transform(Xp[:tspp])); ypt = yp[:tspp]
            wp = sample_weights_uniqueness(frp[:tspp], PRED_DAYS)
            pXf.append(Xps); pY.append(ypt); pW.append(wp)
            Xpq, ypq = make_seq(Xps, ypt, SEQ_LEN)
            if len(Xpq) > 0:
                sX.append(Xpq); sY.append(ypq); sW.append(wp[SEQ_LEN:])
        except Exception:
            pass
    Xtrfp, ytrp, wtrp = np.vstack(pXf), np.concatenate(pY), np.concatenate(pW)
    Xtrsp, ytrsp, wtrsp = np.vstack(sX), np.concatenate(sY), np.concatenate(sW)

    # PatchTST (NVDA에서 찾은 구조 재사용)
    cwp = compute_class_weight('balanced', classes=np.array([0, 1]), y=ytrsp)
    m = PatchTST(n_features=Xtrsp.shape[2], seq_len=SEQ_LEN, patch_len=PATCH_LEN,
                 d_model=D_MODEL, n_heads=N_HEADS, n_layers=N_LAYERS, dropout=0.3).to(device)
    train_pytorch_engine(m, Xtrsp, ytrsp, Xvl, yvl, epochs, FINAL_BATCH_SIZE,
                         FINAL_LEARNING_RATE, {0: cwp[0], 1: cwp[1]}, patience=20, sample_weight=wtrsp)

    # 트리 (고정 하이퍼파라미터)
    lg = lgb.LGBMClassifier(n_estimators=600, learning_rate=0.03, max_depth=6, num_leaves=40,
                            subsample=0.8, colsample_bytree=0.8, class_weight='balanced',
                            random_state=SEED, verbose=-1)
    lg.fit(Xtrfp, ytrp, sample_weight=wtrp, eval_set=[(Xvlf, yvl)],
           callbacks=[lgb.early_stopping(30, verbose=False)])
    rf = RandomForestClassifier(n_estimators=500, max_depth=10, min_samples_split=10,
                                min_samples_leaf=5, class_weight='balanced', random_state=SEED, n_jobs=-1)
    rf.fit(Xtrfp, ytrp, sample_weight=wtrp)
    lg, rf = _calibrate(lg, Xvlf, yvl), _calibrate(rf, Xvlf, yvl)

    m.eval()
    with torch.no_grad():
        lpv = m(torch.tensor(Xvl, dtype=torch.float32).to(device)).cpu().numpy().flatten()
        lpt = m(torch.tensor(Xte, dtype=torch.float32).to(device)).cpu().numpy().flatten()
    gpv, rpv = lg.predict_proba(Xvlf)[:, 1], rf.predict_proba(Xvlf)[:, 1]
    gpt, rpt = lg.predict_proba(Xtef)[:, 1], rf.predict_proba(Xtef)[:, 1]

    def negauc(rw):
        w = np.abs(rw); w = w / (w.sum() + 1e-9)
        return -roc_auc_score(yvl, w[0] * lpv + w[1] * gpv + w[2] * rpv)

    r = minimize(negauc, np.array([1 / 3, 1 / 3, 1 / 3]), method='Nelder-Mead',
                 options={'xatol': 1e-4, 'fatol': 1e-4, 'maxiter': 500})
    w = np.abs(r.x); w = w / w.sum()
    return {'ticker': ticker, 'thr': thr,
            'test_auc': roc_auc_score(yte, w[0] * lpt + w[1] * gpt + w[2] * rpt),
            'val_auc': roc_auc_score(yvl, w[0] * lpv + w[1] * gpv + w[2] * rpv),
            'w': w, 'n': len(yte)}


ROBUST = {
    'AAPL': ['MSFT', 'GOOGL', 'META', 'AMZN'],
    'MSFT': ['AAPL', 'GOOGL', 'AMZN', 'META'],
    'JPM':  ['BAC', 'GS', 'WFC', 'MS'],
    'TSLA': ['NVDA', 'AMD', 'GOOGL', 'AMZN'],
}
# 방금 돌린 NVDA 결과 포함
results = [{'ticker': 'NVDA', 'thr': BEST_THRESHOLD, 'test_auc': real_test_auc, 'val_auc': val_auc,
            'w': np.array([W_LSTM, W_LGBM, W_RF]), 'n': len(y_te)}]
for tk, pr in ROBUST.items():
    t0 = time.time()
    print(f'\n▶ {tk} 학습 중...')
    try:
        res = run_ticker(tk, pr)
        if res:
            results.append(res)
            print(f'   ✅ {tk}: Test AUC={res["test_auc"]:.4f} ({time.time() - t0:.0f}s)')
        else:
            print(f'   ⚠️ {tk}: 스킵(라벨 단일)')
    except Exception as e:
        print(f'   ❌ {tk} 실패: {e}')

print('\n' + '=' * 60)
print(f'{"종목":<6}{"thr":>7}{"Val AUC":>10}{"Test AUC":>10}{"W(L/G/R)":>22}')
print('-' * 60)
for r in results:
    print(f'{r["ticker"]:<6}{r["thr"]:>7.3f}{r["val_auc"]:>10.4f}{r["test_auc"]:>10.4f}'
          f'{"  %.2f/%.2f/%.2f" % (r["w"][0], r["w"][1], r["w"][2]):>22}')
aucs = [r['test_auc'] for r in results]
print('-' * 60)
print(f'📊 Test AUC 평균={np.mean(aucs):.4f} | 최소={np.min(aucs):.4f} | '
      f'>0.55 개수={sum(a > 0.55 for a in aucs)}/{len(aucs)}')
print('=' * 60)
