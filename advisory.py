"""월간 자문 리포트 실행 스크립트 (실전화 0~1단계: advisory / semi-auto).

사용법:
    # 최초(전액 현금 가정, NAV 지정)
    python advisory.py --nav 10000

    # 현재 보유가 있으면 holdings.json 지정 (예시: holdings.example.json 참고)
    python advisory.py --holdings holdings.json

    # 레짐 필터(위험장 현금화) 켜기
    python advisory.py --holdings holdings.json --regime

출력: 콘솔 리포트 + reports/advisory_YYYY-MM-DD.json / orders_YYYY-MM-DD.csv
* 자동으로 주문을 넣지 않는다. 사람이 리포트를 보고 브로커에서 직접 집행(0~1단계).
"""
import argparse
import json
import sys
from dataclasses import replace

from trend_system import DEFAULT, fetch_close, generate_report, format_report, save_report

# 윈도우 한국어 콘솔(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


def load_holdings(path, nav):
    if path:
        with open(path, encoding='utf-8') as f:
            h = json.load(f)
        h.setdefault('cash', 0.0)
        h.setdefault('positions', {})
        return h
    # holdings 미지정 → 전액 현금 (최초 배분)
    return {'cash': float(nav), 'positions': {}}


def main():
    ap = argparse.ArgumentParser(description='추세추종 포트폴리오 월간 자문 리포트')
    ap.add_argument('--holdings', default=None, help='현재 보유 JSON 경로')
    ap.add_argument('--nav', type=float, default=10000.0, help='holdings 미지정 시 가정할 전액 현금 NAV')
    ap.add_argument('--regime', action='store_true', help='레짐 필터(SPY 200일선) 켜기')
    ap.add_argument('--no-save', action='store_true', help='파일 저장 생략')
    ap.add_argument('--notify', action='store_true', help='리포트를 텔레그램으로 전송(.env 설정 필요)')
    args = ap.parse_args()

    cfg = replace(DEFAULT, use_regime=args.regime)

    print('데이터 수집 중...', file=sys.stderr)
    close = fetch_close(cfg.tickers, cfg.start)

    holdings = load_holdings(args.holdings, args.nav)
    rep = generate_report(close, cfg, holdings)

    text = format_report(rep)
    print(text)

    if args.notify:
        from trend_system.notify import send_telegram
        ok = send_telegram(text)
        print('텔레그램 전송:', '성공' if ok else '건너뜀/실패(.env 확인)', file=sys.stderr)

    if not args.no_save:
        jpath, cpath = save_report(rep)
        print(f'\n저장됨: {jpath} | {cpath}')


if __name__ == '__main__':
    main()
