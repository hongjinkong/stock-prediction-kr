"""검증(evaluate) — 백테스트 한 줄 숫자를 믿지 않기 위한 도구 모음.

이 모듈의 목적은 전략을 좋아 보이게 하는 게 아니라, **좋아 보이는 이유가 진짜인지**를 깨는 것이다.
2026-08 감사에서 드러난 네 가지 함정을 각각 측정한다.

  1. 벤치마크 오류 — SPY와 비교하면 뭐든 좋아 보인다. 올바른 상대는 '같은 유니버스 동일비중 매수보유'.
  2. 위상(phase) 의존성 — `i % 21 == 0` 은 21개 중 하나의 임의 선택. 전부 돌려서 분포를 봐야 한다.
  3. 유니버스 후견편향 — 개별주는 결과를 알고 고른 것. ETF만으로도 성립하는지 확인.
  4. 파라미터 과적합 — "관습값이라 안전하다"는 주장은 민감도 격자로 증명해야 말이 된다.
"""
import numpy as np
import pandas as pd
from dataclasses import replace

from .portfolio import backtest, perf


# --------------------------------------------------------------------------- 현금(무위험)
def fetch_rf(index, ticker='BIL', start='2009-01-01'):
    """미투자 현금의 무위험수익. BIL(1-3개월 국채 ETF) 총수익을 프록시로 쓴다.
    네트워크 실패 시 0% 로 폴백(그 경우 Sharpe_ex 는 Sharpe 와 같아진다)."""
    try:
        import yfinance as yf
        d = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        return d['Close'].dropna().pct_change().reindex(index).fillna(0.0)
    except Exception as e:
        print(f'  [evaluate] 무위험수익 수집 실패({e}) → 현금 0% 가정')
        return pd.Series(0.0, index=index)


# --------------------------------------------------------------------------- 벤치마크
def benchmarks(close, rf=None, ann=252):
    """비교 대상들. 핵심은 equal_weight — 같은 자산을 그냥 균등하게 들고 있었을 때."""
    r = close.pct_change().fillna(0.0)
    out = {'equal_weight': r.mean(axis=1)}
    if 'SPY' in close.columns:
        out['SPY'] = r['SPY']
        if 'TLT' in close.columns:
            out['60/40'] = 0.6 * r['SPY'] + 0.4 * r['TLT']
    return {k: perf(v, ann, rf) | {'returns': v} for k, v in out.items()}


def sharpe_diff_test(r1, r2, rf, ann=252, n_boot=2000, block=21, seed=0):
    """두 전략의 Sharpe 차이가 우연인지 검정 — 21일 블록 부트스트랩.

    일간 수익은 자기상관·변동성 군집이 있어 단순 부트스트랩이 p값을 과소평가한다.
    월 단위 블록으로 리샘플해 시계열 구조를 보존한다.
    반환: (관측 Sharpe 차, 95% 신뢰구간, p값)
    """
    e1 = (r1 - rf.reindex(r1.index).fillna(0.0)).dropna()
    e2 = (r2 - rf.reindex(r2.index).fillna(0.0)).dropna()
    idx = e1.index.intersection(e2.index)
    a1, a2 = e1.loc[idx].values, e2.loc[idx].values
    n = len(idx)
    if n < block * 4:
        return np.nan, (np.nan, np.nan), np.nan

    def sh(a):
        return a.mean() / a.std() * np.sqrt(ann) if a.std() > 0 else 0.0

    rng = np.random.default_rng(seed)
    nb = n // block
    diffs = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n - block, nb)
        ii = np.concatenate([np.arange(s, s + block) for s in starts])
        diffs[b] = sh(a1[ii]) - sh(a2[ii])
    obs = sh(a1) - sh(a2)
    p = 2 * min((diffs <= 0).mean(), (diffs >= 0).mean())
    return float(obs), (float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))), float(min(p, 1.0))


# --------------------------------------------------------------------------- 견고성
def phase_robustness(close, cfg, rf=None):
    """리밸런스 위상 21개를 전부 실행. 헤드라인 숫자가 분포의 어디쯤인지 본다.
    반환: DataFrame(phase, CAGR, Sharpe_ex, MDD)."""
    rows = []
    for ph in range(cfg.rebal):
        r, _, _ = backtest(close, cfg, rf=rf, phase=ph)
        p = perf(r, cfg.ann, rf)
        rows.append({'phase': ph, 'CAGR': p['CAGR'], 'Sharpe_ex': p['Sharpe_ex'], 'MDD': p['MDD']})
    return pd.DataFrame(rows)


