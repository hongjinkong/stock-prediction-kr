"""추세 신호 · 변동성 · 레짐 — 모두 '해당 시점까지의 정보'만 사용."""
import numpy as np


def trend_signal(close, win):
    """종가 > win일 이동평균 이면 1(상승추세), 아니면 0. (DataFrame in/out)"""
    sma = close.rolling(win).mean()
    return (close > sma).astype(float)


def volatility(close, win, ann):
    """연율화 실현변동성(rolling std of returns). (DataFrame in/out)"""
    r = close.pct_change()
    return r.rolling(win).std() * np.sqrt(ann)


def regime_ok(close, ticker, win):
    """레짐 필터: 기준 티커(SPY)가 win일 이동평균 위에 있으면 True(위험 감내)."""
    sma = close[ticker].rolling(win).mean()
    return bool(close[ticker].iloc[-1] > sma.iloc[-1])
