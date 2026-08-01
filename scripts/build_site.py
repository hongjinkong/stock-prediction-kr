"""웹 대시보드 데이터 생성 — site/data/bundle.js 를 만든다.

    python scripts/build_site.py --cache        # 시세 캐시 사용(빠름)
    python scripts/build_site.py --holdings holdings.json

JSON이 아니라 `window.QUANT_DATA = {...}` 형태의 .js 로 내보낸다.
파일을 그냥 더블클릭해도(file://) 동작하게 하기 위해서다 — fetch()는 CORS로 막힌다.
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from trend_system import DEFAULT, backtest, perf, target_weights
from trend_system.signals import trend_signal, volatility
from trend_system.evaluate import benchmarks

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate import load_data, run_validation

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DATA = os.path.join(ROOT, 'site', 'data')

# 대시보드에 사람이 읽을 이름을 붙인다 (티커만 보면 뭔지 모른다)
NAMES = {
    'SPY': 'S&P 500 지수', 'QQQ': '나스닥100 지수', 'AAPL': '애플', 'MSFT': '마이크로소프트',
    'NVDA': '엔비디아', 'JPM': 'JP모건', 'XOM': '엑슨모빌', 'GLD': '금', 'TLT': '미국 장기국채',
}
KIND = {'SPY': '지수', 'QQQ': '지수', 'GLD': '안전자산', 'TLT': '안전자산'}


def r3(x, n=4):
    """NaN/inf 를 None 으로 바꿔 JSON 안전하게."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else round(f, n)


def curve(returns):
    """일별수익 → 누적 성장배수(1 시작)."""
    return (1 + returns.fillna(0)).cumprod()


def drawdown(eq):
    return eq / eq.cummax() - 1


def downsample(idx, series_map, step=5):
    """주 1회로 솎되 마지막 거래일은 반드시 포함 (파일 크기 ↓, 모양 유지)."""
    keep = list(range(0, len(idx), step))
    if keep[-1] != len(idx) - 1:
        keep.append(len(idx) - 1)
    return ([idx[i].strftime('%Y-%m-%d') for i in keep],
            {k: [r3(v.iloc[i]) for i in keep] for k, v in series_map.items()})


def annual_returns(series_map):
    """연도별 수익률 (마지막 해는 연초 대비 누적 = 부분연도)."""
    years = sorted({d.year for d in next(iter(series_map.values())).index})
    rows = []
    for y in years:
        row = {'year': int(y)}
        for k, v in series_map.items():
            seg = v[v.index.year == y]
            row[k] = r3((1 + seg).prod() - 1)
        rows.append(row)
    return rows


def build_dashboard(close, cfg, holdings):
    """오늘 기준 운용 화면 데이터 — 목표 비중 + 자산별 추세 상태."""
    prices = close.iloc[-1]
    sma = close.rolling(cfg.trend_win).mean().iloc[-1]
    vol = volatility(close, cfg.vol_win, cfg.ann).iloc[-1]
    sig = trend_signal(close, cfg.trend_win).iloc[-1]
    tw = target_weights(close, cfg)

    # 추세 신호가 마지막으로 바뀐 날 = 현 상태를 며칠째 유지 중인지
    hist = trend_signal(close, cfg.trend_win)
    assets = []
    for t in close.columns:
        h = hist[t].dropna()
        cur = h.iloc[-1]
        chg = h[h != cur]
        since = h.index[-1] - (chg.index[-1] if len(chg) else h.index[0])
        assets.append({
            'ticker': t, 'name': NAMES.get(t, t), 'kind': KIND.get(t, '개별주'),
            'price': r3(prices[t], 2), 'sma': r3(sma[t], 2),
            'dist': r3(prices[t] / sma[t] - 1),          # 200일선 대비 이격도
            'in_trend': bool(sig[t] == 1),
            'vol': r3(vol[t]), 'target_w': r3(tw.get(t, 0.0)),
            'days_in_state': int(since.days),
        })
    assets.sort(key=lambda a: (-a['target_w'], -a['dist']))

    invested = sum(tw.values())
    return {
        'as_of': str(close.index[-1].date()),
        'assets': assets,
        'cash_weight': r3(1 - invested),
        'invested_weight': r3(invested),
        'n_in_trend': int(sum(1 for a in assets if a['in_trend'])),
        'holdings': holdings,
    }


