"""자문 리포트 — 목표 비중과, 현재 보유 대비 '주문 목록(리밸런싱)'을 생성.
자동매매가 아니라 사람이 보고 직접 집행하는 0~1단계(advisory/semi-auto)용."""
import json
import os
from datetime import datetime

import pandas as pd

from .portfolio import target_weights


def value_holdings(holdings, prices):
    """현재 보유를 평가. holdings = {'cash': float, 'positions': {ticker: shares}}.
    반환: (nav, 현재 비중 dict, 현재 평가액 dict)."""
    cash = float(holdings.get('cash', 0.0))
    positions = holdings.get('positions', {}) or {}
    cur_val = {}
    for t, sh in positions.items():
        if t in prices.index:
            cur_val[t] = float(sh) * float(prices[t])
        else:
            print(f'  [report] 경고: {t} 가격 없음(유니버스 밖) → 평가 제외')
    nav = cash + sum(cur_val.values())
    cur_w = {t: (v / nav if nav > 0 else 0.0) for t, v in cur_val.items()}
    return nav, cur_w, cur_val


def compute_orders(target_w, holdings, prices, nav, band):
    """목표 비중 vs 현재 보유 → 주문 목록. 드리프트가 band 미만이면 생략(단, 청산은 항상 실행)."""
    positions = holdings.get('positions', {}) or {}
    tickers = sorted(set(list(target_w.keys()) + list(positions.keys())))
    orders = []
    for t in tickers:
        if t not in prices.index:
            continue
        px = float(prices[t])
        tw = float(target_w.get(t, 0.0))
        cur_sh = float(positions.get(t, 0.0))
        cur_val = cur_sh * px
        cur_w = cur_val / nav if nav > 0 else 0.0
        tgt_val = tw * nav
        delta_val = tgt_val - cur_val
        delta_sh = delta_val / px if px > 0 else 0.0

        drift = abs(tw - cur_w)
        exit_pos = (tw == 0.0 and cur_sh > 0)      # 추세 꺼지면 청산은 항상
        if drift < band and not exit_pos:
            continue
        if abs(delta_sh) < 1e-9:
            continue
        orders.append({
            'ticker': t,
            'side': 'BUY' if delta_val > 0 else 'SELL',
            'price': round(px, 2),
            'target_weight': round(tw, 4),
            'current_weight': round(cur_w, 4),
            'delta_usd': round(delta_val, 2),
            'delta_shares': round(delta_sh, 4),
        })
    return orders


def generate_report(close, cfg, holdings):
    """전체 자문 리포트(dict) 생성."""
    prices = close.iloc[-1]
    asof = close.index[-1]
    tw = target_weights(close, cfg)
    nav, cur_w, _ = value_holdings(holdings, prices)
    orders = compute_orders(tw, holdings, prices, nav, cfg.rebal_band)

    invested = sum(tw.values())
    return {
        'as_of': str(asof.date()),
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'nav': round(nav, 2),
        'target_cash_weight': round(1 - invested, 4),
        'use_regime': cfg.use_regime,
        'target_weights': {t: round(w, 4) for t, w in tw.items() if w > 0},
        'current_weights': {t: round(w, 4) for t, w in cur_w.items() if w > 0},
        'orders': orders,
    }


def format_report(rep):
    """사람이 읽는 텍스트 리포트."""
    lines = []
    lines.append('=' * 64)
    lines.append(" 🧺 추세추종 포트폴리오 — 월간 자문 리포트")
    lines.append('=' * 64)
    lines.append(f" 기준일: {rep['as_of']} | 생성: {rep['generated_at']}")
    lines.append(f" 계좌 NAV: ${rep['nav']:,.2f} | 레짐필터: {'ON' if rep['use_regime'] else 'OFF'}")
    lines.append('-' * 64)
    lines.append(' 🎯 목표 비중')
    if rep['target_weights']:
        for t, w in sorted(rep['target_weights'].items(), key=lambda x: -x[1]):
            lines.append(f"    {t:<6} {w*100:5.1f}%")
    else:
        lines.append('    (상승추세 자산 없음 → 전액 현금)')
    lines.append(f"    {'현금':<6} {rep['target_cash_weight']*100:5.1f}%")
    lines.append('-' * 64)
    lines.append(' 📋 주문 목록 (다음 거래일에 집행 — 직접 실행)')
    if rep['orders']:
        lines.append(f"    {'종목':<6}{'매매':<6}{'변경$':>12}{'주수(근사)':>12}{'가격':>10}")
        for o in rep['orders']:
            lines.append(f"    {o['ticker']:<6}{o['side']:<6}{o['delta_usd']:>12,.2f}"
                         f"{o['delta_shares']:>12,.3f}{o['price']:>10,.2f}")
    else:
        lines.append('    (리밸런스 밴드 이내 — 주문 없음)')
    lines.append('=' * 64)
    lines.append(' ⚠️ 투자 자문 아님. 집행 전 본인 판단·세금·수수료 확인. 첫 실행은 페이퍼/소액.')
    lines.append('=' * 64)
    return '\n'.join(lines)


def save_report(rep, outdir='reports'):
    """리포트를 날짜별 json + orders csv 로 저장."""
    os.makedirs(outdir, exist_ok=True)
    stamp = rep['as_of']
    jpath = os.path.join(outdir, f'advisory_{stamp}.json')
    with open(jpath, 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    cpath = os.path.join(outdir, f'orders_{stamp}.csv')
    pd.DataFrame(rep['orders']).to_csv(cpath, index=False, encoding='utf-8-sig')
    return jpath, cpath
