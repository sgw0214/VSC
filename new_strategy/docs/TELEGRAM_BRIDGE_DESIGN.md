# Telegram Free-Conversation Bridge Design

## 목적
- 텔레그램 봇을 `자유대화형 인터페이스`로 사용한다.
- 사용자는 텔레그램에서 질문하고, 브리지는 질문을 해석해서:
  - 단순 대화 응답
  - 상태 조회
  - 최신 신호 요약
  - 데이터 최신화 실행
  - fast alert 실행
  - 결과 설명
  를 수행한다.
- 기존 `new_strategy`의 코어 파이프라인은 그대로 유지하고, 브리지는 바깥 레이어로 붙인다.

## 핵심 판단
- 완전 자유대화형으로 가더라도 `모든 메시지를 곧바로 쉘 실행`으로 연결하면 안 된다.
- 따라서 v1은 `자유대화 + 제한된 툴 라우팅` 구조로 설계한다.
- 대화는 자유롭게 받되, 실제 시스템 작업은 허용된 작업만 실행한다.

## 목표 범위
### 포함
- 텔레그램 대화 수신
- 대화 이력 유지
- 질문 의도 분류
- 기존 산출물 조회
- 허용된 운영 작업 실행
- 장시간 작업의 비동기 처리
- 텔레그램 응답 전송

### 제외
- 임의 PowerShell 명령 실행
- 파일 수정/삭제 직접 허용
- 자동 주문
- 텔레그램에서 코드 편집

## 아키텍처
### 1. Telegram Poller
- Telegram `getUpdates` polling
- update offset 저장
- 중복 메시지 방지

### 2. Session Store
- 사용자별 대화 히스토리 저장
- 최근 N턴만 유지
- 긴 로그는 요약본만 저장

### 3. Intent Router
- 메시지를 아래 중 하나로 분류
  - `chat`
  - `status_query`
  - `signal_query`
  - `run_fast_alert`
  - `run_refresh`
  - `show_latest_report`
  - `show_help`
  - `confirm_job`
  - `reject_job`
- 자유대화는 모델 응답으로 처리
- 시스템 작업은 허용된 툴로만 라우팅

### 4. Tool Adapters
- 로컬 함수/스크립트에 대한 안전한 어댑터 계층
- 직접 호출 대상
  - `run_signal_pipeline`
  - `run_strategy_service`
  - CSV/JSON 읽기
  - 최신 신호/결정 보고서 조회
- 각 어댑터는:
  - 입력 파라미터 검증
  - 타임아웃
  - stdout/stderr 캡처
  - 성공/실패 표준 응답
  를 공통 처리

### 5. Job Runner
- 오래 걸리는 작업은 백그라운드 job으로 실행
- 예:
  - `--refresh-data`
  - `--refresh-macro`
  - 전체 파이프라인 재실행
- 텔레그램에는 즉시:
  - 접수 메시지
  - job_id
  를 보내고
- 완료 시 별도 후속 메시지 발송

### 6. Response Composer
- 텍스트 응답을 텔레그램용으로 정리
- 길면:
  - 상단 요약
  - 하단 핵심 수치 3~5개
- 너무 긴 표는 그대로 보내지 않고 요약

### 7. Audit Log
- 모든 입력/출력과 실행 작업을 저장
- 파일 예:
  - `telegram_bridge_message_log.csv`
  - `telegram_bridge_job_log.csv`
  - `telegram_bridge_state.json`

## 데이터 흐름
1. 사용자가 봇에 메시지 전송
2. Poller가 `getUpdates`로 수신
3. 허용 chat_id인지 확인
4. Session Store에서 최근 대화 이력 로드
5. Intent Router가 질문 의도 분류
6. 분기
   - 조회성 질문:
     - 로컬 데이터 조회
     - 요약 응답
   - 일반 대화:
     - 모델에 질문 전달
     - 응답 생성
   - 실행 작업:
     - Safety Gate 통과
     - Job Runner 실행
     - 접수/완료 메시지 발송
7. Audit Log 저장
8. offset 업데이트

## 대화 모드 설계
### A. 단순 대화
예시:
- "현재 전략 성과 어때?"
- "오늘 신호 왜 이렇게 나왔어?"
- "risk_off가 무슨 뜻이야?"

처리:
- 모델이 대답
- 필요 시 최신 CSV/JSON을 읽어서 근거를 넣음

### B. 조회형 질문
예시:
- "오늘 매수 후보 보여줘"
- "최근 알림 다시 보여줘"
- "최신 데이터 날짜 알려줘"

처리:
- 모델 호출 없이 로컬 조회만 수행 가능
- 토큰 절약용으로 우선 로컬 조회

### C. 실행형 질문
예시:
- "주가 데이터 최신화해줘"
- "fast alert 다시 돌려줘"
- "매크로까지 포함해서 전체 재실행해줘"

처리:
- 모델이 실행 의도임을 인식
- Safety Gate에서 허용 작업인지 판단
- 위험 작업이면 확인 단계 요구

## Safety Gate
### 바로 실행 허용
- 최신 상태 조회
- 최근 신호 조회
- 최근 알림 조회
- 로그/리포트 요약
- fast alert 실행

### 확인 후 실행
- 주가 최신화
- 매크로 최신화
- 전체 파이프라인 재실행
- 텔레그램 알림 재발송

### 금지
- 임의 명령 실행
- 임의 파일 삭제
- git push/pull/checkout
- 전략 코드 수정

