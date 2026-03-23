# Strategy V2 Final 2026-03-21

## 1. 기본 전략
- 기준 전략은 `월봉매수 / 주봉매도`이다.
- 기본 파라미터는 `buy_0%__sell_-5%`이다.
- 매수:
  - 종목별 `최적 월이평선` 기준 `0% 이상`
- 매도:
  - 종목별 `최적 주이평선` 기준 `-5% 이탈`

## 2. 축 역할
- `최적 MA`: 메인 축
  - 방향, 진입, 청산 기준
- `주가 위치`: 보조 축
  - 과열, 추격, 분할 진입 강도 조절
- `매크로`: 보조 축
  - 시장 상태와 운용 강도 조절
- `재무`: 보조 축
  - 수익성, 성장성, 지속성, 안정성 해석과 통과 여부 판단

## 3. 매크로 기준
- 입력 변수는 `USD/KRW`, `VIX`만 사용한다.
- 상태 구분:
  - `risk_on` -> `정상구간`
  - `neutral` -> `주의구간`
  - `risk_off` -> `방어구간`
- 운용강도:
  - `정상구간`: `1.0`
  - `주의구간`: `0.7`
  - `방어구간`: `0.4`
- 원칙:
  - 매크로는 종목의 매력을 부정하는 축이 아니다.
  - 매크로는 같은 종목이라도 얼마나 조심해서 들어갈지 정하는 축이다.
  - 매크로만으로 `SELL`을 만들지 않는다.

## 4. 운영 스케줄
- `07:00`
  - KRX 보조 데이터 갱신
- `08:20 ~ 08:25`
  - 프리장 1차 대응 메시지
  - `08:10` 슬롯 결과 기준
- `09:20 ~ 09:25`
  - 본장 2차 대응 메시지
  - `09:10` 슬롯 결과 기준
- `08:10`부터 30분마다
  - 전종목 Kiwoom 갱신
  - fast 계산
  - 변화 종목 알림
- `20:10`
  - 장후 EOD 수집
  - 마감 요약 메시지

## 5. 시스템 원칙
- 장중 fast는 상시 실시간 시세수집을 기본으로 쓰지 않는다.
- 기본 fast 경로는 `08:10부터 30분 전종목 Kiwoom 갱신`이다.
- `live_quotes`는 잔존 파일 또는 옵션성 보조 데이터로만 본다.
- 데이터가 없으면 기본값으로 대체하지 않고 `없음`으로 표시한다.

## 6. 코드 반영 대상
- [earnings_signal_engine.py](E:\VSC\CODE\new_strategy\earnings_signal_engine.py)
- [run_signal_pipeline.py](E:\VSC\CODE\new_strategy\run_signal_pipeline.py)
- [macro_pipeline.py](E:\VSC\CODE\new_strategy\macro_pipeline.py)
- [run_market_schedule_service.py](E:\VSC\CODE\new_strategy\run_market_schedule_service.py)
- [streamlit_app.py](E:\VSC\CODE\new_strategy\streamlit_app.py)
- [telegram_bridge_service.py](E:\VSC\CODE\new_strategy\telegram_bridge_service.py)

## 7. 현재 반영 상태
- `strategy_id = earnings_pti_v2`
- `trend_mode = optimal_ma_v2`
- `monthly_buy_threshold = 0.0`
- `weekly_sell_threshold = -0.05`
- fast 운영 기준:
  - `07:00 / KRX 보조 데이터 갱신`
  - `08:10부터 / 30분 전종목 갱신`
- 장후 운영 기준:
  - `20:10 / EOD 수집 + 마감 요약`
