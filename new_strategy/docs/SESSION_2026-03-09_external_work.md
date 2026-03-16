# Session 2026-03-09

## Paths

- Code: `C:\Users\sgw02\python\new_strategy`
- Data/output: `C:\Users\sgw02\Desktop\data\python\new_strategy`
- External data: `C:\Users\sgw02\Desktop\data\python\new_strategy\external`

## Strategy context

- Recent analysis focus was `stock_quarterly_relationship_summary.csv`
- User is exploring how to improve correlation using:
  - earnings-based relationships
  - pre-pricing / leading behavior
  - external indicators by industry
- User does **not** want speculative or invented data
- Fact-based collection only

## Key decisions

- Raw data and outputs should be stored under desktop `new_strategy`
- Code remains under `C:\Users\sgw02\python\new_strategy`
- Existing macro data should be reused where possible
- Indicators not tied to one industry should be treated as common macro indicators
- External indicators should be managed under `new_strategy/external/`
- Analysis rerun will happen later, after more data is collected and validated

## Files created or updated

### In desktop data folder

- `common_macro_indicator_map.csv`
- `industry_external_indicator_map.csv`
- `external_indicator_collection_manifest.csv`
- `external/common_market_macro.csv`
- `external/priority1_collection_status.csv`
- `external/priority1_fetch_run_status.csv`
- `external/energy_daily.csv`
- `external/agri_commodity_weekly.csv`
- `external/korea_domestic_monthly.csv`
- `external/krx_market_daily.csv`
- `external/china_macro_monthly.csv`
- `external/rates_kr_daily.csv`

### In code folder

- `paths.py`
- `external_sources.py`
- `init_external_priority1.py`
- `fetch_external_priority1.py`
- `new_strategy/docs/EXTERNAL_PIPELINE.md`

## Existing macro reused

From existing macro files:

- `kospi`
- `vix`
- `usdkrw`
- `us10y`
- `kr10y`
- `gold_kr_close`
- `gold_kr_ret`
- `gold_kr_volume`
- `gold_kr_trading_value`
- `risk_count`
- `regime`
- `exposure`

These were exported into:

- `external/common_market_macro.csv`

## Industry indicator mapping

Industry-level external indicator mapping was defined in:

- `industry_external_indicator_map.csv`

Common macro classification was defined in:

- `common_macro_indicator_map.csv`

Collection/refresh manifest was defined in:

- `external_indicator_collection_manifest.csv`

## Priority-1 collection status

Collected with actual data:

- `oil_brent`
  - file: `external/energy_daily.csv`
- `grains`
  - file: `external/agri_commodity_weekly.csv`
  - columns: `wheat, corn, soybean, grain_composite`
- `consumer_sentiment_kr`
  - file: `external/korea_domestic_monthly.csv`
- `retail_sales_kr`
  - file: `external/korea_domestic_monthly.csv`
- `kospi_trading_value`
  - file: `external/krx_market_daily.csv`
- `china_pmi`
  - currently stored as proxy in `external/china_macro_monthly.csv`
- `kr_3y`
  - currently stored as proxy in `external/rates_kr_daily.csv`

## Important caveats

- `china_pmi` is **not** official China PMI yet
  - current column: `china_mfg_confidence_proxy`
  - source: FRED/OECD proxy
- `kr_3y` is **not** exact Korea 3-year treasury yield yet
  - current columns:
    - `kr_short_rate_proxy`
    - `kr_interest_rate_spread_proxy`
  - source: public proxy series

These were explicitly marked as proxy-based to avoid confusion.

## KRX market daily issue and fix

Problem:

- `krx_market_daily.csv` initially stopped at `2025-12-19`

Cause:

- it was first aggregated from `feature_daily-001.csv`
- that source itself only ran through `2025-12-19`

Fix:

- updated aggregation logic to also read:
  - `C:\Users\sgw02\Desktop\data\python\Stock\basic_*.xlsx`

Current result:

- `external/krx_market_daily.csv` now runs through `2026-02-27`

## Default collection window

- Start: `2015-01-01`
- End: latest available value as of run date

Rule:

- daily/weekly/monthly indicators are stored in their native frequency
- later merges into stock/fundamental panels should use backward/asof logic only

## User preferences captured

- Fact-based data only
- Do not assume fixed pre-pricing timing
- Raw data/output on desktop path
- External data first, analysis later

## Suggested next steps

1. Replace proxy series where needed
   - official China PMI
   - exact Korea 3Y yield
2. Build external feature transforms
   - `20D_ret`, `60D_ret`, `mom_chg`, `3M_avg`, `ma_gap`
3. Validate external series coverage and release timing
4. Merge validated external indicators into quarterly/daily panels
5. Re-run correlation analysis only after data consistency checks
