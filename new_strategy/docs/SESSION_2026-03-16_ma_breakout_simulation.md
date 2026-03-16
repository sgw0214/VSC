# Session 2026-03-16 MA Breakout Simulation

## Scope

This handoff is limited to the moving-average breakout simulation work.
It does not cover dashboard, telegram, DART, macro, or live execution topics.

## Paths

- Code root: `E:\VSC\CODE\new_strategy`
- Simulation code folder: `E:\VSC\CODE\new_strategy\ma_breakout_research`
- Output root: `C:\Users\sgw02\OneDrive\python\new_strategy\output`
- MA breakout output folder: `C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research`

## Existing Simulation Code

- `new_strategy/ma_breakout_research/backtest_ma_breakout_modes.py`
  - backtests MA breakout returns by stock
  - supports `native_timeframe_close` and `daily_close_action`
- `new_strategy/ma_breakout_research/build_strategy_ma_selection.py`
  - builds a strategy-ready selection table from prior simulation outputs
  - the current version was based on a global safe-window concept
- `new_strategy/ma_window_research/analyze_optimal_ma_windows.py`
  - close-to-MA tracking error study
- `new_strategy/ma_window_research/render_stock_ma_chart.py`
  - single-stock MA chart renderer

## Existing Simulation Outputs

From `output/ma_breakout_research/`:

- `native_timeframe_close_returns_by_stock.csv`
- `daily_close_action_returns_by_stock.csv`
- `all_action_modes_returns_by_stock.csv`
  - new combined raw table
  - concatenates the two files above
  - preserves `action_mode` so downstream work can rank across both modes directly
- `best_window_by_stock.csv`
- `best_window_distribution.csv`
- `summary_report.md`
- `run_meta.json`

## Current Backtest Rule

- Signal rule:
  - buy when `close > moving average`
  - sell when `close <= moving average`
- Position assumption:
  - decision is made at close
  - position is applied from the next bar
- Native mode:
  - monthly MA trades at month-end close
  - weekly MA trades at week-end close
  - daily MA trades at daily close
- Daily-close mode:
  - monthly/weekly/daily MA conditions are evaluated at each daily close
  - weekly/monthly MA values are derived from the latest completed weekly/monthly bar and forward-filled

## Important Findings From The Conversation

- `best_window_distribution.csv` is a summary table, not the right base for final per-stock ranking.
- `stock_count` in that table means:
  - the number of stocks for which that window was the best result
  - within a given `action_mode + ma_timeframe`
- `stock_share` is therefore:
  - the share of best-window winners within that grouped universe
  - not a direct safe-stock ratio
- A reviewed user-added safety column exists in `best_window_distribution.csv`, but it reflects grouped behavior, not stock-level behavior.
- The previously built `ma_breakout_strategy_selection` outputs used global safe windows only.
  - That approach ended up labeling all selected stocks as safe candidates.
  - That result should be treated as an intermediate experiment, not the final stock-level logic.

## Current Preferred Data Source

If the next task is to choose the best condition per stock, use:

- `C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\all_action_modes_returns_by_stock.csv`

Why:

- it is the raw per-stock result table
- it already contains both action modes
- it already contains monthly, weekly, and daily MA runs
- it avoids over-relying on summary tables

## What The Combined Raw Table Contains

Columns include:

- `code`
- `name`
- `ma_timeframe`
- `action_mode`
- `ma_window`
- `test_start`
- `test_end`
- `bars`
- `total_return`
- `buy_hold_return`
- `excess_return`
- `annualized_return`
- `max_drawdown`
- `trade_count`
- `completed_trade_count`
- `win_rate`
- `exposure_ratio`

## Recommended Selection Direction For The Next Task

If the user asks for a direct best-condition table, the simplest logic is:

1. load `all_action_modes_returns_by_stock.csv`
2. compare all rows per stock across:
   - `action_mode`: `native_timeframe_close`, `daily_close_action`
   - `ma_timeframe`: `monthly`, `weekly`, `daily`
   - `ma_window`: available tested windows
3. select the highest-performing row per stock based on the metric the user requests
4. use tie-breakers explicitly if needed

This is different from the earlier safe-window summary approach.

## Constraint

- Keep future outputs separated from the live strategy until the user explicitly requests strategy integration.
- Do not modify dashboard, telegram, or live execution logic unless asked.
