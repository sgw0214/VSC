# Trend Lab File Contract (2026-04-11)

## Goal
- Keep trend sensing assets fully isolated from strategy runtime logic.
- Prevent file cleanup mistakes by using fixed path scope + fixed prefix + fixed manifest.

## Isolation Rule
- **Core strategy runtime** stays under existing contracts (`strategy_v2` files used by signal/decision/alerts).
- **Trend lab files** must only use:
  - `data/trend_lab/*`
  - `output/strategy_v2/trend_lab/*`

## Naming Rule
- Every trend file name must start with `trend_`.
- Do not place non-trend files in `trend_lab/`.
- Do not place trend files at `data_root` or `strategy_v2` root directly.

## Canonical File List
Managed by: `new_strategy/trend_file_contract.py`

### Data
- `trend_keyword_taxonomy.csv` (required)
- `trend_keyword_industry_map.csv` (required)
- `trend_keyword_aliases.csv` (optional)
- `trend_unclassified_keywords.csv` (required)

### Output
- `trend_global_snapshot.json` (required)
- `trend_news_mentions_rolling.csv` (required)
- `trend_keyword_daily_scores.csv` (required)
- `trend_keyword_industry_links.csv` (required)
- `trend_holding_exposure.csv` (required)
- `trend_collection_status.csv` (optional)
- `trend_classification_log.csv` (optional)

## Implementation Entry Points
- Path helpers:
  - `new_strategy.paths.trend_data_path(...)`
  - `new_strategy.paths.trend_output_path(...)`
- Contract helpers:
  - `new_strategy.trend_file_contract.trend_file_specs()`
  - `new_strategy.trend_file_contract.resolve_trend_file(key)`
  - `new_strategy.trend_file_contract.ensure_trend_lab_dirs()`

## Cleanup Safety
- In cleanup/inventory scripts, `trend_lab` directory must be treated as `keep` scope by default.
- Any archive action for trend files should only target old snapshots/logs, not taxonomy/mapping contracts.
