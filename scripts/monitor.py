"""페이퍼 계좌 성과 모니터링 (실전화: 몇 달 지켜보기 단계).

실행할 때마다 계좌 NAV를 reports/equity_log.csv 에 기록하고,
최초 기록 대비 '전략 vs SPY' 누적수익을 비교한다. 매주/매달 돌리면 트랙레코드가 쌓인다.

사용법:
  python monitor.py            # 기록 + 요약 출력
  python monitor.py --notify   # 요약을 텔레그램으로도 전송
"""
import argparse
import datetime
import os
import sys

import pandas as pd
import yfinance as yf

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 루트를 import 경로에 추가

from trend_system.broker import get_client, account_holdings

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

LOG = os.path.join('reports', 'equity_log.csv')


def spy_close():
    df = yf.download('SPY', period='5d', auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return float(df['Close'].dropna().iloc[-1])


def main():
    ap = argparse.ArgumentParser(description='페이퍼 계좌 성과 모니터링')
    ap.add_argument('--notify', action='store_true', help='요약을 텔레그램으로 전송')
    args = ap.parse_args()

    print('Alpaca 페이퍼 계좌 조회 중...', file=sys.stderr)
    client = get_client(paper=True)
    holdings, nav, acct = account_holdings(client)
    spy = spy_close()
    today = datetime.date.today().isoformat()

    os.makedirs('reports', exist_ok=True)
    row = {'date': today, 'nav': round(nav, 2), 'cash': round(float(acct.cash), 2),
           'n_positions': len(holdings['positions']), 'spy': round(spy, 4)}
    if os.path.exists(LOG):
        log = pd.read_csv(LOG)
        log = log[log['date'] != today]           # 같은 날 재실행 시 갱신
        log = pd.concat([log, pd.DataFrame([row])], ignore_index=True)
    else:
        log = pd.DataFrame([row])                 # 첫 기록 (빈 프레임 concat 회피)
    log = log.sort_values('date').reset_index(drop=True)
    log.to_csv(LOG, index=False, encoding='utf-8-sig')

    nav0, spy0 = log['nav'].iloc[0], log['spy'].iloc[0]
    strat = nav / nav0 - 1
    bench = spy / spy0 - 1

    lines = [
        '=' * 56,
        ' 📈 페이퍼 계좌 모니터링',
        '=' * 56,
        f' 기록: {log["date"].iloc[0]} ~ {today} ({len(log)}회)',
        f' NAV ${nav:,.2f} | 현금 ${float(acct.cash):,.2f} | 보유 {len(holdings["positions"])}종목',
        '-' * 56,
        f' 전략 누적수익 : {strat*100:+.2f}%',
        f' SPY  누적수익 : {bench*100:+.2f}%',
        f' 초과(알파)    : {(strat-bench)*100:+.2f}%p',
        '=' * 56,
    ]
    text = '\n'.join(lines)
    print(text)
    print(f' 로그 파일: {LOG} ({len(log)}행 누적)')

    if args.notify:
        from trend_system.notify import send_telegram
        ok = send_telegram(text)
        print('텔레그램 전송:', '성공' if ok else '건너뜀/실패', file=sys.stderr)


if __name__ == '__main__':
    main()
