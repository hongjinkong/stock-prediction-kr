"""Alpaca 페이퍼 계좌 반자동 리밸런싱 (실전화 2단계).

동작:
  1) Alpaca 페이퍼 계좌의 현재 현금·보유를 읽어온다
  2) 그 NAV/보유 기준으로 목표 비중 + 주문 목록(자문 리포트)을 만든다
  3) 기본은 '드라이런' — 주문을 실제로 넣지 않고 미리보기만 한다
  4) --execute 를 붙이면 페이퍼 계좌에 실제 시장가 주문을 제출한다

사전 준비:
  - pip install alpaca-py
  - https://alpaca.markets 가입 → Paper Trading → API Keys 발급
  - .env.example 를 복사해 .env 로 만들고 키 입력 (.env 는 git에 안 올라감)

사용법:
  python paper_trade.py                 # 드라이런(미리보기)
  python paper_trade.py --regime        # 레짐 필터 켜고 미리보기
  python paper_trade.py --execute       # 실제 페이퍼 주문 제출
"""
import argparse
import sys
from dataclasses import replace

from trend_system import DEFAULT, fetch_close, generate_report, format_report, save_report

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser(description='Alpaca 페이퍼 리밸런싱')
    ap.add_argument('--regime', action='store_true', help='레짐 필터(SPY 200일선) 켜기')
    ap.add_argument('--execute', action='store_true', help='실제 페이퍼 주문 제출(미지정 시 드라이런)')
    args = ap.parse_args()

    # 브로커는 여기서 import (alpaca-py 없으면 친절한 에러)
    from trend_system.broker import get_client, account_holdings, submit_rebalance

    cfg = replace(DEFAULT, use_regime=args.regime)

    print('Alpaca 페이퍼 계좌 연결 중...', file=sys.stderr)
    client = get_client(paper=True)
    holdings, nav, acct = account_holdings(client)
    print(f'  계좌 자산(NAV): ${nav:,.2f} | 현금: ${float(acct.cash):,.2f} | '
          f'보유 종목 {len(holdings["positions"])}개', file=sys.stderr)

    print('시세 데이터 수집 중...', file=sys.stderr)
    close = fetch_close(cfg.tickers, cfg.start)
    rep = generate_report(close, cfg, holdings)
    print(format_report(rep))
    save_report(rep)

    if not rep['orders']:
        print('\n리밸런스 밴드 이내 — 제출할 주문이 없습니다.')
        return

    if not args.execute:
        print('\n[드라이런] 실제 주문은 제출하지 않았습니다. 제출하려면 --execute 를 붙이세요.')
        return

    print('\n⚠️  페이퍼 계좌에 실제 주문을 제출합니다...')
    results = submit_rebalance(client, rep['orders'], dry_run=False)
    for sym, detail, oid in results:
        print(f'   ✅ {sym:<6} {detail:<18} → {oid}')
    print('\n제출 완료. Alpaca 대시보드에서 체결을 확인하세요. (장 마감 시 다음 개장에 체결)')


if __name__ == '__main__':
    main()
