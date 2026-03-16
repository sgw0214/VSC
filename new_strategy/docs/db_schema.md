# Database Schema

`new_strategy/build_market_db.py` builds:

- `C:\Users\sgw02\OneDrive\python\new_strategy\market_data.db`

The database integrates three domains:

1. `fact_price_daily`
2. `fact_fundamental_quarterly`
3. `fact_macro_daily`

## Tables

- `dim_symbol`
  - `code` (PK), `name`, `market`, `industry`, `first_seen`, `last_seen`

- `fact_price_daily`
  - PK: `(date, code)`
  - Fields:
    - `open, high, low, close`
    - `volume, trading_value`
    - `market_cap, shares_outstanding`
    - `source`

- `fact_fundamental_quarterly`
  - PK: `(code, bsns_year, reprt_code)`
  - Fields:
    - `corp_code, corp_name`
    - `rcept_no, rcept_dt, period`
    - `revenue, op_income, net_income`
    - `total_assets, total_liab, total_equity`
    - `op_margin, roe_simple`
    - `source`

- `fact_macro_daily`
  - PK: `date`
  - Base fields:
    - `kospi, vix, usdkrw, us10y, kr10y`
  - Optional gold fields:
    - `gold_kr_close, gold_kr_ret, gold_kr_volume, gold_kr_trading_value`
  - Source fields:
    - `kospi_source, vix_source, usdkrw_source, us10y_source, kr10y_source`

## Build

```bash
python -m new_strategy.build_market_db ^
  --stock-dir C:\Users\sgw02\OneDrive\python\Stock ^
  --start-year 2015 ^
  --end-year 2025 ^
  --macro-csv C:\Users\sgw02\OneDrive\python\new_strategy\macro_daily.csv ^
  --fundamental-csv C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_multi.csv ^
  --db-path C:\Users\sgw02\OneDrive\python\new_strategy\market_data.db
```

## Query examples

```sql
-- stock history
SELECT date, close
FROM fact_price_daily
WHERE code='005930'
ORDER BY date;

-- fundamentals history
SELECT bsns_year, reprt_code, revenue, op_income, net_income
FROM fact_fundamental_quarterly
WHERE code='005930'
ORDER BY bsns_year, reprt_code;

-- macro history
SELECT date, vix, usdkrw, us10y, kr10y, gold_kr_close, gold_kr_ret
FROM fact_macro_daily
ORDER BY date;
```
