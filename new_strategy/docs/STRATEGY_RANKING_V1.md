# Strategy Ranking V1

## 목표

`feature_daily` 기반으로 가격, 매크로, 재무를 같이 쓰는 실전형 랭킹 전략의 초안을 정의한다.

## 데이터 기준

- 백테스트/실전:
  - `*_pti` 사용
- 구조 분석/설명:
  - `*_period` 참고

## 1. 투자 유니버스

- 시장:
  - KOSPI
- 거래 가능 조건:
  - `is_trading_day = True`
- 유동성 필터:
  - `adv20 >= 1,000,000,000`
  - `adv20_pct_rank >= 0.70`
  - `liq_strength >= 1.0`

## 2. 매크로 게이트

- 기본:
  - `regime != risk_off`
- 노출:
  - `risk_on = 1.0`
  - `neutral = 0.3`
  - `risk_off = 0.1`
- 해석:
  - `gold_kr_close`가 60일 평균을 강하게 상회하면 방어 레짐 신호 강화

## 3. 추세 조건

- 구조:
  - `close > ma_short > ma_mid > ma_long`
- 방향:
  - `ma_short_slope > 0`
  - `ma_mid_slope > 0`
  - `ma_long_slope > 0`

## 4. 실적 품질 조건

PTI 기준 사용:

- `revenue_yoy_pct_pti > 0`
- `op_income_yoy_pct_pti > 0`
- `net_income_yoy_pct_pti > 0`
- `op_margin_pti > 0`

추가 가점:

- `op_income_qoq_pti > 0`
- `net_income_qoq_pti > 0`
- `days_since_filing <= 90`

## 5. 진입 회피 조건

- 단기 과열 회피:
  - `ret_5 <= 0.12`
  - `dist_ma_mid <= 0.18`
  - `atr_ratio <= 0.08`

## 6. 랭킹 스코어 초안

### 가격/추세

- `quality_score`
- `momentum_score`

### 재무

- `op_income_yoy_pct_pti`
- `net_income_yoy_pct_pti`
- `op_margin_pti`

### 신선도

- `-days_since_filing`

## 예시 합성 점수

```text
rank_score =
  0.35 * z(quality_score)
+ 0.20 * z(momentum_score)
+ 0.20 * z(op_income_yoy_pct_pti)
+ 0.15 * z(net_income_yoy_pct_pti)
+ 0.10 * z(op_margin_pti)
```

## 7. 매수 후보

- 필터 통과 종목 중 `rank_score` 상위 10개
- 실제 보유는 상위 5개 이하

## 8. 매도 조건

- 기존 조건 유지:
  - ATR 손절
  - 5주선/10주선 동시 하락
- 재무 악화 보조 조건:
  - 신규 공시 후
  - `op_income_yoy_pct_pti < 0`
  - `net_income_yoy_pct_pti < 0`
  - 이 경우 강제 매도 후보로 기록

## 9. 다음 구현 단계

1. `feature_daily`에서 `rank_score` 계산
2. PTI 실적 필터를 랭킹/매수 조건에 결합
3. 기존 백테스트와 성과 비교
