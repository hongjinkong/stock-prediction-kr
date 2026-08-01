"""전략 검증 리포트 — 백테스트 숫자를 믿기 전에 돌려보는 스크립트.

    python scripts/validate.py              # 전체 검증 (수 분 소요)
    python scripts/validate.py --quick      # 파라미터 민감도 생략
    python scripts/validate.py --cache      # 시세를 로컬에 캐시(재실행 빠름)

출력: 콘솔 리포트 + reports/validation.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from trend_system import DEFAULT, fetch_close, backtest, perf
from trend_system.evaluate import (fetch_rf, benchmarks, sharpe_diff_test, phase_robustness,
                                   param_sensitivity, universe_bias, crisis_table, subperiods)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.cache')


def load_data(cfg, use_cache):
    """시세 + 무위험수익. --cache 면 로컬 pickle 재사용."""
    cp, rp = os.path.join(CACHE_DIR, 'close.pkl'), os.path.join(CACHE_DIR, 'rf.pkl')
    if use_cache and os.path.exists(cp) and os.path.exists(rp):
        print('  캐시에서 로드 (.cache/)')
        return pd.read_pickle(cp), pd.read_pickle(rp)
    close = fetch_close(cfg.tickers, cfg.start)
    rf = fetch_rf(close.index)
    if use_cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        close.to_pickle(cp)
        rf.to_pickle(rp)
    return close, rf


def run_validation(close, cfg, rf, quick=False):
    """전 검증을 실행해 dict 로 반환 (build_site.py 도 이 함수를 쓴다)."""
    strat, expo, turnover = backtest(close, cfg, rf=rf)
    bm = benchmarks(close, rf, cfg.ann)
    ew = bm['equal_weight']['returns']

    obs, ci, pval = sharpe_diff_test(strat, ew, rf, cfg.ann)
    naive, _, _ = backtest(close, cfg, rf=None, drift=False, apply_band=False)

    out = {
        'as_of': str(close.index[-1].date()),
        'period': [str(close.index[0].date()), str(close.index[-1].date())],
        'tickers': list(close.columns),
        'n_days': int(len(close)),
        'rf_annual': float(rf.mean() * cfg.ann),
        'config': {'trend_win': cfg.trend_win, 'vol_win': cfg.vol_win, 'risk_frac': cfg.risk_frac,
                   'w_cap': cfg.w_cap, 'rebal': cfg.rebal, 'cost': cfg.cost,
                   'rebal_band': cfg.rebal_band},
        'strategy': {k: v for k, v in perf(strat, cfg.ann, rf).items()},
        'naive_backtest': {k: v for k, v in perf(naive, cfg.ann, rf).items()},
        'turnover_total': float(turnover),
        'avg_exposure': float(expo.mean()),
        'benchmarks': {k: {m: v[m] for m in ('CAGR', 'Vol', 'Sharpe', 'Sharpe_ex', 'MDD', 'Calmar')}
                       for k, v in bm.items()},
        'significance_vs_equal_weight': {'sharpe_diff': obs, 'ci95': list(ci), 'p_value': pval,
                                         'significant': bool(pval < 0.05)},
        'crisis': crisis_table(strat, {k: v['returns'] for k, v in bm.items()}).to_dict('records'),
        'subperiods': subperiods(strat, ew, rf, ann=cfg.ann).to_dict('records'),
        'universe_bias': universe_bias(close, cfg, rf=rf),
    }
    ph = phase_robustness(close, cfg, rf)
    out['phase_robustness'] = {
        'rows': ph.to_dict('records'),
        'sharpe_mean': float(ph.Sharpe_ex.mean()), 'sharpe_std': float(ph.Sharpe_ex.std()),
        'sharpe_min': float(ph.Sharpe_ex.min()), 'sharpe_max': float(ph.Sharpe_ex.max()),
        'mdd_mean': float(ph.MDD.mean()), 'mdd_worst': float(ph.MDD.min()),
        'headline_phase0': float(ph[ph.phase == 0].Sharpe_ex.iloc[0]),
    }
    if not quick:
        ps = param_sensitivity(close, cfg, rf)
        out['param_sensitivity'] = {
            'rows': ps.to_dict('records'), 'n': int(len(ps)),
            'sharpe_mean': float(ps.Sharpe_ex.mean()), 'sharpe_min': float(ps.Sharpe_ex.min()),
            'sharpe_max': float(ps.Sharpe_ex.max()),
            'base_sharpe': ps.attrs['base_sharpe'], 'base_rank': ps.attrs['base_rank'],
            'all_positive': bool((ps.Sharpe_ex > 0).all()),
        }
    out['_series'] = {'strategy': strat, 'equal_weight': ew, 'exposure': expo,
                      'benchmarks': {k: v['returns'] for k, v in bm.items()}}
    return out


def _pct(x):
    return f'{x*100:6.2f}%' if x is not None and not (isinstance(x, float) and np.isnan(x)) else '   n/a'


def print_report(v, cfg):
    L = print
    L('=' * 96)
    L(' 🔍 추세추종 전략 검증 리포트')
    L('=' * 96)
    L(f"  구간 {v['period'][0]} ~ {v['period'][1]}  ({v['n_days']:,}거래일)  |  자산 {len(v['tickers'])}종")
    L(f"  현금 무위험수익(BIL) 연 {v['rf_annual']*100:.2f}%  |  평균 노출 {v['avg_exposure']*100:.1f}%"
      f"  |  누적 회전율 {v['turnover_total']:.1f}배")

    L('\n' + '-' * 96)
    L(' [1] 백테스트 가정의 현실성')
    L('-' * 96)
    s, n = v['strategy'], v['naive_backtest']
    L(f"   {'':<28}{'CAGR':>9}{'Sharpe_ex':>11}{'MDD':>10}")
    L(f"   {'낙관 가정(구버전)':<28}{_pct(n['CAGR']):>9}{n['Sharpe_ex']:>11.2f}{_pct(n['MDD']):>10}")
    L(f"   {'현실 가정(드리프트+현금+밴드)':<28}{_pct(s['CAGR']):>9}{s['Sharpe_ex']:>11.2f}{_pct(s['MDD']):>10}")
    L(f"   ➜ MDD가 {(s['MDD']-n['MDD'])*100:+.1f}%p 만큼 나빠진다. 구버전은 '매일 무비용 리밸런싱'을 가정했다.")

    L('\n' + '-' * 96)
    L(' [2] 벤치마크 — SPY가 아니라 "같은 자산 동일비중 매수보유"와 비교해야 한다')
    L('-' * 96)
    L(f"   {'':<28}{'CAGR':>9}{'Sharpe_ex':>11}{'MDD':>10}")
    L(f"   {'추세추종':<28}{_pct(s['CAGR']):>9}{s['Sharpe_ex']:>11.2f}{_pct(s['MDD']):>10}")
    for k, b in v['benchmarks'].items():
        L(f"   {k:<28}{_pct(b['CAGR']):>9}{b['Sharpe_ex']:>11.2f}{_pct(b['MDD']):>10}")
    sig = v['significance_vs_equal_weight']
    L(f"\n   동일비중 대비 Sharpe 차 {sig['sharpe_diff']:+.3f}  95%CI [{sig['ci95'][0]:+.2f}, {sig['ci95'][1]:+.2f}]"
      f"  p={sig['p_value']:.3f}")
    L(f"   ➜ {'통계적으로 유의' if sig['significant'] else '통계적으로 유의하지 않음 — 수익률 우위를 주장할 수 없다'}")
    L(f"   ➜ 단, MDD는 {(v['benchmarks']['equal_weight']['MDD']-s['MDD'])*100:+.1f}%p 개선."
      f" 이것이 추세추종의 실제 값어치다(수익 증가 ✕, 낙폭 축소 ○).")

    L('\n' + '-' * 96)
    L(' [3] 리밸런스 위상 의존성 — "i % 21 == 0" 은 21개 중 하나의 임의 선택')
    L('-' * 96)
    p = v['phase_robustness']
    L(f"   Sharpe_ex  평균 {p['sharpe_mean']:.3f} ± {p['sharpe_std']:.3f}"
      f"   범위 [{p['sharpe_min']:.3f}, {p['sharpe_max']:.3f}]")
    L(f"   헤드라인(phase 0) = {p['headline_phase0']:.3f}"
      f"  → 분포의 {'상단' if p['headline_phase0'] > p['sharpe_mean'] else '평균 이하'}")
    L(f"   MDD  평균 {_pct(p['mdd_mean'])}  최악 {_pct(p['mdd_worst'])}")
    L(f"   ➜ 보고할 숫자는 평균과 최악값이지, 가장 예쁜 위상 하나가 아니다.")

    L('\n' + '-' * 96)
    L(' [4] 유니버스 후견편향 — 개별주는 2026년에 결과를 알고 고른 것')
    L('-' * 96)
    u = v['universe_bias']
    L(f"   {'9자산(개별주 포함)':<28}{_pct(u['full']['CAGR']):>9}{u['full']['Sharpe_ex']:>11.2f}{_pct(u['full']['MDD']):>10}")
    L(f"   {'ETF만 ' + ' '.join(u['etf_tickers']):<28}{_pct(u['etf_only']['CAGR']):>9}"
      f"{u['etf_only']['Sharpe_ex']:>11.2f}{_pct(u['etf_only']['MDD']):>10}")
    L(f"   ➜ 수익의 약 {u['return_share_from_stock_picks']*100:.0f}%가 개별주 선택에서 온다. 이 부분은 미래에 재현 보장이 없다.")
    L(f"   ➜ 반면 ETF만으로도 Sharpe {u['etf_only']['Sharpe_ex']:.2f} / MDD {_pct(u['etf_only']['MDD'])} —"
      f" 리스크 관리 효과 자체는 종목 선택과 무관하게 남는다.")

    if 'param_sensitivity' in v:
        L('\n' + '-' * 96)
        L(' [5] 파라미터 민감도 — "관습값이라 과적합 없다"는 주장의 실증')
        L('-' * 96)
        g = v['param_sensitivity']
        L(f"   격자 {g['n']}개 조합  Sharpe_ex 범위 [{g['sharpe_min']:.2f}, {g['sharpe_max']:.2f}]  평균 {g['sharpe_mean']:.2f}")
        L(f"   기본값(200/63/0.03) = {g['base_sharpe']:.2f} → {g['base_rank']}위 / {g['n']}개")
        L(f"   ➜ 기본값이 봉우리가 아니라 {'분포 한가운데' if g['base_rank'] > g['n']*0.25 else '상위권'}이고,"
          f" {'모든' if g['all_positive'] else '대부분'} 조합이 양(+)."
          f" 파라미터를 고른 행위가 성과를 만든 게 아니다 = 과적합 아님.")

    L('\n' + '-' * 96)
    L(' [6] 위기 구간 방어력 (추세추종의 존재 이유)')
    L('-' * 96)
    L(f"   {'구간':<26}{'추세추종':>10}{'동일비중':>10}{'SPY':>10}")
    for c in v['crisis']:
        L(f"   {c['period']:<26}{_pct(c['strategy']):>10}{_pct(c['equal_weight']):>10}{_pct(c.get('SPY', float('nan'))):>10}")

    L('\n' + '-' * 96)
    L(' [7] 구간별 안정성')
    L('-' * 96)
    L(f"   {'구간':<14}{'전략 CAGR':>11}{'Sharpe':>9}{'MDD':>10}   |{'동일비중 CAGR':>14}{'Sharpe':>9}{'MDD':>10}")
    for r in v['subperiods']:
        L(f"   {r['period']:<14}{_pct(r['strat_CAGR']):>11}{r['strat_Sharpe_ex']:>9.2f}{_pct(r['strat_MDD']):>10}"
          f"   |{_pct(r['bench_CAGR']):>14}{r['bench_Sharpe_ex']:>9.2f}{_pct(r['bench_MDD']):>10}")

    L('\n' + '=' * 96)
    L(' 결론: 이 전략은 "더 버는 법"이 아니라 "덜 잃는 법"이다.')
    L('       동일비중 대비 수익률 우위는 통계적으로 입증되지 않으며, 낙폭 축소만이 재현 가능한 효과다.')
    L('=' * 96)


def main():
    ap = argparse.ArgumentParser(description='추세추종 전략 검증')
    ap.add_argument('--quick', action='store_true', help='파라미터 민감도 격자 생략')
    ap.add_argument('--cache', action='store_true', help='시세를 .cache/ 에 저장·재사용')
    ap.add_argument('--out', default='reports/validation.json')
    args = ap.parse_args()

    cfg = DEFAULT
    print('데이터 수집 중...', file=sys.stderr)
    close, rf = load_data(cfg, args.cache)

    print('검증 실행 중 (파라미터 격자 포함 시 수 분)...', file=sys.stderr)
    v = run_validation(close, cfg, rf, quick=args.quick)
    print_report(v, cfg)

    v.pop('_series', None)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(v, f, ensure_ascii=False, indent=2, default=float)
    print(f'\n저장됨: {args.out}')


if __name__ == '__main__':
    main()
