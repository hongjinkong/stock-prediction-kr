"""포트폴리오 구성(역변동성 + 총노출 상한 + 레짐) 및 백테스트.
노트북 US_trend_portfolio.ipynb 과 동일 로직을 함수로 정리한 것."""
import numpy as np
import pandas as pd

from .signals import trend_signal, volatility, regime_ok


def portfolio_vol_scale(weights, close, cfg):
    """✅ 포트폴리오 전체 변동성 타겟팅 스케일 계수.
    최근 공분산으로 포트폴리오 추정 변동성을 구해, 목표(target_portfolio_vol)를 넘으면
    전체 비중을 줄인다(폭락 시 디레버리징 → MDD 축소). None이면 1.0(끔)."""
    if not cfg.target_portfolio_vol:
        return 1.0
    held = {t: wv for t, wv in weights.items() if wv and wv > 0}
    if not held:
        return 1.0
    cols = list(held.keys())
    rets = close[cols].pct_change().tail(cfg.vol_win).dropna()
    if len(rets) < 5:
        return 1.0
    cov = rets.cov().values * cfg.ann
    wv = np.array([held[t] for t in cols])
    var = float(wv @ cov @ wv)
    if var <= 0:
        return 1.0
    port_vol = np.sqrt(var)
    # ✅ 디레버리징 전용: 고변동이면 줄이되(scale<1), 평온해도 키우지 않음(≤max_leverage).
    #    추세 포트폴리오는 이미 보수적이라, 레버리지 업은 오히려 MDD를 키움.
    return float(min(cfg.target_portfolio_vol / port_vol, cfg.max_leverage))


def target_weights(close, cfg):
    """오늘(마지막 행) 기준 목표 비중(dict) 계산.
    신호·변동성은 오늘 종가까지 정보로 계산 → 다음 거래일에 집행(룩어헤드 없음)."""
    sig = trend_signal(close, cfg.trend_win).iloc[-1]
    vol = volatility(close, cfg.vol_win, cfg.ann).iloc[-1]

    w = {t: 0.0 for t in close.columns}
    if cfg.use_regime and not regime_ok(close, cfg.regime_ticker, cfg.trend_win):
        return w  # 위험장 → 전체 현금

    for t in close.columns:
        v = vol[t]
        if sig[t] == 1 and pd.notna(v) and v > 0:
            w[t] = min(cfg.risk_frac / v, cfg.w_cap)   # 역변동성 사이징

    s = sum(w.values())
    if s > cfg.target_lev:                              # 총노출 상한(레버리지 금지)
        w = {t: v * cfg.target_lev / s for t, v in w.items()}

    # ✅ 포트폴리오 전체 변동성 타겟팅 (폭락 시 디레버리징)
    scale = portfolio_vol_scale(w, close, cfg)
    if scale != 1.0:
        w = {t: v * scale for t, v in w.items()}
    return w


