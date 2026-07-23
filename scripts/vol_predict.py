"""변동성 예측 R² 비교 (스크립트판 — 채팅에서 `! python scripts/vol_predict.py` 로 실행).

노트북 US_vol_predict.ipynb 와 동일 로직을 콘솔에 출력한다.
5일/21일/21일+log × HAR/GBM 의 out-of-sample R²(레벨·로그스케일)를 자산별로 비교.
"""
import sys
import warnings

import numpy as np
import pandas as pd
import yfinance as yf
import lightgbm as lgb
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

warnings.filterwarnings('ignore')
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

ASSETS = ['SPY', 'QQQ', 'NVDA', 'AAPL', 'TSLA']
START = '2010-01-01'
ANN = 252
TEST_FRAC = 0.30


def fetch_ohlc(t):
    df = yf.download(t, start=START, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[['Open', 'High', 'Low', 'Close']].dropna()


def build_h(df, horizon, use_log, vix):
    d = df.copy()
    r = d['Close'].pct_change()
    lnhl = np.log(d['High'] / d['Low'])
    rv_fut = r.rolling(horizon).std().shift(-horizon) * np.sqrt(ANN)
    y = np.log(rv_fut) if use_log else rv_fut
    X = pd.DataFrame(index=d.index)
    X['rv_5'] = r.rolling(5).std() * np.sqrt(ANN)
    X['rv_21'] = r.rolling(21).std() * np.sqrt(ANN)
    X['rv_63'] = r.rolling(63).std() * np.sqrt(ANN)
    X['ewma'] = np.sqrt((r ** 2).ewm(alpha=1 - 0.94).mean()) * np.sqrt(ANN)
    X['parkinson'] = np.sqrt((1 / (4 * np.log(2))) * (lnhl ** 2).rolling(5).mean()) * np.sqrt(ANN)
    X['abs_ret'] = r.abs().rolling(5).mean()
    X['ret_5'] = d['Close'].pct_change(5)
    X['vol_of_vol'] = X['rv_21'].rolling(21).std()
    if vix is not None:
        v = vix.reindex(d.index).ffill()
        X['vix'] = v / 100.0
        X['vix_chg'] = v.diff(5)
    return pd.concat([X, y.rename('y'), rv_fut.rename('lvl')], axis=1).replace([np.inf, -np.inf], np.nan).dropna()


def eval_cfg(df, horizon, use_log, vix):
    ds = build_h(df, horizon, use_log, vix)
    feats = [c for c in ds.columns if c not in ('y', 'lvl')]
    n = len(ds); cut = int(n * (1 - TEST_FRAC))
    Xtr, ytr = ds[feats].iloc[:cut], ds['y'].iloc[:cut]
    Xte = ds[feats].iloc[cut:]
    lvl = ds['lvl'].iloc[cut:].values; logl = np.log(lvl)
    tol = (lambda p: np.exp(p)) if use_log else (lambda p: p)
    har = LinearRegression().fit(Xtr[['rv_5', 'rv_21', 'rv_63']], ytr)
    gbm = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, max_depth=4, num_leaves=15,
                            min_child_samples=30, subsample=0.8, colsample_bytree=0.8,
                            random_state=42, verbose=-1).fit(Xtr, ytr)
    hp = np.clip(tol(har.predict(Xte[['rv_5', 'rv_21', 'rv_63']])), 1e-9, None)
    gp = np.clip(tol(gbm.predict(Xte)), 1e-9, None)
    return {'HAR_lvl': r2_score(lvl, hp), 'GBM_lvl': r2_score(lvl, gp),
            'HAR_log': r2_score(logl, np.log(hp)), 'GBM_log': r2_score(logl, np.log(gp))}


def main():
    print('데이터 수집 중...', file=sys.stderr)
    data = {t: fetch_ohlc(t) for t in ASSETS}
    vix = fetch_ohlc('^VIX')['Close']

    print('=' * 60)
    print(' SPY: 설정별 out-of-sample R² (레벨 / 로그스케일)')
    print('=' * 60)
    print(f'{"설정":14}{"HAR_lvl":>9}{"GBM_lvl":>9}{"HAR_log":>9}{"GBM_log":>9}')
    best = None
    for lab, h, lg in [('5일(원본)', 5, False), ('21일', 21, False), ('21일+log', 21, True)]:
        r = eval_cfg(data['SPY'], h, lg, vix)
        print(f'{lab:14}{r["HAR_lvl"]:9.3f}{r["GBM_lvl"]:9.3f}{r["HAR_log"]:9.3f}{r["GBM_log"]:9.3f}')
        m = max(r.values())
        if best is None or m > best[1]:
            best = (lab, m)
    print(f'\n→ SPY 최고 R²: {best[0]} ({best[1]:.3f})')

    print('\n' + '=' * 60)
    print(' 자산별 R² (21일+log 설정, 일반성 확인)')
    print('=' * 60)
    print(f'{"자산":8}{"HAR_lvl":>9}{"GBM_lvl":>9}{"HAR_log":>9}{"GBM_log":>9}')
    for t in ASSETS:
        try:
            r = eval_cfg(data[t], 21, True, vix)
            print(f'{t:8}{r["HAR_lvl"]:9.3f}{r["GBM_lvl"]:9.3f}{r["HAR_log"]:9.3f}{r["GBM_log"]:9.3f}')
        except Exception as e:
            print(f'{t:8} 실패: {e}')
    print('=' * 60)


if __name__ == '__main__':
    main()
