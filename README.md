# 📈 미국 주식 AI 앙상블 예측 모델 (US Stock AI Ensemble)

> NVDA(엔비디아) 등 미국 주식의 다음 영업일 방향성을 예측하는 AI 앙상블 모델

---

## 🔍 프로젝트 개요

거시경제 지표와 기술적 지표를 융합한 **3중 앙상블 AI 모델**로 미국 주식의 상승/하락 방향성을 예측합니다.  
단순한 가격 예측을 넘어 **실전 매매 시그널 대시보드**와 **백테스팅**까지 구현했습니다.

---

## 🧠 모델 구조

```
[주가 데이터 (yfinance)]   [거시경제 지수 (S&P500, NDX, VIX, DXY, OIL, TNX)]
              ↓                              ↓
         Feature Engineering (기술적 지표 30개+)
                          ↓
         RandomForest Feature Selection
                          ↓
     ┌────────────────────┬─────────────────┐
     │   PatchTST (LSTM)  │   LightGBM      │   RandomForest
     │   (Transformer)    │   (Optuna 튜닝) │   (500 Trees)
     └────────────────────┴─────────────────┘
                          ↓
              Soft Voting Ensemble (1:1:1)
                          ↓
             매매 시그널 대시보드 출력
```

---

## ⚙️ 사용 기술

| 분류 | 기술 |
|------|------|
| **딥러닝** | PyTorch, PatchTST (Transformer 기반 시계열 모델) |
| **머신러닝** | LightGBM, RandomForest |
| **하이퍼파라미터 최적화** | Optuna |
| **데이터 수집** | yfinance, FinanceDataReader |
| **기술적 지표** | ta 라이브러리 (RSI, MACD, Bollinger Bands 등) |
| **전처리** | RobustScaler, RandomForest Feature Selection |
| **GPU 가속** | CUDA (RTX 5060 Ti) |

---

## 📊 입력 피처

### 기술적 지표
- **이동평균**: SMA(5, 10, 20, 60, 120), EMA(12, 26)
- **모멘텀**: RSI(7, 14, 21), MACD, Stochastic
- **변동성**: Bollinger Bands, ATR, 단기/장기 변동성 비율
- **거래량**: OBV, Volume Ratio

### 거시경제 지표
| 지표 | 설명 |
|------|------|
| S&P 500 | 미국 대형주 지수 |
| NASDAQ 100 | 기술주 지수 |
| VIX | 공포 지수 |
| DXY | 달러 인덱스 |
| WTI 원유 | 에너지 가격 |
| 10년 국채 금리 | 금리 환경 |

---

## 🚀 주요 기능

### 1. 실전 매매 시그널 대시보드
```
=================================================================
 🔮 PyTorch 앙상블 실전 매매 시그널 대시보드: NVDA
=================================================================
 📅 기준 거래일  : 2026-06-25 (종가: $135.42)
 🎯 타겟 예측    : 미래 1영업일 뒤 방향성
 🛡️ 매매 룰 세팅 : 숏(인버스) 절대 금지 | 강제 홀딩 기간: 5일
-----------------------------------------------------------------
 [모델 1] PyTorch PatchTST : 63.2% (Opinion: 📈 BUY)
 [모델 2] LightGBM         : 58.7% (Opinion: 📈 BUY)
 [모델 3] RandomForest     : 61.1% (Opinion: 📈 BUY)
─────────────────────────────────────────────────────────────────
 🏆 앙상블 최종 결론 : 🔥 강력 매수 (STRONG LONG)
 📊 시그널 신뢰 강도 : 24.7%
=================================================================
```

### 2. 백테스팅
- 테스트 세트에서 Buy & Hold 전략 대비 AI 전략 수익률 비교
- 숏(인버스) 금지 + 5일 강제 홀딩 + 현금 관망 로직 적용

### 3. Optuna 자동 하이퍼파라미터 최적화
- LightGBM 파라미터 자동 탐색
- 최적 Threshold 자동 탐색

---

## 📁 프로젝트 구조

```
stock-prediction-kr/
├── US_final_predict.ipynb   # 메인 노트북 (미장 전용)
└── models/
    └── NVDA/
        ├── patchtst.pth     # PatchTST 모델 가중치
        ├── lgbm.pkl         # LightGBM 모델
        ├── rf.pkl           # RandomForest 모델
        └── meta.pkl         # 전처리 객체 (scaler, selector 등)
```

---

## 🔧 설치 및 실행

```bash
# 패키지 설치
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install yfinance FinanceDataReader pykrx ta lightgbm optuna scikit-learn

# 노트북 실행
jupyter notebook US_final_predict.ipynb
```

---

## 📌 설정값 변경

`Cell 3`에서 종목 및 파라미터 변경 가능:

```python
TICKER     = 'NVDA'      # 예측 종목 (AAPL, TSLA, MSFT 등으로 변경 가능)
START_DATE = '2015-01-01'
PRED_DAYS  = 1           # 예측 기간 (영업일)
SEQ_LEN    = 60          # 시퀀스 길이
```

---

## ⚠️ 주의사항

> 이 모델은 **학습/연구 목적**으로 제작되었습니다.  
> 실제 투자 손익에 대한 책임은 본인에게 있으며, 투자 권유가 아닙니다.

---

## 🛠️ 개발 환경

- **OS**: Windows 11
- **GPU**: NVIDIA GeForce RTX 5060 Ti
- **CUDA**: 12.8
- **Python**: 3.11
- **PyTorch**: 2.12.0 (dev)
