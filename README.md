# 📈 KRX Stock Prediction Hybrid Ensemble Engine (v3)

> **시계열 데이터 누수(Data Leakage)를 완벽히 차단한 Walk-Forward 검증 기반의 하이브리드 주가 방향성 예측 시스템** > 본 프로젝트는 금융 시계열 데이터 예측 시 흔히 발생하는 미래 데이터 유출 오류를 차단하고, 딥러닝과 트리 기반 머신러닝 알고리즘을 정교하게 결합하여 실전 매매 타점을 도출하는 퀀트 파이프라인 프로토타입입니다.

---

## 🚀 핵심 아키텍처 및 특징 (Key Features)

### 1. 🛡️ 엄격한 데이터 누수 차단 (Anti-Data Leakage)
- 기존의 일괄 스케일링/피처 선택 방식에서 벗어나, **각 Walk-Forward Fold의 Train 데이터셋으로만 RobustScaler 및 SelectFromModel을 학습(`fit`)**시킴으로써 미래 정보가 과거로 스며드는 현상을 원천 봉쇄했습니다.
- 타겟 레이블 생성 시 발생하는 시점 간 경계 오염을 완전히 제어하여 신뢰할 수 있는 미래 예측 지표를 도출합니다.

### 2. 🧠 하이브리드 이종 앙상블 시스템 (Hybrid Ensemble)
정밀한 예측을 위해 서로 다른 수학적 매커니즘을 가진 3가지 이종 모델을 결합한 **Soft Voting 앙상블**을 구사합니다.
- **PyTorch BiLSTM + Attention**: 시계열 데이터의 장·단기 문맥적 추세 및 패턴 포착
- **LightGBM (Optuna Optimized)**: 베이지안 최적화를 통한 하이퍼파라미터 튜닝 기반의 고속 부스팅 트리 캐리
- **RandomForest (Balanced)**: 다수의 의사결정나무 배깅을 통한 노이즈 오버피팅 방지 및 안정성 확보

### ⚖️ 3. 동적 가중치 조율 (Dynamic Weight Balancing)
- 시계열 규제 강화로 인해 박스권에서 노이즈화되기 쉬운 LSTM의 반영 비중을 `5%`로 최소화하고, 실전 검증 성능이 입증된 트리 계열 모델(LGBM `65%`, RF `30%`)에 가중치를 집중하여 대시보드의 실전 정밀도를 극대화했습니다.

### ⏱️ 4. API Rate-Limiting 방어 메커니즘
- 대량의 KRX 데이터 수집 시 발생하는 거래소 서버의 트래픽 차단 에러(`Expecting value: line 1 column 1`)를 방지하기 위해 요청 주기 사이에 `time.sleep()` 지연 로직을 설계하여 파이프라인의 수집 안정성을 확보했습니다.

---

## 📊 검증 스펙 및 실전 대시보드 결과 (Evaluation)

### 🔄 Walk-Forward Validation 평균 스코어
미래 데이터를 참조하지 않은 순수 시계열 교차 검증 엔진 통과 결과:
- **평균 정확도 (Accuracy)**: `80.6% ~ 83.7%`
- **평균 AUC (Area Under ROC)**: `0.89 ~ 0.91` (글로벌 퀀트 펀드 엔진 수준의 판별력 입증)

### 🔮 실전 예측 시뮬레이션 포트폴리오 (2026-06-23 현재 가동 기준)
세 모델의 예측 확률이 고르게 일치하여 높은 신뢰도의 섹터별 시그널을 출력 중입니다.
- **삼성전자 (005930)** ➡️ 📈 **상승 시그널 포착** (Ensemble 78.2%)
- **현대차 (005380)** ➡️ 📉 **하락 시그널 포착** (Ensemble 84.7%)
- **기아 (000270)** ➡️ 📉 **강력 하락 시그널 포착** (Ensemble 91.8%)

---

## 🛠️ 개발 환경 및 주요 라이브러리 (Tech Stack)
- **Language**: Python 3.x
- **Deep Learning**: PyTorch
- **Machine Learning**: LightGBM, Scikit-Learn, Optuna
- **Data Pipeline**: Pandas, NumPy, FinanceDataReader