"""변동성 타겟팅 ON vs OFF — 실데이터로 추세 포트폴리오 백테스트 비교.

per-asset 역변동성 위에 '포트폴리오 디레버리징 오버레이'가 실제로 도움되는지(특히 2020·2022)
실데이터로 확인. 실행: `! python scripts/voltarget_compare.py`
"""
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

from trend_system import DEFAULT, fetch_close
from trend_system.portfolio import backtest, perf


def main():
    print('데이터 수집 중...', file=sys.stderr)
    close = fetch_close(DEFAULT.tickers, DEFAULT.start)

    cfg_on = DEFAULT                                   # target_portfolio_vol=0.12 (기본 ON)
    cfg_off = replace(DEFAULT, target_portfolio_vol=None)

    print('=' * 68)
    print(' 변동성 타겟팅 오버레이 — 추세 포트폴리오 (실데이터, 비용반영)')
    print(f' 목표 변동성 {cfg_on.target_portfolio_vol:.0%} | 구간 {close.index[0].date()}~{close.index[-1].date()}')
    print('=' * 68)
    print(f'{"설정":16}{"CAGR":>9}{"Vol":>8}{"Sharpe":>9}{"MDD":>9}{"평균노출":>9}')
    for label, cfg in [('타겟팅 OFF', cfg_off), ('타겟팅 ON', cfg_on)]:
        pr, ex, _ = backtest(close, cfg)
        m = perf(pr)
        print(f'{label:16}{m["CAGR"]*100:8.1f}%{m["Vol"]*100:7.1f}%{m["Sharpe"]:9.2f}'
              f'{m["MDD"]*100:8.1f}%{ex.mean()*100:8.0f}%')
    print('=' * 68)
    print(' 관전: ON의 MDD가 OFF보다 얕으면(특히 폭락 구간) 안전망이 작동한 것.')
    print('       거의 같으면 → 이미 역변동성으로 통제돼 오버레이는 극단 위기용 안전망.')


if __name__ == '__main__':
    main()
