"""변동성 타겟팅 전략 — 예측 변동성으로 SPY 포지션을 사이징 (수익화 단계).

아이디어: 목표 변동성(예: 15%)을 유지하도록 비중 = 목표변동성 / 예측변동성.
예측 변동성이 높으면(폭락 신호) 비중을 줄여 낙폭을 방어. 레버리지 없음(비중 ≤ 1).

비교: Buy&Hold  vs  변동성타겟(과거 21일)  vs  변동성타겟(GBM 예측)
실행: `! python scripts/vol_target_strategy.py`
"""
import sys
import warnings

import numpy as np
import pandas as pd
import yfinance as yf
import lightgbm as lgb
from sklearn.metrics import r2_score

warnings.filterwarnings('ignore')
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

TICKER = 'SPY'
START = '2010-01-01'
ANN = 252
HORIZON = 5          # 예측 호라이즌(영업일)
TRAIN_FRAC = 0.55    # 앞 55%로 예측모델 학습, 뒤 45%로 전략 검증(out-of-sample)
TARGET_VOL = 0.15    # 목표 연율 변동성
MAX_W = 1.0          # 비중 상한(레버리지 금지)
COST = 0.0005        # 편도 거래비용


def fetch_ohlc(t):
    df = yf.download(t, start=START, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[['Open', 'High', 'Low', 'Close']].dropna()


def build(df, vix):
    d = df.copy()
    r = d['Close'].pct_change()
    lnhl = np.log(d['High'] / d['Low'])
    y = np.log(r.rolling(HORIZON).std().shift(-HORIZON) * np.sqrt(ANN))   # log 미래변동성
    X = pd.DataFrame(index=d.index)
    X['rv_5'] = r.rolling(5).std() * np.sqrt(ANN)
    X['rv_21'] = r.rolling(21).std() * np.sqrt(ANN)
    X['rv_63'] = r.rolling(63).std() * np.sqrt(ANN)
    X['ewma'] = np.sqrt((r ** 2).ewm(alpha=1 - 0.94).mean()) * np.sqrt(ANN)
    X['parkinson'] = np.sqrt((1 / (4 * np.log(2))) * (lnhl ** 2).rolling(5).mean()) * np.sqrt(ANN)
    X['abs_ret'] = r.abs().rolling(5).mean()
    X['ret_5'] = d['Close'].pct_change(5)
    X['vol_of_vol'] = X['rv_21'].rolling(21).std()
    v = vix.reindex(d.index).ffill()
    X['vix'] = v / 100.0
    X['vix_chg'] = v.diff(5)
    df2 = pd.concat([X, y.rename('y'), r.rename('ret')], axis=1)
    df2 = df2.replace([np.inf, -np.inf], np.nan)
    return df2


def perf(ret):
    r = ret.dropna()
    eq = (1 + r).cumprod()
    n = len(r)
    cagr = eq.iloc[-1] ** (ANN / n) - 1 if (n and eq.iloc[-1] > 0) else np.nan
    vol = r.std() * np.sqrt(ANN)
    sharpe = r.mean() / r.std() * np.sqrt(ANN) if r.std() > 0 else 0.0
    dd = eq / eq.cummax() - 1
    return {'CAGR': cagr, 'Vol': vol, 'Sharpe': sharpe, 'MDD': dd.min()}


def strat_from_volpred(pred_vol, ret_test):
    # 비중 = 목표변동성 / 예측변동성, 상한 MAX_W. 신호는 t+1 체결.
    w = (TARGET_VOL / pred_vol).clip(upper=MAX_W)
    w_exec = w.shift(1).fillna(0.0)
    turn = w_exec.diff().abs().fillna(w_exec.abs())
    return w_exec * ret_test - turn * COST


def main():
    print('데이터 수집 중...', file=sys.stderr)
    df = fetch_ohlc(TICKER)
    vix = fetch_ohlc('^VIX')['Close']
    d = build(df, vix)
    feats = [c for c in d.columns if c not in ('y', 'ret')]

    ds = d.dropna()
    n = len(ds); cut = int(n * TRAIN_FRAC)
    Xtr, ytr = ds[feats].iloc[:cut], ds['y'].iloc[:cut]
    test = ds.iloc[cut:]
    Xte = test[feats]; ret_test = test['ret']

    gbm = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, max_depth=4, num_leaves=15,
                            min_child_samples=30, subsample=0.8, colsample_bytree=0.8,
                            random_state=42, verbose=-1).fit(Xtr, ytr)
    pred_vol = pd.Series(np.exp(gbm.predict(Xte)), index=Xte.index)   # 예측 변동성(연율)
    actual_fut = np.exp(test['y'])
    r2 = r2_score(np.log(actual_fut), np.log(pred_vol))

    # 3개 전략 (같은 test 구간)
    bh = ret_test.copy()                                   # Buy&Hold
    vt_naive = strat_from_volpred(Xte['rv_21'], ret_test)  # 과거 21일 변동성 사이징
    vt_pred = strat_from_volpred(pred_vol, ret_test)       # 예측 변동성 사이징

    print('=' * 66)
    print(f' 변동성 타겟팅 전략 — {TICKER} (out-of-sample, 목표변동성 {TARGET_VOL:.0%}, 무레버리지)')
    print('=' * 66)
    print(f' 예측모델 R²(log): {r2:.3f} | 테스트 {len(ret_test)}일 '
          f'({test.index[0].date()}~{test.index[-1].date()})')
    print('-' * 66)
    print(f'{"전략":22}{"CAGR":>9}{"Vol":>8}{"Sharpe":>9}{"MDD":>9}')
    for name, s in [('Buy&Hold', bh), ('변동성타겟(과거21일)', vt_naive), ('변동성타겟(GBM예측)', vt_pred)]:
        m = perf(s)
        print(f'{name:22}{m["CAGR"]*100:8.1f}%{m["Vol"]*100:7.1f}%{m["Sharpe"]:9.2f}{m["MDD"]*100:8.1f}%')
    print('=' * 66)
    print(' 관전: 변동성타겟은 Vol이 목표(15%) 근처로 안정 + MDD 완화 + Sharpe 개선이 정상.')
    print('       예측(GBM)이 과거(21일)보다 Sharpe↑/MDD↓ 면 → 예측이 실제로 돈이 됨.')


if __name__ == '__main__':
    main()
