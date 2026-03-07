# Walkforward Result Column Guide

File: `new_strategy/output/walkforward_result.csv`

- `test_start_year`: 해당 테스트 구간 시작 연도
- `test_end_year`: 해당 테스트 구간 종료 연도
- `selected_top_n`: 학습 구간에서 선택된 보유 종목 수
- `selected_stop_mode`: 선택된 손절 방식 (`fixed` 또는 `atr`)
- `selected_fixed_stop`: 고정 손절률 (예: `-0.08`은 -8%)
- `selected_atr_mult`: ATR 손절 배수 (atr 모드일 때 유효)
- `cagr`: 연환산 수익률
- `mdd`: 최대 낙폭 (최저 드로다운, 음수)
- `sharpe`: 연환산 샤프지수 (무위험 수익률 0 가정)
- `win_rate`: 일별 수익률 기준 수익일 비율
- `days`: 테스트 구간 내 매매 일수

## Signal-Rebalance Result Columns
File: `new_strategy/output/walkforward_result_signal_top5.csv`

- `max_positions`: 포트폴리오 보유 상한 종목 수 (요청 조건: 5)
- `entry_top_n`: 진입 후보군 상한 순위 (요청 조건: 10)
- `stop_mode`, `fixed_stop`, `atr_mult`: 손절 방식/파라미터
- `cagr`, `mdd`, `sharpe`, `win_rate`, `days`: 성과 지표 (동일 정의)
- Signal log (`*_signals.csv`) 추가 컬럼:
- `signal`: `BUY` / `SELL` / `CANDIDATE`
- `reason`: `entry_signal`, `stop_loss`, `trend_break`, `candidate_only_full_positions` 등
- `detail`: 신호 근거값(rank, exposure, stop_pct, hold_days 등)
  - `SELL` 로그에는 `realized_ret`(실현 수익률)가 포함됩니다.

## Quick Interpretation
- 수익성 우선: `cagr`가 높고 `sharpe`가 높을수록 좋음
- 리스크 우선: `mdd` 절대값이 작을수록 좋음 (예: -0.20이 -0.50보다 우수)
- 안정성 확인: `win_rate` 단독보다 `cagr + mdd + sharpe`를 함께 봐야 함

## Important Trading Assumption
- 현재 백테스트 수익(`daily_return`)은 **당일 종가 진입 -> 다음 거래일 청산(1일 보유)** 가정입니다.
- 따라서 `latest_picks.csv`는 기본적으로 단기 리밸런싱 신호이며, 장기 보유(예: 2026년 1월까지 홀딩) 성과와 직접 동일하지 않습니다.

### Updated
- 신호기반 리밸런싱 백테스트는 고정 홀딩일을 두지 않고, 매수/매도 신호와 매크로 노출에 따라 포지션을 유지/교체합니다.
- 추세 필터 기본값은 `5주/10주/20주`를 일봉으로 근사한 `ma_short(25일)`, `ma_mid(50일)`, `ma_long(100일)`입니다.
- 매수 추세 조건은 `5w > 10w > 20w` + 이평 기울기 양(+)입니다.
- 매도 추세 조건은 `5w`와 `10w`가 동시에 하향 전환(AND)일 때입니다.
- `rank_break` 및 `macro_target_trim` 강제 매도는 제거되었습니다.
- 보유 슬롯이 가득 차면 신규 종목은 `CANDIDATE` 로그로만 기록합니다.
