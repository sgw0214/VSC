# Strategy Earnings PTI V1

## 목적

기존 추세 중심 전략을 폐기하고, 공시 기반 실적 개선 종목을 선별하는 실적 중심 전략으로 전환한다.

핵심 철학:

- 주 신호는 실적
- 가격은 과열 회피와 최소 추세 확인용
- 매크로는 노출 조절용
- 백테스트 기준 실적은 `PTI(point-in-time)`만 사용

## 데이터 기준

- 메인 데이터셋:
  - `C:\Users\sgw02\OneDrive\python\new_strategy\feature_daily.pkl`

사용 컬럼:

- 실적:
  - `op_income_yoy_pct_pti`
  - `net_income_yoy_pct_pti`
  - `op_income_qoq_pct_pti`
  - `net_income_qoq_pct_pti`
  - `op_margin_pti`
  - `days_since_filing`
- 가격/리스크:
  - `close`
  - `ma_mid`
  - `ret_5`
  - `atr_ratio`
  - `adv20`
  - `adv20_pct_rank`
  - `is_trading_day`
- 매크로:
  - `regime`
  - `exposure`

## 1. 투자 유니버스

- 시장:
  - `KOSPI`
- 거래 가능:
  - `is_trading_day = True`
- 유동성:
  - `adv20 >= 1,000,000,000`
  - `adv20_pct_rank >= 0.50`

## 2. 실적 필수 조건

진입 후보는 아래를 모두 만족해야 한다.

- `op_income_yoy_pct_pti > 0`
- `net_income_yoy_pct_pti > 0`
- `op_margin_pti > 0`
- `days_since_filing <= 90`

의미:
- 최근 90일 이내 공시된 실적 중
- 영업이익과 순이익이 전년동기 대비 개선되고
- 마진이 양수인 종목만 본다.

## 3. 실적 가점 조건

랭킹에 반영하되 필수 조건은 아니다.

- `revenue_yoy_pct_pti > 0`
- `op_income_qoq_pct_pti > 0`
- `net_income_qoq_pct_pti > 0`

의미:
- 매출이 같이 늘고 있는지
- 직전 분기 대비 추가 개선이 있는지 본다.

## 4. 가격 보조 조건

실적이 좋아도 너무 과열된 종목은 피한다.

- `close > ma_mid`
- `ret_5 <= 0.10`
- `atr_ratio <= 0.10`
- `close / ma_mid - 1 <= 0.15`

의미:
- 완전 역추세 종목은 피하고
- 단기 급등 추격도 피한다.

## 5. 매크로 조건

- `risk_on`
  - 정상 운영
- `neutral`
  - 신규 매수 허용, 보유 수 축소 가능
- `risk_off`
  - 신규 매수 중단 또는 보유 수 0~1로 축소

초기 백테스트 규칙:
- `risk_off`에서는 신규 진입 금지

## 6. 랭킹 스코어

기본 랭킹은 PTI 실적 개선 정도를 중심으로 계산한다.

## 사용 변수

- `op_income_yoy_pct_pti`
- `net_income_yoy_pct_pti`
- `op_income_qoq_pct_pti`
- `net_income_qoq_pct_pti`
- `op_margin_pti`

## 스코어 공식

각 날짜별 cross-sectional z-score 기준:

```text
earnings_score =
  0.35 * z(op_income_yoy_pct_pti)
+ 0.25 * z(net_income_yoy_pct_pti)
+ 0.15 * z(op_income_qoq_pct_pti)
+ 0.10 * z(net_income_qoq_pct_pti)
+ 0.15 * z(op_margin_pti)
```

보조 점수:

```text
freshness_score = -z(days_since_filing)
```

최종:

```text
rank_score =
  0.90 * earnings_score
+ 0.10 * freshness_score
```

## 7. 매수 규칙

- 필수 조건 통과 종목만 후보
- 후보 중 `rank_score` 상위 10개 추출
- 실제 보유는 상위 5개 이하
- 동일 종목 재진입은 같은 날 금지

## 8. 매도 규칙

### 손절

- 기본:
  - ATR 손절 유지

### 추세 붕괴

- `ma_short`, `ma_mid` 동시 하락
- 기존 추세 확인 매도 유지 가능

### 실적 악화

신규 공시가 나온 뒤 아래 중 하나면 매도 후보:

- `op_income_yoy_pct_pti <= 0`
- `net_income_yoy_pct_pti <= 0`
- `op_margin_pti <= 0`

### 매크로 방어

- `risk_off` 진입 시 신규 매수 중단
- 필요시 보유 수 축소

## 9. 백테스트 규칙

- 데이터:
  - `feature_daily.pkl`
- 실적 사용:
  - `PTI`만 사용
- 기간:
  - 기존 walk-forward 구조 유지 가능
- 보유 수:
  - 최대 `5`
- 후보 수:
  - 상위 `10`
- 비용:
  - 아직 미반영이면 추후 추가

## 10. 검증 포인트

1. 전체 시장
2. 업종별
3. 시총구간별
4. `risk_on / neutral / risk_off` 별

특히 확인할 것:

- 실적 개선형이 건설/기계/금융에서 다르게 작동하는지
- 소형주에서 실적 신호가 더 강한지
- 공시 후 5/20/60일 수익률 중 어느 구간이 가장 잘 반응하는지

## 11. 구현 우선순위

1. `rank_score` 계산 컬럼 추가
2. 실적 필수 조건 필터 구현
3. `risk_off` 신규 매수 금지 룰 반영
4. 백테스트 수행
