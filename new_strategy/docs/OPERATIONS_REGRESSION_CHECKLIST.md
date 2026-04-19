# Operations Regression Checklist

이 문서는 `new_strategy`의 **기존 운영 기능이 빠지지 않았는지** 확인하기 위한 기준 문서다.

원칙
- 새 기능보다 기존 운영 기능의 연결 상태를 우선 확인한다.
- 문서/운영 스케줄/브리지/대시보드가 서로 다른 말을 하면 코드 기준으로 다시 맞춘다.
- 변경 후에는 아래 체크리스트를 순서대로 확인한다.

## 1. 운영 기능 목록

### 1. 프리장 대응 메시지
- 목적: 장 시작 전 실행형 fast 기준 요약 발송
- 시간: `08:20 ~ 08:25`
- 코드:
  - `new_strategy/telegram_bridge_service.py`
    - `EARLY_SESSION_WINDOWS`
    - `_maybe_send_early_session_brief(...)`
  - `new_strategy/telegram_bridge_tools.py`
    - `early_session_brief_text(...)`
- 데이터 기준:
  - 장중이면 `signal_daily_fast_latest.csv`
- 확인 로그:
  - `output/strategy_v2/telegram_bridge/telegram_bridge_message_log.csv`
  - `tool_name = scheduled_early_session_brief`
  - `scheduled_briefs`에 `YYYY-MM-DD:preopen_1`

### 2. 본장 대응 메시지
- 목적: 장 시작 후 최신 fast 기준 실행형 요약 발송
- 시간: `09:20 ~ 09:25`
- 코드:
  - `new_strategy/telegram_bridge_service.py`
    - `EARLY_SESSION_WINDOWS`
    - `_maybe_send_early_session_brief(...)`
  - `new_strategy/telegram_bridge_tools.py`
    - `early_session_brief_text(...)`
- 데이터 기준:
  - 장중이면 `signal_daily_fast_latest.csv`
- 확인 로그:
  - `tool_name = scheduled_early_session_brief`
  - `scheduled_briefs`에 `YYYY-MM-DD:regular_open_1`

### 3. 장중 30분 fast 재계산
- 목적: 전종목 키움 현재가 기준 fast 재계산
- 시간:
  - 시작 `08:10`
  - 종료 `20:00`
  - 간격 `30분`
- 코드:
  - `new_strategy/run_market_schedule_service.py`
    - `_run_intraday_full_refresh_fast_alert()`
    - `_intraday_slot_key(...)`
- 명령:
  - `python -m new_strategy.run_signal_pipeline --refresh-data --prefer-kiwoom-eod --send-alerts --fast-alerts --live-quotes ...`
- 확인 파일:
  - `output/strategy_v2/market_schedule_state.json`
    - `last_intraday_slot`
  - `output/strategy_v2/fast_alert_metadata.json`

### 4. 장후 EOD 갱신
- 목적: 장 종료 후 키움 EOD 전체 갱신
- 시간: `20:10`
- 코드:
  - `new_strategy/run_market_schedule_service.py`
    - `_run_eod_refresh_summary()`
- 명령:
  - `python -m new_strategy.run_signal_pipeline --refresh-data --prefer-kiwoom-eod --send-alerts`
- 확인 파일:
  - `output/strategy_v2/refresh_runtime_metadata.json`
    - `price_after`
    - `stock_refresh_source`
  - `output/strategy_v2/strategy_metadata.json`
    - `latest_signal_date`

### 5. 장후 요약 메시지
- 목적: 장후 `latest/full` 기준 익일 의사결정 요약
- 시간: `20:10 이후`, 당일 `latest/full`이 준비된 뒤 1회
- 코드:
  - `new_strategy/telegram_bridge_service.py`
    - `_maybe_send_postclose_summary(...)`
  - `new_strategy/telegram_bridge_tools.py`
    - `postclose_summary_text(...)`
- 데이터 기준:
  - `signal_daily_latest.csv`
  - `decision_report_daily.csv`
- 출력 형식:
  - `익일매수`
  - `익일관심유지`
  - `익일비중축소검토`
  - `익일매도`
