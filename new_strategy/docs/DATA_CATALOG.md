# Data Catalog

## 경로 기준

- 코드:
  - `E:\VSC\CODE\new_strategy`
- 전략 데이터 루트:
  - `C:\Users\sgw02\OneDrive\python\new_strategy`
- 주가 원본 루트:
  - `C:\Users\sgw02\OneDrive\python\Stock`

## 1. 주가 원천 데이터

### `C:\Users\sgw02\OneDrive\python\Stock\basic_YYYYMMDD.xlsx`
- 역할:
  - 일자별 개별 종목 원천 주가 파일
- 성격:
  - 가장 세밀한 raw 데이터
- 사용 시점:
  - 원본 검증
  - 특정 날짜 재점검
- 비고:
  - 전략 파이프라인은 현재 이 파일들을 직접 읽기보다 연도별 파일을 주로 사용

### `C:\Users\sgw02\OneDrive\python\Stock\2015.xlsx ~ 2025.xlsx`
- 역할:
  - 연도별 통합 주가 원본
- 성격:
  - 전략용 주가 입력의 기준 raw
- 사용 코드:
  - `new_strategy/build_price_panel.py`
  - `new_strategy/build_market_db.py`
- 비고:
  - 현재 전략 파이프라인의 핵심 원천 주가 데이터

### `C:\Users\sgw02\OneDrive\python\Stock\Total.xlsx`
- 역할:
  - 전체 기간 통합본으로 보이는 별도 파일
- 성격:
  - 보조 raw
- 사용 시점:
  - 연도별 파일 검증
  - 누락 점검
- 비고:
  - 현재 자동 파이프라인의 기본 입력은 아님

## 2. 주가 가공 데이터

### `C:\Users\sgw02\OneDrive\python\new_strategy\price_panel.csv`
- 역할:
  - 전략/백테스트용 표준 일별 주가 패널
- 성격:
  - 핵심 가공 데이터
- 생성 코드:
  - `new_strategy/build_price_panel.py`
- 주요 컬럼:
  - `date`, `code`, `name`, `market`, `industry`
  - `open`, `high`, `low`, `close`, `volume`, `trading_value`
  - `market_cap`, `shares_outstanding`
- 사용 코드:
  - `new_strategy/backtest_walkforward.py`
  - `new_strategy/recommend_latest.py`
  - `new_strategy/fetch_fundamental_dart.py`
  - `new_strategy/fetch_macro_investing.py`

### `C:\Users\sgw02\OneDrive\python\new_strategy\price_panel_sample.csv`
- 역할:
  - 샘플/테스트용 가격 패널
- 성격:
  - 보조 파일
- 비고:
  - 운영 필수는 아님

## 3. 재무 데이터

### `C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_raw.csv`
- 역할:
  - DART 원응답 누적 저장본
- 성격:
  - raw 재무 데이터
- 생성 코드:
  - `new_strategy/fetch_fundamental_dart.py`
- 사용 시점:
  - 재집계
  - 원본 검증
  - 컬럼 로직 수정 후 재생성

### `C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_multi.csv`
- 역할:
  - 전략용 분기 재무 최종본
- 성격:
  - 핵심 가공 데이터
- 생성 코드:
  - `new_strategy/fetch_fundamental_dart.py`
- 주요 내용:
  - 종목코드 기준 분기/반기/연간 재무
  - 분기 매출액, 분기 영업이익, 분기 당기순이익 파생 컬럼 포함
- 사용 시점:
  - 종목 선별
  - 실적 기반 필터/랭킹
  - 통합 DB 적재

### `C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_multi_request_log.csv`
- 역할:
  - DART 호출 이력 관리
- 성격:
  - 운영 보조 파일
- 사용 시점:
  - 중복 호출 방지
  - 누락 재수집 범위 계산

### `C:\Users\sgw02\OneDrive\python\new_strategy\dart_corp_codes.csv`
- 역할:
  - 종목코드와 DART 법인코드 매핑 캐시
- 성격:
  - 재무 수집 보조 기준표
- 사용 코드:
  - `new_strategy/fetch_fundamental_dart.py`

## 4. 매크로 데이터

### `C:\Users\sgw02\OneDrive\python\new_strategy\macro_daily.csv`
- 역할:
  - 일별 매크로 원천 시계열
