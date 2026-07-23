"""데이터 수집 — yfinance 수정주가(auto_adjust). 연구/자문용.
※ 실전 자동매매로 가면 브로커 데이터나 유료 피드로 교체 권장(결측·정정·타임존)."""
import pandas as pd
import yfinance as yf


def fetch_close(tickers, start, end=None, min_len=300):
    """티커별 종가를 받아 '모든 자산이 존재하는 공통 구간' DataFrame으로 반환."""
    frames = {}
    failed = []
    for t in tickers:
        try:
            df = yf.download(t, start=start, end=end, auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            s = df['Close'].dropna()
            if len(s) > min_len:
                frames[t] = s
            else:
                failed.append(t)
        except Exception as e:
            failed.append(t)
            print(f'  [data] {t} 수집 실패: {e}')
    if not frames:
        raise RuntimeError('수집된 데이터가 없습니다. 네트워크/티커를 확인하세요.')
    close = pd.DataFrame(frames).dropna()
    if failed:
        print(f'  [data] 제외된 티커: {failed}')
    return close


def latest_prices(close):
    """가장 최근 거래일 종가(Series)와 그 날짜를 반환."""
    return close.iloc[-1], close.index[-1]
