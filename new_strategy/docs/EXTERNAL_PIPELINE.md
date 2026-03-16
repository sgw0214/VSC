# External Pipeline

## Paths

- Code: `C:\Users\sgw02\python\new_strategy`
- Data/output: `C:\Users\sgw02\Desktop\data\python\new_strategy`
- External store: `C:\Users\sgw02\Desktop\data\python\new_strategy\external`

## Current rule

- Reuse existing macro series first.
- Store each external family in a separate csv under `external/`.
- Keep raw frequency as-is:
  - daily -> daily
  - weekly -> weekly
  - monthly -> monthly
- Derive lag/rolling features later after data quality is checked.

## First step

```bash
python new_strategy/init_external_priority1.py
```

This does two things:

- exports reusable existing macro/regime columns into `external/common_market_macro.csv`
- creates empty target files for `priority=1` indicators and writes `external/priority1_collection_status.csv`

## Period rule

- Default collection window: `2015-01-01` to `today`
- Monthly/weekly series are saved only up to the latest published point.
- Later panel merges must use backward/asof joins only.

## Current fetch command

```bash
python -m new_strategy.fetch_external_priority1
```

- Implemented now:
  - `oil_brent`
- Initialized but not implemented yet:
  - `china_pmi`
  - `kr_3y`
  - `grains`
  - `consumer_sentiment_kr`
  - `retail_sales_kr`
  - `kospi_trading_value`

Run status is written to:

- `external/priority1_fetch_run_status.csv`

## Next implementation targets

- `china_pmi`
- `oil_brent`
- `kr_3y`
- `grains`
- `consumer_sentiment_kr`
- `retail_sales_kr`
- `kospi_trading_value`
