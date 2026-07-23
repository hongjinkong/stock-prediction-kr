"""SEC EDGAR companyfacts 로 point-in-time(PIT) 펀더멘털 재구성.

무료 API(https://data.sec.gov). 각 재무 값에 'filed'(신고일)가 있어,
"그 날짜에 실제로 알 수 있었던 값"만 쓰면 look-ahead 없이 밸류·퀄리티를 백테스트할 수 있다.

⚠️ SEC는 User-Agent(이름/이메일) 헤더를 요구한다. .env 에 SEC_USER_AGENT 설정 권장.
   초당 ~10요청 제한 → load_fundamentals 는 종목마다 짧게 sleep.
"""
import json
import os
import time
import urllib.request

import numpy as np
import pandas as pd


def _user_agent():
    ua = os.environ.get('SEC_USER_AGENT')
    if not ua and os.path.exists('.env'):
        for line in open('.env', encoding='utf-8'):
            if line.startswith('SEC_USER_AGENT='):
                ua = line.split('=', 1)[1].strip()
                break
    return ua or 'factor-research contact@example.com'


def _get(url, retries=3):
    req = urllib.request.Request(url, headers={'User-Agent': _user_agent()})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.0)


def ticker_cik_map():
    """티커 → 10자리 CIK 매핑."""
    d = _get('https://www.sec.gov/files/company_tickers.json')
    return {v['ticker'].upper(): str(v['cik_str']).zfill(10) for v in d.values()}


def companyfacts(cik10):
    return _get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json')


def concept_df(facts, tag, taxonomy='us-gaap'):
    """companyfacts 에서 특정 개념(tag)의 시계열을 DataFrame[end, filed, val, form] 으로."""
    try:
        units = facts['facts'][taxonomy][tag]['units']
    except (KeyError, TypeError):
        return pd.DataFrame(columns=['end', 'filed', 'val', 'form'])
    rows = []
    for _unit, arr in units.items():
        for it in arr:
            if it.get('val') is None:
                continue
            rows.append({'end': it.get('end'), 'filed': it.get('filed'),
                         'val': it.get('val'), 'form': it.get('form', '')})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df['end'] = pd.to_datetime(df['end'], errors='coerce')
    df['filed'] = pd.to_datetime(df['filed'], errors='coerce')
    return df.dropna(subset=['filed']).sort_values('filed').reset_index(drop=True)


def first_available(facts, tags, taxonomy='us-gaap'):
    """여러 후보 tag 중 데이터가 있는 첫 번째 개념을 반환(회사마다 태그가 다름)."""
    for t in tags:
        df = concept_df(facts, t, taxonomy)
        if not df.empty:
            return df
    return pd.DataFrame(columns=['end', 'filed', 'val', 'form'])


def pit_value(df, asof, forms=None):
    """asof 시점에 알 수 있었던 값 = filed <= asof 중 '가장 최근 회계기간(end)'의 값.
    (같은 신고에 여러 비교기간이 섞여 있어, filed 뿐 아니라 end 로도 정렬해 최신 기간을 고른다.)"""
    if df is None or len(df) == 0:
        return np.nan
    d = df[df['filed'] <= pd.Timestamp(asof)]
    if forms is not None:
        dd = d[d['form'].isin(forms)]
        if not dd.empty:
            d = dd
    if len(d) == 0:
        return np.nan
    d = d.sort_values(['end', 'filed'])
    return float(d.iloc[-1]['val'])


def load_fundamentals(tickers, verbose=True):
    """유니버스의 핵심 재무 개념 시계열을 한 번에 로드.
    반환: {ticker: {'NI':df, 'EQ':df, 'REV':df, 'SH':df}}"""
    cmap = ticker_cik_map()
    out = {}
    for i, t in enumerate(tickers, 1):
        cik = cmap.get(t.upper())
        if not cik:
            if verbose:
                print(f'  [{i}/{len(tickers)}] {t}: CIK 없음, 건너뜀')
            continue
        try:
            f = companyfacts(cik)
        except Exception as e:
            if verbose:
                print(f'  [{i}/{len(tickers)}] {t}: 실패 {e}')
            continue
        sh = first_available(f, ['EntityCommonStockSharesOutstanding'], 'dei')
        if sh.empty:
            sh = first_available(f, ['CommonStockSharesOutstanding'], 'us-gaap')
        out[t] = {
            'NI':  first_available(f, ['NetIncomeLoss']),
            'EQ':  first_available(f, ['StockholdersEquity',
                                       'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest']),
            'REV': first_available(f, ['Revenues',
                                       'RevenueFromContractWithCustomerExcludingAssessedTax',
                                       'SalesRevenueNet']),
            'SH':  sh,
        }
        if verbose and i % 10 == 0:
            print(f'  ...{i}/{len(tickers)} 로드')
        time.sleep(0.15)   # SEC rate limit 준수
    if verbose:
        print(f'✅ 펀더멘털 로드 완료: {len(out)}종목')
    return out


def pit_factor_row(fund, tickers, asof, price_row):
    """asof 시점의 PIT 밸류·퀄리티 팩터 (종목별 Series 4종 반환).
    price_row: 그 날짜의 종목별 종가 Series (시가총액 계산용)."""
    ey, by, roe, margin = {}, {}, {}, {}
    for t in tickers:
        d = fund.get(t)
        if not d:
            continue
        ni  = pit_value(d['NI'],  asof, forms=['10-K'])   # 연간 순이익(PIT)
        eq  = pit_value(d['EQ'],  asof)                    # 자기자본(최신)
        rev = pit_value(d['REV'], asof, forms=['10-K'])   # 연간 매출(PIT)
        sh  = pit_value(d['SH'],  asof)                    # 발행주식수
        px  = price_row.get(t, np.nan)
        mktcap = px * sh if (pd.notna(px) and pd.notna(sh) and sh > 0) else np.nan
        if pd.notna(mktcap) and mktcap > 0:
            if pd.notna(ni):  ey[t] = ni / mktcap
            if pd.notna(eq):  by[t] = eq / mktcap
        if pd.notna(eq) and eq > 0 and pd.notna(ni):    roe[t] = ni / eq
        if pd.notna(rev) and rev > 0 and pd.notna(ni):  margin[t] = ni / rev
    return (pd.Series(ey), pd.Series(by), pd.Series(roe), pd.Series(margin))
