# Operations File Map

Date: 2026-03-30

## Goal

This document defines which files are:

- source of truth
- derived operational outputs
- state files
- caches
- research-only artifacts

It also records the current mismatch between dashboard and Telegram postclose briefing.

## 1. Source Of Truth

These files are the canonical inputs for V2 operations.

| Role | File |
| --- | --- |
| Price source | `C:\Users\sgw02\OneDrive\python\new_strategy\price_panel.csv` |
| Feature source | `C:\Users\sgw02\OneDrive\python\new_strategy\feature_daily.csv` |
| Macro source | `C:\Users\sgw02\OneDrive\python\new_strategy\macro_regime_v3_rec.csv` |
| Fundamental source | `C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_multi.csv` |
| Optimal MA contract snapshot | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\optimal_ma_monthly_weekly_snapshot.pkl` |
| Real holdings source | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\telegram_bridge\manual_portfolio_positions.csv` |

Rules:

- Real holdings are defined only by `manual_portfolio_positions.csv`.
- Optimal MA changes only when manually refreshed.
- Daily operations must use new price, macro, and fundamental data against the fixed Optimal MA snapshot.

## 2. Operational Outputs

These files are the latest decision outputs used by UI and messaging.

| Role | File |
| --- | --- |
| Postclose latest signal | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\signal_daily_latest.csv` |
| Fast latest signal | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\signal_daily_fast_latest.csv` |
| Postclose decision report | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\decision_report_daily.csv` |
| Fast decision report | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\decision_report_fast_latest.csv` |
| Dashboard execution snapshot | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\dashboard_operational_execution_snapshot.csv` |
| Dashboard postclose snapshot | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\dashboard_operational_postclose_snapshot.csv` |

Rules:

- Postclose dashboard and postclose Telegram briefing must be based on the same postclose output set.
- Intraday fast dashboard and intraday fast alerts must be based on the same fast output set.
- Telegram premarket/open/fast/postclose must read the dashboard operational snapshot, not re-filter signal files independently.

## 3. State Files

These files track process state. They are not trading inputs.

| Role | File |
| --- | --- |
| Market scheduler state | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\market_schedule_state.json` |
| Telegram bridge state | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\telegram_bridge\telegram_bridge_state.json` |
| Refresh metadata | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\refresh_runtime_metadata.json` |

Rules:

- State files may be displayed in dashboard status panels.
- State files must not be treated as market data or strategy signals.

## 4. Cache And Speed Helpers

These files exist for performance only.

| Role | File |
| --- | --- |
| Latest price snapshot | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\price_panel_latest_snapshot.csv` |
| Latest feature snapshot | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\feature_latest_snapshot.csv` |
| Industry cache | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\price_panel_industry_base.pkl` |

Rules:

- These are derived caches.
- They must never override canonical source files conceptually.

## 5. Internal Engine State

This file is not a source of real holdings.

| Role | File |
| --- | --- |
| Fast engine internal state | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\fast_position_state.csv` |

Rules:

- `fast_position_state.csv` is an engine state file only.
- It must not replace `manual_portfolio_positions.csv`.
- If there is a conflict, `manual_portfolio_positions.csv` wins.

## 6. Research-Only Outputs

These files are not required for daily operations.

| Role | File |
| --- | --- |
| Full trade history | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\trade_log.csv` |
| Equity curve | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\equity_curve.csv` |
| Strategy evaluation | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\strategy_eval.csv` |
| Condition research | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\research_condition_performance.csv` |
| Rule candidate research | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\research_rule_candidates.csv` |

Rules:

- These files must not be on the critical path for operational messaging.
- They may be kept for the Research page only.

## 7. Logs

These files are for audit and debugging.

| Role | File |
| --- | --- |
| Alert log | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\alert_log.csv` |
| Scheduler log | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\background_refresh_service.log` |
| Telegram message log | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\telegram_bridge\telegram_bridge_message_log.csv` |
| Telegram note log | `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\telegram_bridge\telegram_bridge_notes.csv` |

Rules:

- Alert investigations should use `alert_log.csv` first.
- Messaging investigations should use `telegram_bridge_message_log.csv` first.

## 8. Current Mismatch

Current dashboard and Telegram postclose briefing are not using the same final filter.

Dashboard path:

- `E:\VSC\CODE\new_strategy\streamlit_app.py`
- `build_strategy_report_payload()`
- Keeps only:
  - real holdings
  - monthly buy-cross candidates

Telegram postclose path:

- `E:\VSC\CODE\new_strategy\telegram_bridge_tools.py`
- `_postclose_operational_signal_df()`
- Keeps:
  - real holdings
  - `BUY`
  - `BUY_WATCH`
  - `WATCH`

Result:

- Dashboard is narrower.
- Telegram postclose is wider.
- This causes different stock sets on the same day.

## 9. Normalized Operational Rule

Operational screens should follow this rule:

- Dashboard postclose decision view: postclose output + postclose final filter
- Telegram postclose briefing: same postclose output + same postclose final filter
- Dashboard intraday view: fast output + fast final filter
- Telegram intraday fast alert: same fast output + position-change-only rule

## 10. Cleanup Candidates

These files are not harmful, but they are not operationally important.

- `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\alert_log_kakao_legacy.csv`
- `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\data_health_summary (1).json`
- `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\refresh_runtime_metadata (1).json`
- `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\fast_position_state.pre_v2_reset_20260322_014429.csv`
- `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\dashboard_pipeline_runs\`

These should be archived or ignored, not treated as current operational inputs.
