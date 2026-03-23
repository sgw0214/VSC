# Optimal MA Publish Schema

Scope: `M1 -> L1` handoff only.

This schema defines the published contract for:

- `output/ma_breakout_research/published/optimal_ma_selection_monthly_weekly.csv`
- `output/ma_breakout_research/published/optimal_ma_selection_monthly_weekly_meta.json`

`L1` live strategy and dashboard code may consume this publish output.
`T1` telegram bridge must not read raw MA research outputs directly.

## Schema Version

- `optimal_ma_monthly_weekly_v2`

## CSV Contract

Required columns:

1. `code`
2. `name`
3. `ma_timeframe`
4. `action_mode`
5. `ma_window`
6. `total_return`
7. `buy_hold_return`
8. `excess_return`
9. `annualized_return`
10. `max_drawdown`
11. `win_rate`
12. `completed_trade_count`
13. `trade_count`
14. `exposure_ratio`
15. `selection_scope`
16. `published_source`

Constraints:

- `code`
  - 6-character alphanumeric string
  - leading zero preserved where applicable
  - preferred-share codes with trailing letters are allowed
- `ma_timeframe`
  - one of: `monthly`, `weekly`
- `action_mode`
  - one of: `native_timeframe_close`, `daily_close_action`
- `selection_scope`
  - fixed value: `monthly_weekly`
- one row per `code`

Ranking rule used to produce the file:

Pre-filter:

- exclude `ma_window = 1`

Ranking rule used to produce the file:

1. `total_return`
2. `max_drawdown`
3. `completed_trade_count`
4. `annualized_return`
5. `win_rate`
6. `action_mode_priority`
7. `timeframe_priority`
8. `ma_window`

Tie-break intent:

- prefer `native_timeframe_close`
- prefer `monthly` over `weekly`
- prefer shorter window if still tied

## Meta JSON Contract

Required keys:

1. `published_at`
2. `schema_version`
3. `source_path`
4. `selection_path`
5. `selection_scope`
6. `row_count`
7. `stock_count`
8. `selection_rule`

Constraints:

- `schema_version` must equal `optimal_ma_monthly_weekly_v2`
- `selection_scope` must equal `monthly_weekly`

## Ownership

- `M1` owns generation and validation of this publish file.
- `L1` owns consumption only.
- Any schema change requires:
  1. new schema version
  2. publish script update
  3. consumer update in `L1`

## Validation

Validation script:

- `new_strategy/ma_breakout_research/validate_optimal_ma_publish.py`

Recommended sequence:

1. publish file
2. validate file
3. only then allow `L1` to consume the result
