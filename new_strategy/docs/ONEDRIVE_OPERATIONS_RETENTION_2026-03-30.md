# OneDrive 운영 데이터 정리 기준

## 목적
- OneDrive 사용량을 운영 기준으로 정리한다.
- 대시보드/브리지/스케줄러가 읽는 파일은 보존한다.
- 연구 산출물과 테스트 결과는 운영 경로에서 분리한다.

## 무조건 보존
- 루트 데이터
  - `feature_daily.csv`
  - `feature_daily.pkl`
  - `price_panel.csv`
  - `fundamental_quarterly_raw.csv`
  - `fundamental_quarterly_multi.csv`
  - `macro_daily.csv`
  - `gold_kr_daily.xlsx`
  - `market_data.db`
- 운영 출력
  - `output/strategy_v2/**`
- MA 계약 운영 입력
  - `output/ma_breakout_research/all_action_modes_returns_by_stock.csv`
  - `output/ma_breakout_research/native_timeframe_close_returns_by_stock.csv`
  - `output/ma_breakout_research/published/**`
  - `output/v2_four_timing_mode_grid/best_mode_by_stock_full.csv`

## 운영 중복/낮은 우선순위
- `feature_daily.parquet`
  - 현재 런타임 기본 경로에서 직접 참조하지 않음
- `price_panel_sample.csv`
  - 샘플 파일
- `* (1).json`
  - 중복 메타 파일

## 연구 산출물 분리 대상
- `output/strategy_compare*`
- `output/v2_*` 연구 결과 디렉터리
  - 단, `output/v2_four_timing_mode_grid/best_mode_by_stock_full.csv`는 보존
- `output/ma_breakout_research` 내부
  - `archive/`
  - `analysis/`
  - `charts/`
  - `daily_close_action_returns_by_stock.csv`
  - `best_window_by_stock.csv`
  - `best_window_distribution.csv`
  - `summary_report.md`
  - `run_meta.json`

## 런타임 보존 기간 관리 대상
- `output/strategy_v2/dashboard_pipeline_runs/*`
- `output/strategy_v2/*.log`
- `output/strategy_v2/telegram_bridge/briefings/*`
- `output/strategy_v2/telegram_bridge/mockups/*`
- `output/strategy_v2/telegram_bridge/*.log`

## 도구
- 인벤토리/아카이브 스크립트
  - `python -m new_strategy.ops_storage_cleanup`
- 아카이브 실제 적용
  - `python -m new_strategy.ops_storage_cleanup --apply-archive`
- 런타임 산출물 14일 초과 정리
  - `python -m new_strategy.ops_storage_cleanup --prune-runtime-days 14`

## 원칙
- 운영 입력/상태 파일은 삭제보다 보존 우선
- 연구 산출물은 삭제보다 `output/_ops_archive/<timestamp>/` 이동 우선
- 런타임 로그/이미지는 기간 기준으로 정리