def param_sensitivity(close, cfg, rf=None, grid=None):
    """파라미터 격자 전수 실행. 기본값이 '봉우리'에 서 있으면 과적합 신호다.
    기본값이 분포 한가운데면, 값을 고른 행위 자체가 성과를 만들지 않았다는 증거."""
    grid = grid or {'trend_win': [100, 150, 200, 250], 'vol_win': [42, 63, 126],
                    'risk_frac': [0.02, 0.03, 0.04]}
    rows = []
    for tw in grid['trend_win']:
        for vw in grid['vol_win']:
            for rk in grid['risk_frac']:
                c = replace(cfg, trend_win=tw, vol_win=vw, risk_frac=rk)
                r, _, _ = backtest(close, c, rf=rf)
                p = perf(r, cfg.ann, rf)
                rows.append({'trend_win': tw, 'vol_win': vw, 'risk_frac': rk,
                             'CAGR': p['CAGR'], 'Sharpe_ex': p['Sharpe_ex'], 'MDD': p['MDD']})
    df = pd.DataFrame(rows)
    base = df[(df.trend_win == cfg.trend_win) & (df.vol_win == cfg.vol_win)
              & (df.risk_frac == cfg.risk_frac)]
    df.attrs['base_sharpe'] = float(base.Sharpe_ex.iloc[0]) if len(base) else np.nan
    df.attrs['base_rank'] = int((df.Sharpe_ex > df.attrs['base_sharpe']).sum() + 1) if len(base) else -1
    return df


def universe_bias(close, cfg, etf_only=('SPY', 'QQQ', 'GLD', 'TLT'), rf=None):
    """개별주(2026년에 돌아보고 고른 승자)를 뺐을 때 얼마나 남는가.
    성과의 상당 부분이 종목 선택에서 왔다면, 그 부분은 미래에 재현되지 않는다."""
    cols = [t for t in etf_only if t in close.columns]
    full, _, _ = backtest(close, cfg, rf=rf)
    sub, _, _ = backtest(close[cols], cfg, rf=rf)
    pf, ps = perf(full, cfg.ann, rf), perf(sub, cfg.ann, rf)
    share = 1 - ps['CAGR'] / pf['CAGR'] if pf['CAGR'] else np.nan
    return {'full': pf, 'etf_only': ps, 'etf_tickers': cols,
            'return_share_from_stock_picks': float(share)}


# --------------------------------------------------------------------------- 위기 방어
CRISES = {
    '2011 미국 신용등급 강등': ('2011-07-01', '2011-10-31'),
    '2015-16 차이나 쇼크': ('2015-08-01', '2016-02-29'),
    '2018 Q4 급락': ('2018-10-01', '2018-12-31'),
    '2020 코로나 폭락': ('2020-02-19', '2020-03-23'),
    '2022 금리인상 약세장': ('2022-01-01', '2022-10-12'),
}


def crisis_table(strategy_ret, bench_rets, crises=None):
    """위기 구간별 누적수익. 추세추종의 존재 이유(낙폭 방어)가 실제로 작동했는지."""
    crises = crises or CRISES
    rows = []
    for name, (a, b) in crises.items():
        row = {'period': name, 'start': a, 'end': b,
               'strategy': float((1 + strategy_ret.loc[a:b]).prod() - 1)}
        for k, v in bench_rets.items():
            row[k] = float((1 + v.loc[a:b]).prod() - 1)
        rows.append(row)
    return pd.DataFrame(rows)


def subperiods(strategy_ret, bench_ret, rf, bounds=(('2010', '2014'), ('2015', '2019'),
                                                    ('2020', '2022'), ('2023', '2026')), ann=252):
    """구간을 잘라 성과가 특정 시기에만 몰려 있지 않은지 확인."""
    rows = []
    for lo, hi in bounds:
        s, b = strategy_ret.loc[lo:hi], bench_ret.loc[lo:hi]
        rr = rf.loc[lo:hi]
        ps, pb = perf(s, ann, rr), perf(b, ann, rr)
        rows.append({'period': f'{lo}~{hi}',
                     'strat_CAGR': ps['CAGR'], 'strat_Sharpe_ex': ps['Sharpe_ex'], 'strat_MDD': ps['MDD'],
                     'bench_CAGR': pb['CAGR'], 'bench_Sharpe_ex': pb['Sharpe_ex'], 'bench_MDD': pb['MDD']})
    return pd.DataFrame(rows)