def backtest(close, cfg, rf=None, drift=True, phase=0, apply_band=True):
    """월간(rebal) 리밸런스 백테스트. 반환: (일별수익 Series, 노출 Series, 총회전율).

    실전 운용과 일치시키기 위해 다음을 반영한다 (2026-08 감사에서 추가):
      - drift      : 리밸런스 사이에 비중이 가격을 따라 움직인다. 끄면(=False) '매일 무비용으로
                     목표비중 복원'이라는 비현실적 가정이 되어 MDD가 낙관적으로 나온다(-17.9%→-15.7%).
      - rf         : 미투자 현금의 무위험수익(예: BIL 일간수익 Series). None이면 현금 0% 가정.
      - phase      : 리밸런스 위상. i % rebal == phase 인 날 리밸런싱.
                     phase=0 은 임의의 한 선택일 뿐이며, 21개 위상 전부를 돌려야 정직하다(evaluate.py).
      - apply_band : cfg.rebal_band 미만의 드리프트는 주문 생략(report.compute_orders와 동일 규칙).
                     실전은 밴드를 쓰는데 백테스트만 안 쓰면 비용이 과대추정된다.
    """
    rets = close.pct_change().fillna(0.0)
    sig = trend_signal(close, cfg.trend_win).shift(1).fillna(0.0)   # t+1 체결
    vol = volatility(close, cfg.vol_win, cfg.ann).shift(1)
    sma = close.rolling(cfg.trend_win).mean()
    regime = (close[cfg.regime_ticker] > sma[cfg.regime_ticker]).shift(1, fill_value=False)
    if rf is None:
        rf = pd.Series(0.0, index=close.index)
    else:
        rf = rf.reindex(close.index).fillna(0.0)

    tickers = list(close.columns)
    w = pd.Series(0.0, index=tickers)
    cash = 1.0                       # 미투자 현금 비중(NAV 대비)
    port = pd.Series(0.0, index=close.index)
    expo = pd.Series(0.0, index=close.index)
    turnover = 0.0

    for i, dt in enumerate(close.index):
        # 1) 그날의 수익은 '그날 장중 들고 있던' 비중이 번다.
        #    신호는 dt-1 종가 기준(shift(1))이고 체결은 dt 종가이므로, dt 수익은 직전 비중 몫이다.
        expo.iloc[i] = float(w.sum())
        r = float((w * rets.loc[dt]).sum()) + cash * float(rf.loc[dt])

        # 2) 종가 기준으로 비중이 가격을 따라 이동(드리프트)
        if drift:
            gross = 1.0 + r
            if gross > 0:
                w = w * (1.0 + rets.loc[dt]) / gross
                cash = cash * (1.0 + float(rf.loc[dt])) / gross

        # 3) 리밸런스일이면 종가에 체결
        cost = 0.0
        if i >= phase and (i - phase) % cfg.rebal == 0:
            neww = pd.Series(0.0, index=tickers)
            if (not cfg.use_regime) or bool(regime.loc[dt]):
                for t in tickers:
                    v = vol.loc[dt, t]
                    if sig.loc[dt, t] == 1 and pd.notna(v) and v > 0:
                        neww[t] = min(cfg.risk_frac / v, cfg.w_cap)
                s = neww.sum()
                if s > cfg.target_lev:
                    neww = neww * (cfg.target_lev / s)
                # ✅ 포트폴리오 변동성 타겟팅 (dt 시점까지 정보만 사용)
                scale = portfolio_vol_scale(neww.to_dict(), close.loc[:dt], cfg)
                neww = neww * scale
            if apply_band and cfg.rebal_band:
                # 드리프트가 밴드 미만이면 기존 비중 유지(청산은 항상 실행)
                hold = ((neww - w).abs() < cfg.rebal_band) & ~((neww == 0.0) & (w > 0))
                neww = neww.where(~hold, w)
            turn = float((neww - w).abs().sum())
            turnover += turn
            cost = turn * cfg.cost
            w = neww
            cash = 1.0 - float(w.sum())
        port.iloc[i] = r - cost
    return port, expo, turnover


def perf(returns, ann=252, rf=None):
    """수익률 Series → 핵심 지표 dict.

    rf(무위험 일간수익 Series)를 주면 Sharpe_ex(초과수익 기준 샤프)를 함께 낸다.
    Sharpe(원시)는 무위험수익을 빼지 않아 금리가 높던 구간을 과대평가하므로,
    전략 비교에는 Sharpe_ex 를 쓸 것.
    """
    r = returns.dropna()
    eq = (1 + r).cumprod()
    n = len(r)
    out = {'CAGR': np.nan, 'Vol': 0.0, 'Sharpe': 0.0, 'Sharpe_ex': np.nan,
           'MDD': 0.0, 'Calmar': np.nan, 'Final': np.nan}
    if n == 0:
        return out
    out['Final'] = float(eq.iloc[-1])
    if eq.iloc[-1] > 0:
        out['CAGR'] = float(eq.iloc[-1] ** (ann / n) - 1)
    out['Vol'] = float(r.std() * np.sqrt(ann))
    out['Sharpe'] = float(r.mean() / r.std() * np.sqrt(ann)) if r.std() > 0 else 0.0
    if rf is not None:
        ex = (r - rf.reindex(r.index).fillna(0.0)).dropna()
        if len(ex) and ex.std() > 0:
            out['Sharpe_ex'] = float(ex.mean() / ex.std() * np.sqrt(ann))
    dd = eq / eq.cummax() - 1
    out['MDD'] = float(dd.min())
    out['Calmar'] = float(out['CAGR'] / abs(out['MDD'])) if out['MDD'] < 0 else np.nan
    return out
