# Workstream Split 2026-03-16

## 목적

현재 코드베이스를 아래 3개 작업 스트림으로 분리한다.

1. `T1: Telegram Bridge / 운영 응답`
2. `L1: Live Strategy / Dashboard / Signal Engine`
3. `M1: MA Breakout Simulation / Research`

핵심 원칙은 다음과 같다.

- `T1`과 `M1`은 직접 연결하지 않는다.
- `M1`은 연구 산출물만 만든다.
- `L1`만 `M1`의 확정 산출물을 읽어 라이브 전략에 반영한다.
- `T1`은 오직 `L1`의 최신 결과만 읽는다.

## 현재 코드베이스에서 확인한 경계

### 1. Telegram Bridge / 운영 응답

주요 코드:

- `new_strategy/telegram_bridge_config.py`
- `new_strategy/telegram_bridge_memory.py`
- `new_strategy/telegram_bridge_models.py`
- `new_strategy/telegram_bridge_portfolio.py`
- `new_strategy/telegram_bridge_router.py`
- `new_strategy/telegram_bridge_service.py`
- `new_strategy/telegram_bridge_tools.py`
- `new_strategy/telegram_helper.py`

관련 문서:

- `new_strategy/docs/TELEGRAM_BRIDGE_2026-03-16_ACTION_LOG.md`
- `new_strategy/docs/TELEGRAM_BRIDGE_DESIGN.md`

주요 출력 경로:

- `output/strategy_v2/telegram_bridge/`
- `output/strategy_v2/telegram_bridge/manual_portfolio_positions.csv`
- `output/strategy_v2/telegram_bridge/manual_portfolio_trades.csv`

읽어도 되는 입력:

- `output/strategy_v2/*.csv`
- `output/strategy_v2/*.json`
- `output/strategy_v2/telegram_bridge/*`

직접 수정하면 안 되는 영역:

- `new_strategy/ma_breakout_research/`
- `new_strategy/ma_window_research/`
- `new_strategy/compare_strategy_with_optimal_ma.py`
- `new_strategy/compare_optimal_ma_scope.py`

### 2. Live Strategy / Dashboard / Signal Engine

주요 코드:

- `new_strategy/earnings_signal_engine.py`
- `new_strategy/strategy_rules.py`
- `new_strategy/run_signal_pipeline.py`
- `new_strategy/refresh_runtime_data.py`
- `new_strategy/run_market_schedule_service.py`
- `new_strategy/run_background_refresh_service.ps1`
- `new_strategy/streamlit_app.py`
- `new_strategy/optimal_ma_overlay.py`

주요 출력 경로:

- `output/strategy_v2/`
- `output/strategy_v2/signal_daily*.csv`
- `output/strategy_v2/decision_report*.csv`
- `output/strategy_v2/strategy_metadata.json`
- `output/strategy_v2/fast_alert_metadata.json`

허용되는 연구 입력:

- `output/ma_breakout_research/` 아래의 확정 산출물

주의:

- `new_strategy/optimal_ma_overlay.py`는 이제
  `output/ma_breakout_research/published/optimal_ma_selection_monthly_weekly.csv`
  를 우선 읽는다.
- raw 파일 직접 읽기는 publish 파일이 없을 때만 안전 fallback으로 남겨둔다.
- 즉 `L1`과 `M1`의 기본 연결은 publish 계층으로 옮겼고, 다음 단계는 raw fallback 제거 여부 결정이다.

### 3. MA Breakout Simulation / Research

주요 코드:

- `new_strategy/ma_breakout_research/backtest_ma_breakout_modes.py`
- `new_strategy/ma_breakout_research/build_strategy_ma_selection.py`
- `new_strategy/ma_window_research/analyze_optimal_ma_windows.py`
- `new_strategy/ma_window_research/render_stock_ma_chart.py`
- `new_strategy/compare_strategy_with_optimal_ma.py`
- `new_strategy/compare_optimal_ma_scope.py`

관련 문서:

- `new_strategy/docs/SESSION_2026-03-16_ma_breakout_simulation.md`
- `new_strategy/docs/MA_BREAKOUT_SIMULATION_DELIVERABLES.md`
- `new_strategy/docs/REDO_PREVIOUS_TASK_ma_breakout_prompt.txt`

주요 출력 경로:

- `output/ma_breakout_research/`
- `output/strategy_compare/`
- `output/strategy_compare_optimal_ma/`
- `output/strategy_compare_optimal_ma_scope/`

직접 수정하면 안 되는 영역:

- `new_strategy/telegram_bridge_*.py`
- `new_strategy/telegram_helper.py`
- `output/strategy_v2/telegram_bridge/`

## 병렬 진행 단위

### Track T1. Telegram Bridge 개선

목적:

- 텔레그램 질의/응답, 운영 알림, 수동 체결 입력, 실체결 검증 연결

코드 소유 범위:

- `telegram_bridge_*.py`
- `telegram_helper.py`

문서 소유 범위:

- `docs/TELEGRAM_BRIDGE_2026-03-16_ACTION_LOG.md`

출력 소유 범위:

- `output/strategy_v2/telegram_bridge/`

금지:

- MA 시뮬레이션 연구 코드 수정
- 연구 산출물 재생성

### Track L1. Live Strategy / Dashboard