def main():
    ap = argparse.ArgumentParser(description='웹 대시보드 데이터 생성')
    ap.add_argument('--cache', action='store_true', help='시세를 .cache/ 에 저장·재사용')
    ap.add_argument('--quick', action='store_true', help='파라미터 민감도 생략')
    ap.add_argument('--holdings', default=None, help='보유 JSON (없으면 현금 100%% 가정)')
    ap.add_argument('--out', default=os.path.join(SITE_DATA, 'bundle.js'))
    args = ap.parse_args()

    cfg = DEFAULT
    print('데이터 수집 중...', file=sys.stderr)
    close, rf = load_data(cfg, args.cache)

    print('검증 실행 중...', file=sys.stderr)
    v = run_validation(close, cfg, rf, quick=args.quick)
    s = v.pop('_series')
    strat, ew, expo = s['strategy'], s['equal_weight'], s['exposure']
    bench = s['benchmarks']

    eq = {'strategy': curve(strat), 'equal_weight': curve(ew),
          'SPY': curve(bench['SPY']), '60/40': curve(bench['60/40'])}
    dd = {f'dd_{k}': drawdown(vv) for k, vv in eq.items() if k in ('strategy', 'equal_weight')}
    dates, series = downsample(close.index, {**eq, **dd, 'exposure': expo})

    holdings = {'cash': 10000.0, 'positions': {}}
    if args.holdings:
        with open(args.holdings, encoding='utf-8') as f:
            holdings = json.load(f)

    bundle = {
        'meta': {
            'as_of': v['as_of'], 'period': v['period'], 'tickers': v['tickers'],
            'n_days': v['n_days'], 'config': v['config'],
            'rf_annual': r3(v['rf_annual']),
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'avg_exposure': r3(v['avg_exposure']), 'turnover_total': r3(v['turnover_total'], 1),
        },
        'headline': {
            'strategy': {k: r3(x) for k, x in v['strategy'].items()},
            'benchmarks': {k: {m: r3(x) for m, x in b.items()} for k, b in v['benchmarks'].items()},
            'naive': {k: r3(x) for k, x in v['naive_backtest'].items()},
        },
        'curves': {'dates': dates, **series},
        'annual': annual_returns({'strategy': strat, 'equal_weight': ew, 'SPY': bench['SPY']}),
        'crisis': [{k: (r3(x) if isinstance(x, float) else x) for k, x in c.items()} for c in v['crisis']],
        'subperiods': [{k: (r3(x) if isinstance(x, float) else x) for k, x in r.items()}
                       for r in v['subperiods']],
        'phase': v['phase_robustness'],
        'params': v.get('param_sensitivity'),
        'universe': v['universe_bias'],
        'significance': v['significance_vs_equal_weight'],
        'dashboard': build_dashboard(close, cfg, holdings),
    }

    os.makedirs(SITE_DATA, exist_ok=True)
    payload = json.dumps(bundle, ensure_ascii=False, separators=(',', ':'), default=r3)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('// 자동 생성 — scripts/build_site.py 로 갱신. 직접 수정하지 말 것.\n')
        f.write(f'window.QUANT_DATA = {payload};\n')
    print(f'생성됨: {args.out}  ({os.path.getsize(args.out)/1024:.0f} KB)')
    print(f'  기준일 {bundle["meta"]["as_of"]} | 추세 자산 {bundle["dashboard"]["n_in_trend"]}/{len(close.columns)}종'
          f' | 현금 {bundle["dashboard"]["cash_weight"]*100:.1f}%')


if __name__ == '__main__':
    main()
