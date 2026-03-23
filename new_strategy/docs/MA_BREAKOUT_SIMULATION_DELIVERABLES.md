# MA Breakout Simulation Deliverables

## Code

- [backtest_ma_breakout_modes.py](E:\VSC\CODE\new_strategy\ma_breakout_research\backtest_ma_breakout_modes.py)
- [build_strategy_ma_selection.py](E:\VSC\CODE\new_strategy\ma_breakout_research\build_strategy_ma_selection.py)
- [README.md](E:\VSC\CODE\new_strategy\ma_breakout_research\README.md)
- [analyze_optimal_ma_windows.py](E:\VSC\CODE\new_strategy\ma_window_research\analyze_optimal_ma_windows.py)
- [render_stock_ma_chart.py](E:\VSC\CODE\new_strategy\ma_window_research\render_stock_ma_chart.py)
- [publish_optimal_ma_selection.py](E:\VSC\CODE\new_strategy\ma_breakout_research\publish_optimal_ma_selection.py)
- [validate_optimal_ma_publish.py](E:\VSC\CODE\new_strategy\ma_breakout_research\validate_optimal_ma_publish.py)
- [optimal_ma_publish_contract.py](E:\VSC\CODE\new_strategy\optimal_ma_publish_contract.py)

## Output

- [native_timeframe_close_returns_by_stock.csv](C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\native_timeframe_close_returns_by_stock.csv)
- [daily_close_action_returns_by_stock.csv](C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\daily_close_action_returns_by_stock.csv)
- [all_action_modes_returns_by_stock.csv](C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\all_action_modes_returns_by_stock.csv)
- [best_window_by_stock.csv](C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\best_window_by_stock.csv)
- [best_window_distribution.csv](C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\best_window_distribution.csv)
- [summary_report.md](C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\summary_report.md)
- [run_meta.json](C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\run_meta.json)
- [published/optimal_ma_selection_monthly_weekly.csv](C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\published\optimal_ma_selection_monthly_weekly.csv)
- [published/optimal_ma_selection_monthly_weekly_meta.json](C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\published\optimal_ma_selection_monthly_weekly_meta.json)
- [published/optimal_ma_selection_monthly_weekly.md](C:\Users\sgw02\OneDrive\python\new_strategy\output\ma_breakout_research\published\optimal_ma_selection_monthly_weekly.md)
- [OPTIMAL_MA_PUBLISH_SCHEMA.md](E:\VSC\CODE\new_strategy\docs\OPTIMAL_MA_PUBLISH_SCHEMA.md)

## Handoff Files

- [SESSION_2026-03-16_ma_breakout_simulation.md](E:\VSC\CODE\new_strategy\docs\SESSION_2026-03-16_ma_breakout_simulation.md)
- [REDO_PREVIOUS_TASK_ma_breakout_prompt.txt](E:\VSC\CODE\new_strategy\docs\REDO_PREVIOUS_TASK_ma_breakout_prompt.txt)

## Notes

- The combined raw table is the preferred input when the next task needs direct per-stock ranking across both action modes.
- The live strategy should not read the raw combined table directly. It should read the published monthly/weekly selection file only.
- The published monthly/weekly selection file now has a fixed schema contract:
  - `optimal_ma_monthly_weekly_v1`
  - validate with `validate_optimal_ma_publish.py`
- The prior `ma_breakout_strategy_selection` outputs were built from a global safe-window concept and should be treated as an intermediate experiment.