목적:

- 실운영 전략, fast alert, 대시보드, 전략 메타데이터, 라이브 표시

코드 소유 범위:

- `earnings_signal_engine.py`
- `run_signal_pipeline.py`
- `refresh_runtime_data.py`
- `streamlit_app.py`
- `optimal_ma_overlay.py`

문서 소유 범위:

- 전략 운영 문서
- 대시보드 UI 변경 메모

출력 소유 범위:

- `output/strategy_v2/`

금지:

- 텔레그램 브리지 라우팅/명령 체계 수정
- MA 백테스트 원본 생성 로직 수정

### Track M1. MA Breakout Simulation / Research

목적:

- MA 조건 탐색
- 종목별 최적 조건 선정
- 전략 비교 평가

코드 소유 범위:

- `ma_breakout_research/`
- `ma_window_research/`
- `compare_strategy_with_optimal_ma.py`
- `compare_optimal_ma_scope.py`

문서 소유 범위:

- `SESSION_2026-03-16_ma_breakout_simulation.md`
- `MA_BREAKOUT_SIMULATION_DELIVERABLES.md`
- `REDO_PREVIOUS_TASK_ma_breakout_prompt.txt`

출력 소유 범위:

- `output/ma_breakout_research/`
- `output/strategy_compare*/`

금지:

- 텔레그램 브리지 응답 체계 수정
- 라이브 전략 실행 파일 직접 수정

## 현재 코드베이스 기준 권장 인터페이스

### A. T1 -> L1

허용:

- `T1`은 `L1`이 만든 최신 결과 파일만 읽는다.
- 예:
  - `signal_daily_fast_latest.csv`
  - `decision_report_fast_latest.csv`
  - `strategy_metadata.json`

금지:

- `T1`이 `M1`의 원시 CSV를 직접 읽어 해석하는 것

### B. M1 -> L1

허용:

- `M1`은 평가/선정 결과를 파일로 publish 한다.
- `L1`은 그 publish 결과만 읽는다.

권장 publish 산출물:

- `output/ma_breakout_research/published/optimal_ma_selection_monthly_weekly.csv`
- `output/ma_breakout_research/published/optimal_ma_readme.md`

현재 상태:

- `L1`은 publish 파일을 기본 입력으로 사용한다.
- raw 파일 직접 읽기는 예외 fallback으로만 남아 있다.

## 우선순위

### P0. 경계 유지

- `T1`과 `M1`의 직접 연결 금지
- `L1`만 `M1` 산출물 사용

### P1. 라이브 안정성

- `output/strategy_v2/` 경로 안정 유지
- Streamlit, signal pipeline, schedule service는 기존 출력 경로 유지

### P2. 연구 독립성

- `M1`은 언제든 별도 반복 실행 가능해야 한다.
- 연구 결과가 라이브를 자동으로 덮어쓰지 않게 한다.

### P3. publish 단계 추가

- `M1 raw`와 `L1 consumption` 사이에 publish 산출물 계층을 둔다.

## 실행 순서 제안

### 순서 1. T1과 M1의 독립 유지

- 텔레그램 브리지 관련 수정은 `telegram_bridge_*` 범위에서만 진행
- MA 시뮬레이션 관련 수정은 `ma_breakout_research/`, `compare_*` 범위에서만 진행

### 순서 2. M1에서 평가 확정

- `all_action_modes_returns_by_stock.csv` 기반 평가
- 최적 월/주 MA 선정
- 평가 결과 문서화

### 순서 3. M1 publish 산출물 고정

- 라이브 소비용 파일을 별도로 생성
- raw 연구 파일과 분리

### 순서 4. L1에서 publish 결과만 반영

- `optimal_ma_overlay.py`가 publish 산출물만 읽도록 전환
- Streamlit/Signal Engine에 반영

### 순서 5. T1은 L1 결과만 노출

- 텔레그램은 전략 결과와 운영 메시지만 노출
- MA 연구 로직이나 연구 CSV 해석은 하지 않음

## 바로 병렬 진행 가능한 작업 세트

### 세트 A: Telegram Bridge

- `/latest`, 종목 상세, 수동 체결, 실체결 검증
- 작업 파일:
  - `telegram_bridge_tools.py`
  - `telegram_bridge_router.py`
  - `telegram_bridge_portfolio.py`

### 세트 B: MA Simulation

- 월/주 최적 MA 평가
- 기존전략 vs 보조지표 평가
- publish 산출물 정의
- 작업 파일:
  - `compare_strategy_with_optimal_ma.py`
  - `compare_optimal_ma_scope.py`
  - `ma_breakout_research/*`

### 세트 C: Dashboard / Live Integration

- 대시보드 표시
- 실행 로직 소프트 반영
- publish 파일만 읽는 overlay
- 작업 파일:
  - `streamlit_app.py`
  - `optimal_ma_overlay.py`
  - `earnings_signal_engine.py`

## 현재 기준 권장 다음 액션

1. `M1 publish 산출물` 포맷을 먼저 확정한다.
2. `L1 optimal_ma_overlay.py`를 raw 파일 직접 읽기에서 publish 파일 읽기로 바꾼다.
3. `T1`은 계속 `output/strategy_v2/`만 읽게 유지한다.

이 순서가 가장 안전하다.
