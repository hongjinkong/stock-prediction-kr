"""전략 설정 — 모든 파라미터는 '관습값'으로 고정한다.
이 데이터에 맞춰 최적화하는 순간 과적합이 시작되므로, 라이브 성과가 나빠도 여기를 튜닝하지 말 것."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # 유니버스: 지수 ETF + 대형주 + 금 + 채권
    tickers: List[str] = field(default_factory=lambda: [
        'SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'JPM', 'XOM', 'GLD', 'TLT'
    ])
    start: str = '2010-01-01'

    trend_win: int = 200      # 추세 필터: 종가 > 200일 이동평균 이면 상승추세
    vol_win: int = 63         # 변동성 추정 창(약 3개월)
    risk_frac: float = 0.03   # 자산당 목표 변동성 기여(연 3%) → 역변동성 비중
    w_cap: float = 0.30       # 종목당 최대 비중
    target_lev: float = 1.0   # 총 노출 상한(레버리지 금지 = 롱/현금)
    rebal: int = 21           # 백테스트 리밸런스 주기(영업일)
    cost: float = 0.0005      # 편도 거래비용 0.05%
    ann: int = 252            # 연 거래일

    use_regime: bool = False  # True면 SPY가 200일선 아래일 때 전체 현금화
    regime_ticker: str = 'SPY'

    rebal_band: float = 0.03  # 비중 드리프트가 이 값 미만이면 주문 생략(회전율 억제)


DEFAULT = Config()