## 확인(Confirmation) 방식
- 사용자가 실행형 질문을 하면:
  - 브리지가 job preview를 생성
  - 예:
    - "주가 최신화 + fast alert를 실행하려고 합니다. 계속할까요?"
    - `confirm 1024`
- 사용자가:
  - `confirm 1024`
  - 또는 `/confirm 1024`
  를 보내야 실제 실행
- 텔레그램 자유대화형이라도 위험 작업은 이 단계를 둔다

## 모델 사용 전략
### 왜 완전 자유대화만으로 안 가는가
- 상태 질의는 로컬 조회가 더 빠르고 싸다
- 긴 로그/표를 모델에 그대로 넣으면 토큰 낭비가 크다
- 실행형 작업은 명시적 라우팅이 안전하다

### 실제 운영 방식
- `query-first`
  - 상태/신호/로그는 로컬 코드 우선
- `model-second`
  - 해석이 필요할 때만 모델 사용
- `tool-augmented`
  - 모델이 직접 데이터를 알지 못하므로, 브리지가 필요한 데이터만 요약해서 제공

## 토큰 사용 최소화 전략
1. 대화 이력은 최근 N턴만 유지
2. 긴 CSV는 넣지 않고 요약 통계만 전달
3. 조회형은 모델 호출 없이 처리
4. 시스템 프롬프트는 짧고 고정
5. 종목별 설명은 최대 3개 근거만 포함

## 세션 메모리 설계
- 사용자별 파일 또는 SQLite 테이블
- 저장 항목:
  - `chat_id`
  - `role`
  - `message`
  - `created_at`
  - `intent`
  - `job_id`
- 유지 정책:
  - 최근 20턴 유지
  - 오래된 대화는 요약문으로 치환

## 명령/질문 예시
### 자유질문
- "지금 시장 상태 어때?"
- "오늘 왜 BUY가 안 나왔어?"
- "SK하이닉스는 왜 HOLD야?"

### 조회형
- "/status"
- "/latest"
- "/alerts"
- "/health"

### 실행형
- "fast alert 다시 돌려줘"
- "주가 최신화하고 텔레그램 알림 보내줘"
- "매크로까지 다시 받아서 전체 돌려줘"

## 응답 형식 예시
### 상태 요약
- 최신 신호일: `2026-03-10`
- 시장 레짐: `risk_off`
- BUY `0`, SELL `0`, HOLD `8`, WATCH `7`
- 최신 주가 데이터: `2026-03-10`

### 종목 설명
- `000660 SK하이닉스`
- 신호: `HOLD`
- 점수: `0.999`
- 근거:
  - 영업이익률 `46.6%`
  - 순이익률 `51.5%`
  - 영업이익 QoQ `3.94조`

### 작업 접수
- "요청을 접수했습니다."
- "job_id=1042"
- "예상 소요: 1~3분"

### 작업 완료
- "최신화 완료"
- "price_panel 최신일: 2026-03-10"
- "feature_daily 최신일: 2026-03-10"
- "알림 발송: 3건"

## 운영 프로세스
### 서비스 1: 전략 엔진
- 기존 `run_strategy_service`
- 데이터 최신화 + 알림

### 서비스 2: 텔레그램 브리지
- 새 프로세스
- polling loop
- 질문 응답/작업 접수

### 분리 이유
- 전략 엔진 장애와 대화 인터페이스 장애를 분리
- 브리지 재시작이 파이프라인을 깨지 않게 함

## 파일 구성 제안
- `new_strategy/telegram_bridge_service.py`
  - 메인 루프
- `new_strategy/telegram_bridge_router.py`
  - intent 분류
- `new_strategy/telegram_bridge_tools.py`
  - 상태 조회/실행 어댑터
- `new_strategy/telegram_bridge_memory.py`
  - 세션 저장
- `new_strategy/telegram_bridge_models.py`
  - OpenAI 호출 래퍼
- `new_strategy/telegram_bridge_config.py`
  - 허용 chat_id, polling 간격, 토큰 제한 등

## 환경변수
- `NEW_STRATEGY_TELEGRAM_BOT_TOKEN`
- `NEW_STRATEGY_TELEGRAM_CHAT_ID`
- `OPENAI_API_KEY`
- `NEW_STRATEGY_TELEGRAM_BRIDGE_MODEL`
- `NEW_STRATEGY_TELEGRAM_BRIDGE_ALLOWED_CHAT_IDS`
- `NEW_STRATEGY_TELEGRAM_BRIDGE_POLL_SECONDS`
- `NEW_STRATEGY_TELEGRAM_BRIDGE_HISTORY_TURNS`

## 보안 원칙
1. 허용된 chat_id만 수신
2. 실행형 작업은 allowlist만 허용
3. 위험 작업은 확인 단계 필수
4. API 키는 파일이 아니라 환경변수
5. 모든 실행은 로그로 남김

## 단계별 구현 권장
### 1단계
- polling
- `/status`, `/latest`, `/health`
- 모델 없이 로컬 조회만

### 2단계
- 자유대화 응답
- 최근 대화 이력 유지
- 종목/전략 설명

### 3단계
- `fast alert` 실행
- 최신화 작업 접수/완료 메시지

### 4단계
- 확인 기반 위험 작업
- 장시간 job 관리

## 최종 판단
- 자유대화형 브리지는 가능하다.
- 다만 실제 운영은 `자유대화 + 안전한 도구 라우팅 + 확인 단계` 구조가 맞다.
- 지금 `new_strategy`에는 이 브리지를 `외부 레이어`로 붙이는 방식이 가장 합리적이다.
