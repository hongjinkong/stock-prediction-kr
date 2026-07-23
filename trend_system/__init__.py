"""trend_system — 규칙 기반 추세추종 포트폴리오 패키지.

기본 사용:
    from trend_system import DEFAULT, fetch_close, generate_report, format_report
    close = fetch_close(DEFAULT.tickers, DEFAULT.start)
    rep = generate_report(close, DEFAULT, holdings)
    print(format_report(rep))
"""
from .config import Config, DEFAULT
from .data import fetch_close, latest_prices
from .signals import trend_signal, volatility, regime_ok
from .portfolio import target_weights, backtest, perf
from .report import generate_report, format_report, save_report, value_holdings, compute_orders

__all__ = [
    'Config', 'DEFAULT', 'fetch_close', 'latest_prices',
    'trend_signal', 'volatility', 'regime_ok',
    'target_weights', 'backtest', 'perf',
    'generate_report', 'format_report', 'save_report', 'value_holdings', 'compute_orders',
]
