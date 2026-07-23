# 🧭 프로젝트 여정 (PROJECT JOURNEY)

> **한 줄 요약**
> "주가를 예측한다"는 환상에서 출발 → 엄격한 검증으로 **"일봉 기술지표엔 알파 없음(효율적 시장)"** 을 실증 →
> 예측 대신 **리스크 관리(추세추종)** 로 전환 → **실제 페이퍼 자동매매**까지 구현 →
> 진짜 엣지를 찾아 **펀더멘털(SEC point-in-time) 데이터**로 확장.

---

## 단계별 여정 (무엇 / 어떻게 / 결과)

### Phase 1 — 예측 모델 진단·교정
- **무엇**: 기존 AI 주가예측 모델(NVDA 단일종목, 29종목 크로스섹셔널)의 버그·데이터 누출 제거
- **어떻게**: `bfill`(미래값 역채움) 제거 · `auto_adjust` 수정주가 · 실전예측 시점버그(`for_predict`) 수정 ·
  Optuna 테스트구간 배제 · **Purged Walk-Forward CV**(겹침 라벨 누출 제거) · 거래비용 백테스트 ·
  Sharpe/MDD/Calmar · 확률 캘리브레이션 · 시드 고정
- **결과**: 누출 제거 후 NVDA Test AUC 0.60까지 상승 (겉보기 성공)

### Phase 2 — 견고성 검증 → 착시 발각
- **무엇**: 0.60이 진짜인지 검증
- **어떻게**: `robustness_check.py` 로 AAPL·MSFT·JPM·TSLA·NVDA에 동일 파이프라인 반복
- **결과**: 평균 AUC **0.53**, 5개 중 3개 동전던지기. NVDA 재실행 시 0.60→0.55 → **첫 0.60은 실행 변동성의 운**

### Phase 3 — 크로스섹셔널 전환 → 정직한 결론
- **무엇**: 단일종목 방향성 대신 29종목 상대 랭킹
- **어떻게**: 경제적 기준 threshold · 거래비용·레짐분해 · 종목쏠림 자동경고
- **결과**: Test AUC **0.52**, 비용 반영 시 **시장보유에 열위**, 초과수익 = 소수 모멘텀주 반복베팅 →
  **"일봉 기술지표로는 거래비용 이기는 알파 없음"** = 효율적 시장 실증 → [`FINDINGS.md`](FINDINGS.md)

### Phase 4 — 문제 재정의: 규칙기반 추세추종
- **무엇**: 예측(맞히기) ✕ → 반응(추세 올라타기) ○
- **어떻게**: `US_trend_following.ipynb`(5규칙 vs Buy&Hold, 9자산) ·
  `US_trend_portfolio.ipynb`(다자산 분산 + 변동성 타겟팅 + 레짐 필터)
- **결과**: 추세추종 = "덜 잃고 오래 버티는 법"(MDD 방어). 파라미터 **고정** → 과적합 없음

### Phase 5 — 실전화 (모듈화 → 페이퍼 자동매매)
- **무엇**: 연구 노트북 → 실제 운용 가능한 시스템
- **어떻게**: `trend_system/` 패키지(config·data·signals·portfolio·report·broker·notify) ·
  `advisory.py`(자문 리포트) · `paper_trade.py`(**Alpaca 페이퍼 자동집행**) · `monitor.py`(성과추적) ·
  안전장치(미체결 시 중복차단) · 텔레그램 알림 · 월간 스케줄러
- **결과**: **Alpaca 페이퍼 계좌에 실제 6종목 주문 집행 성공** + 성과 추적 시작

### Phase 6 — 저장소 폴더 정리
- `docs/` · `notebooks/(prediction·trend·factor)` · `scripts/` · `trend_system/` 구조화
- 개인정보(`.env`·`holdings.json`·`reports/`) gitignore 차단

### Phase 7 — 진짜 엣지 탐색: 다중 팩터 + PIT 펀더멘털
- **무엇**: "더 좋은 모델"이 아니라 "다른 데이터/문제"로 확장
- **어떻게**: `US_factor_model.ipynb`(가격 3팩터 크로스섹셔널) ·
  `trend_system/fundamentals.py`(**SEC EDGAR point-in-time 재무 재구성** — 신고일 기준, look-ahead 차단) ·
  `US_factor_pit.ipynb`(밸류·퀄리티까지 정직한 5팩터 백테스트)
- **결과**: 무료 데이터로 펀더멘털을 과거 시점 정확하게 사용 가능

---

## 관통한 방법론 ("어떻게")

- **데이터**: yfinance(가격) · SEC EDGAR companyfacts(PIT 재무) · Alpaca(브로커)
- **검증 원칙** (모든 단계 공통):
  - 룩어헤드 방지(신호 t → t+1 체결), 거래비용 반영
  - 다자산·다구간 견고성 확인 (단일 결과 불신)
  - 파라미터 고정 (최적화 = 과적합의 시작)
  - 네트워크 없이 합성 데이터로 오프라인 검증 후 커밋
- **도구**: Python(pandas·numpy) · PatchTST/LightGBM/RandomForest · Optuna · matplotlib
- **운영**: 전 과정 git 커밋(정직한 이력) · 개인정보 gitignore · 결론을 미화 없이 문서화

---

## 핵심 교훈

1. **누출을 제거하면 "고성능"의 대부분이 사라진다** — 엄격함이 자기기만을 막는 최고의 자산
2. **일봉 기술지표로 대형주 방향 예측 = 알파 없음** (시장이 그만큼 효율적)
3. **예측 실패 ≠ 프로젝트 실패** — 리스크 관리로 전환한 것이 정직하고 견고한 답
4. **진짜 엣지는 더 좋은 모델이 아니라 다른 데이터/문제에서** 나온다

---

## 저장소 구조

```
stock-prediction-kr/
├── docs/
│   ├── FINDINGS.md              정직한 결과 보고서
│   └── PROJECT_JOURNEY.md       이 문서
├── notebooks/
│   ├── prediction/              예측 모델 (결론: 알파 없음)
│   ├── trend/                   추세추종 (실전 채택)
│   └── factor/                  다중 팩터 + PIT 펀더멘털
├── trend_system/                실전 운용 패키지
├── scripts/                     advisory · paper_trade · monitor
└── models/                      저장된 모델 (로컬)
```

> ⚠️ 본 저장소의 어떤 것도 투자 자문이 아니며, 실거래 사용을 권장하지 않는다. 교육/연구 기록이다.
