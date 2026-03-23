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

Published for live consumption:

- `published/optimal_ma_selection_monthly_weekly.csv`
- `published/optimal_ma_selection_monthly_weekly_meta.json`
- `published/optimal_ma_selection_monthly_weekly.md`
- schema contract: `new_strategy/docs/OPTIMAL_MA_PUBLISH_SCHEMA.md`
- validation script: `new_strategy/ma_breakout_research/validate_optimal_ma_publish.py`

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
- If live strategy needs MA inputs, publish a dedicated consumption file under `output/ma_breakout_research/published/` and let live code read that file only.
- Published monthly/weekly handoff is now fixed under schema version `optimal_ma_monthly_weekly_v1`.

## 2026-03-17 Overnight Research Extension

A separate non-live research track has been started under:

- `new_strategy/alpha_combo_research/run_return_max_search.py`

Its outputs are isolated under:

- `output/alpha_combo_research/`

This track does not write to `output/strategy_v2/` and does not alter live strategy behavior.

Current first-pass outputs:

- `global_combo_results.csv`
- `industry_best_combos_20d.csv`
- `stock_best_combos_20d.csv`
- `summary.md`
- `meta.json`

Input basis:

- `feature_daily.pkl`
- `price_panel.csv`
- `output/ma_breakout_research/published/optimal_ma_selection_monthly_weekly.csv`

Current scope:

- event window: `days_since_filing <= 90`
- single and pairwise condition search
- dimensions include:
  - industry
  - market cap
  - op margin
  - ret_5
  - ATR ratio
  - dist_ma_mid
  - gold / VIX / USDKRW / US10Y regimes
  - optimal MA timeframe / action mode / window buckets

## 2026-03-17 Robust Phase 2

Added scripts:

- `new_strategy/alpha_combo_research/run_return_max_search_robust.py`
- `new_strategy/alpha_combo_research/build_deployable_shortlist.py`

Additional outputs:

- `output/alpha_combo_research/robust_phase2/global_combo_results_robust.csv`
- `output/alpha_combo_research/robust_phase2/industry_best_combos_20d_robust.csv`
- `output/alpha_combo_research/robust_phase2/stock_best_combos_20d_robust.csv`
- `output/alpha_combo_research/robust_phase2/deployable_global_shortlist.csv`
- `output/alpha_combo_research/robust_phase2/summary.md`
- `output/alpha_combo_research/robust_phase2/deployable_summary.md`

Expanded search dimensions:

- filing windows: `15 / 30 / 60 / 90`
- profitability: operating margin, ROE, QoQ positives
- quality: `quality_score`
- momentum/overheat: `ret_5`, `ret_20`, `ret_60`
- volatility/trend shape: `ATR`, `dist_ma_mid`
- macro: gold, VIX, USDKRW, US10Y, KR10Y and their 60-day MA relations
- optimal MA: timeframe / action mode / window bucket
- single / pairwise / triple combinations

Robust scoring:

- `robust_score = winsor_mean*100 + median*40 + win_rate*8 + p25*20 + p10*10`

Current interpretation:

- Phase 1 raw mean-return ranking over-emphasized `small cap + high VIX`.
- Phase 2 robust ranking shifts the strongest repeatable global patterns toward:
  - `filing within 15 days`
  - `positive or >=5% operating margin`
  - `positive / high ROE`
  - selective `quality_score`

Deployable shortlist filters:

- `horizon_days == 20`
- `obs >= 20,000`
- `median_return >= 0.30%`
- `win_rate >= 52%`
- `p10_return >= -12%`
- `condition_count <= 3`