- 성격:
  - 핵심 매크로 raw/준가공 데이터
- 현재 포함:
  - `kospi`
  - `vix`
  - `usdkrw`
  - `us10y`
  - `kr10y`
- 생성 코드:
  - `new_strategy/fetch_macro_investing.py`
- 비고:
  - 금 데이터도 이 파일에 합쳐서 매크로 보조지표로 관리하는 방향이 적절함

### `C:\Users\sgw02\OneDrive\python\new_strategy\macro_regime_v3_rec.csv`
- 역할:
  - 일별 레짐 및 노출 비중 기준표
- 성격:
  - 핵심 전략 입력 데이터
- 생성 코드:
  - `new_strategy/macro_pipeline.py`
- 사용 코드:
  - `new_strategy/backtest_walkforward.py`
  - `new_strategy/recommend_latest.py`

### `C:\Users\sgw02\OneDrive\python\new_strategy\macro_coverage_report.csv`
- 역할:
  - 매크로 데이터 커버리지 점검표
- 성격:
  - 품질 점검용 보조 파일

### `C:\Users\sgw02\OneDrive\python\new_strategy\gold_kr_daily.xlsx`
- 역할:
  - 국내 금 일별 데이터
- 성격:
  - 매크로 보조지표 원천 데이터
- 생성 코드:
  - `new_strategy/gold_kr_api.py`
- 권장 위치:
  - 별도 자산 데이터로 두기보다 `macro_daily.csv`에 병합해 사용하는 것이 일관적임
- 활용 예:
  - 위험회피 강도 확인
  - 원자재/안전자산 추세 확인
  - 레짐 보조 필터

## 5. 통합 저장소

### `C:\Users\sgw02\OneDrive\python\new_strategy\market_data.db`
- 역할:
  - 주가 + 매크로 + 재무 통합 DB
- 성격:
  - 조회/분석용 통합 저장소
- 생성 코드:
  - `new_strategy/build_market_db.py`
- 테이블:
  - `dim_symbol`
  - `fact_price_daily`
  - `fact_macro_daily`
  - `fact_fundamental_quarterly`
- 사용 목적:
  - 전략 연구
  - 빠른 조회
  - 향후 대시보드 백엔드

## 6. 캐시

### `C:\Users\sgw02\OneDrive\python\new_strategy\cache\yearly\*.pkl`
- 역할:
  - 연도별 주가 원본 캐시
- 성격:
  - 속도 최적화용 캐시
- 생성 코드:
  - `new_strategy/build_price_panel.py`
- 비고:
  - `Stock\2015.xlsx~2025.xlsx`가 바뀌면 해당 연도 캐시만 재생성됨

### `C:\Users\sgw02\OneDrive\python\new_strategy\cache\features\features.pkl`
- 역할:
  - 백테스트 피처 캐시
- 성격:
  - 속도 최적화용 캐시
- 사용 코드:
  - `new_strategy/backtest_walkforward.py`
- 비고:
  - 운영 필수는 아니며, 백테스트 시 다시 생성 가능

## 7. 전략 기준 분류

### 필수
- `Stock\2015.xlsx ~ 2025.xlsx`
- `price_panel.csv`
- `fundamental_quarterly_multi.csv`
- `macro_daily.csv`
- `macro_regime_v3_rec.csv`

### 준필수
- `dart_corp_codes.csv`
- `fundamental_quarterly_raw.csv`
- `market_data.db`
- `cache\yearly\*.pkl`

### 보조
- `gold_kr_daily.xlsx`
- `macro_coverage_report.csv`
- `fundamental_quarterly_multi_request_log.csv`
- `price_panel_sample.csv`
- `cache\features\features.pkl`

## 8. 권장 정리 방향

- 금 데이터는 별도 파일로 보관하되, 전략 입력에서는 `macro_daily.csv`에 병합
- 전략/대시보드는 최종적으로 아래 4개를 기준 입력으로 사용
  - `price_panel.csv`
  - `fundamental_quarterly_multi.csv`
  - `macro_daily.csv`
  - `macro_regime_v3_rec.csv`
- 조회/분석 속도를 위해 `market_data.db`를 병행 유지
