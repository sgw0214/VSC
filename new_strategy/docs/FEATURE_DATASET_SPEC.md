# Feature Dataset Spec

## 목적

전략 연구와 백테스트에 사용할 `date + code` 기준 단일 분석 데이터셋을 정의한다.

이 데이터셋은 두 가지 재무 관점을 동시에 가진다.

- `PTI(point-in-time)`
  - 해당 날짜까지 실제로 공시되어 시장이 알 수 있었던 최신 실적
  - 백테스트/실전용
- `period`
  - 해당 날짜가 속한 분기의 실제 발생 실적
  - 상관분석/설명/EDA용

## 기본 키

- `date`
- `code`

## 입력 데이터

- 주가 패널
  - `C:\Users\sgw02\OneDrive\python\new_strategy\price_panel.csv`
- 매크로 레짐
  - `C:\Users\sgw02\OneDrive\python\new_strategy\macro_regime_v3_rec.csv`
- 재무 최종본
  - `C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_multi.csv`

## 출력 파일

- 기본:
  - `C:\Users\sgw02\OneDrive\python\new_strategy\feature_daily.csv`

## 컬럼 그룹

### 1. 식별자

- `date`
- `code`
- `name`
- `market`
- `industry`

### 2. 가격/거래

- `open`
- `high`
- `low`
- `close`
- `volume`
- `trading_value`
- `market_cap`
- `shares_outstanding`
- `is_trading_day`

### 3. 기술/유동성 피처

- `adv20`
- `adv60`
- `ma_short`
- `ma_mid`
- `ma_long`
- `ma_short_slope`
- `ma_mid_slope`
- `ma_long_slope`
- `ret_5`
- `ret_20`
- `ret_60`
- `ret_120`
- `atr20`
- `atr_ratio`
- `dist_ma_mid`
- `momentum_score`
- `trend_strength`
- `liq_strength`
- `quality_score`

### 4. 매크로/레짐

- `kospi`
- `vix`
- `usdkrw`
- `us10y`
- `kr10y`
- `gold_kr_close`
- `gold_kr_ret`
- `gold_kr_volume`
- `gold_kr_trading_value`
- `regime`
- `exposure`

### 5. 재무 PTI

- `filing_date_pti`
- `days_since_filing`
- `revenue_pti`
- `op_income_pti`
- `net_income_pti`
- `op_margin_pti`
- `roe_simple_pti`
- `fiscal_year_pti`
- `reprt_code_pti`

설명:
- 각 날짜별로 `공시일 <= date` 인 최신 실적이 붙는다.

### 6. 재무 period

- `period_start`
- `period_end`
- `revenue_period`
- `op_income_period`
- `net_income_period`
- `op_margin_period`
- `roe_simple_period`
- `fiscal_year_period`
- `reprt_code_period`

설명:
- 날짜가 속한 실제 달력 분기에 맞는 분기 실적이 붙는다.
- 매핑:
  - 1~3월 -> `11013`
  - 4~6월 -> `11012`
  - 7~9월 -> `11014`
  - 10~12월 -> `11011`

## 사용 원칙

### 백테스트

- `*_pti`만 사용
- `period` 컬럼 사용 금지

### 분석/EDA

- `*_period` 사용 가능
- `*_pti`와 비교하면
  - 선행 반응
  - 공시 반응
  - 시차 효과
  를 분리해서 볼 수 있다.

## 구현 메모

- 재무 PTI는 `merge_asof` 방식으로 공시일 기준 결합
- 재무 period는 날짜의 달력 분기와 `사업연도 + 보고서코드` 기준 결합
- 장기적으로는 이 파일을 기반으로 별도 타깃 컬럼
  - `fwd_ret_5d`
  - `fwd_ret_20d`
  - `fwd_ret_60d`
  를 추가할 수 있다.