- 확인 로그:
  - `tool_name = scheduled_postclose_summary`
  - `scheduled_briefs`에 `YYYY-MM-DD:postclose_summary`

### 6. 다음날 KRX 재보정
- 목적: 전일 KRX raw 보정
- 시간: `07:00`
- 코드:
  - `new_strategy/run_market_schedule_service.py`
    - `_run_krx_reconcile()`
- 명령:
  - `python -m new_strategy.run_signal_pipeline --refresh-data`
- 확인 파일:
  - `output/strategy_v2/market_schedule_state.json`
    - `last_krx_reconcile_date`

### 7. 텔레그램 최신 상태 조회
- 명령:
  - `/latest`
  - `/status`
  - 종목 상세 (`삼성전자 정보`, `005930 정보`)
- 코드:
  - `new_strategy/telegram_bridge_tools.py`
    - `latest_signals_text(...)`
    - `latest_status_text(...)`
    - `signal_detail_text(...)`
- 기준:
  - 장중: `fast-only`
  - 장후: `latest/full` 허용

### 8. 실체결 입력 / 실보유 반영
- 명령 예시:
  - `매수 덴티움 51800원 1주`
  - `매도 덴티움 49800원 1주`
- 코드:
  - `new_strategy/telegram_bridge_portfolio.py`
  - `new_strategy/telegram_bridge_tools.py`
  - `new_strategy/streamlit_app.py`
- 확인 파일:
  - `output/strategy_v2/telegram_bridge/manual_portfolio_trades.csv`
  - `output/strategy_v2/telegram_bridge/manual_portfolio_positions.csv`

### 9. 기록 저장
- 입력 형식:
  - `기록_...`
  - `기록]...`
  - `기록:...`
  - `기록 ...`
- 코드:
  - `new_strategy/telegram_bridge_router.py`
  - `new_strategy/telegram_bridge_service.py`
- 확인 파일:
  - `output/strategy_v2/telegram_bridge/telegram_bridge_notes.csv`

## 2. 변경 후 최소 회귀검증

아래는 코드 변경 후 항상 돌린다.

### A. 정적 확인
- `python -m py_compile new_strategy/telegram_bridge_tools.py new_strategy/telegram_bridge_service.py new_strategy/run_market_schedule_service.py new_strategy/streamlit_app.py`
- `python -m new_strategy.verify_operational_contract`

### B. 출력 생성 확인
- `postclose_summary_text('8771118338')`가 당일 latest/full 기준 텍스트를 생성하는지
- `early_session_brief_text('본장', '8771118338')`가 장중 fast 기준으로 생성되는지

### C. 로그 확인
- `telegram_bridge_message_log.csv`
  - `scheduled_early_session_brief`
  - `scheduled_postclose_summary`
- `telegram_bridge_state.json`
  - `last_early_session_brief_at`
  - `last_postclose_summary_at`
- `market_schedule_state.json`
  - `last_intraday_slot`
  - `last_eod_date`
  - `last_krx_reconcile_date`

## 3. 자주 빠지는 항목

아래는 실제로 누락이 있었던 항목이다.

- 문서에는 있는데 스케줄 구현이 없는 경우
  - 예: 장후 요약
- 장중/장후 데이터 기준이 섞이는 경우
  - 예: 장중에 latest/full을 읽어서 fast와 충돌
- 텔레그램 브리프와 개별 알림 기준이 다른 경우
  - 예: 한 종목에 BUY/SELL 중복 신호
- 실보유 파일이 바뀌었는데 대시보드 캐시가 안 깨지는 경우
- 스케줄 작업 실패가 전체 서비스 중단으로 이어지는 경우

## 4. 작업 원칙

- 기존 운영 기능은 "있어야 한다"가 아니라 **코드/로그로 확인**해야 한다.
- 사용자가 이미 기대하고 있는 운영 기능은 문서가 아니라 **회귀검증 대상**으로 취급한다.
- 빠진 기능을 추가할 때는 같은 카테고리 기능 전체를 다시 확인한다.
