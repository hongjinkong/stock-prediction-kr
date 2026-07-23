"""Alpaca 페이퍼 브로커 연동 (실전화 2단계: 반자동/자동).

- API 키는 환경변수 또는 .env 에서만 읽는다 (코드/깃에 절대 하드코딩 금지).
- 기본은 페이퍼(paper=True). 실계좌 연결은 이 프로젝트 범위 밖.
- 이 모듈은 alpaca-py 가 설치돼 있어야 동작하며, 패키지 __init__ 에서 import 하지 않아
  alpaca-py 없이도 나머지 기능(백테스트·자문 리포트)은 정상 동작한다.
"""
import os


def _load_env():
    """.env 파일이 있으면 읽어 환경변수로 올리고, Alpaca 키를 반환."""
    if os.path.exists('.env'):
        with open('.env', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
    key = os.environ.get('ALPACA_API_KEY_ID') or os.environ.get('APCA_API_KEY_ID')
    sec = os.environ.get('ALPACA_API_SECRET_KEY') or os.environ.get('APCA_API_SECRET_KEY')
    if not key or not sec:
        raise RuntimeError(
            'Alpaca 키가 없습니다. .env(또는 환경변수)에 '
            'ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY 를 설정하세요. (.env.example 참고)'
        )
    return key, sec


def get_client(paper=True):
    """Alpaca TradingClient 반환 (기본 페이퍼)."""
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as e:
        raise ImportError("alpaca-py 미설치. 'pip install alpaca-py' 후 다시 시도하세요.") from e
    key, sec = _load_env()
    return TradingClient(key, sec, paper=paper)


def open_orders(client):
    """미체결(open) 주문 목록. 중복 제출 방지용."""
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        return list(client.get_orders(filter=req))
    except Exception:
        try:
            return list(client.get_orders())
        except Exception:
            return []


def account_holdings(client):
    """현재 계좌 상태를 자문 리포트가 쓰는 holdings 형식으로 변환.
    반환: (holdings dict, nav, account 원본)."""
    acct = client.get_account()
    positions = client.get_all_positions()
    pos = {p.symbol: float(p.qty) for p in positions}
    holdings = {'cash': float(acct.cash), 'positions': pos}
    nav = float(acct.portfolio_value)
    return holdings, nav, acct


def submit_rebalance(client, orders, dry_run=True):
    """주문 목록(리포트의 rep['orders'])을 페이퍼 계좌에 시장가로 제출.
    - BUY: 금액(notional) 기준 (소수점 매수)
    - SELL: 수량(qty) 기준 (보유 초과 방지)
    dry_run=True 면 실제 제출 없이 계획만 반환(이 경우 alpaca-py 불필요)."""
    if not dry_run:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

    results = []
    for o in orders:
        sym = o['ticker']
        if o['side'] == 'BUY':
            detail = f"BUY ${abs(o['delta_usd']):,.2f}"
        else:
            detail = f"SELL {abs(o['delta_shares']):.4f}주"

        if dry_run:
            results.append((sym, detail, 'DRY-RUN'))
            continue

        side = OrderSide.BUY if o['side'] == 'BUY' else OrderSide.SELL
        if o['side'] == 'BUY':
            req = MarketOrderRequest(symbol=sym, notional=round(abs(o['delta_usd']), 2),
                                     side=side, time_in_force=TimeInForce.DAY)
        else:
            req = MarketOrderRequest(symbol=sym, qty=round(abs(o['delta_shares']), 6),
                                     side=side, time_in_force=TimeInForce.DAY)
        res = client.submit_order(req)
        results.append((sym, detail, str(getattr(res, 'id', 'submitted'))))
    return results
