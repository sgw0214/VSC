# Database Schema

`new_strategy/build_market_db.py` builds `new_strategy/data/market_data.db` with three data domains:

1. `fact_price_daily` (KRX stock daily)
2. `fact_fundamental_quarterly` (DART quarterly/annual fundamentals)
3. `fact_macro_daily` (macro time series)

## Tables

- `dim_symbol`
  - `code` (PK), `name`, `market`, `industry`, `first_seen`, `last_seen`
- `fact_price_daily`
  - PK: `(date, code)`
  - Fields: `open, high, low, close, volume, trading_value, market_cap, shares_outstanding, source`
- `fact_fundamental_quarterly`
  - PK: `(code, bsns_year, reprt_code)`
  - Fields: `rcept_no, rcept_dt, revenue, op_income, net_income, total_assets, total_liab, total_equity, op_margin, roe_simple, source`
- `fact_macro_daily`
  - PK: `date`
  - Fields: `kospi, vix, usdkrw, us10y, kr10y` plus source columns

## Build

```bash
python new_strategy/build_market_db.py ^
  --stock-dir stock ^
  --start-year 2015 ^
  --end-year 2025 ^
  --macro-csv new_strategy/data/macro_daily.csv ^
  --fundamental-csv new_strategy/data/fundamental_quarterly.csv ^
  --db-path new_strategy/data/market_data.db
```

## Query Examples

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
SELECT date, vix, usdkrw, us10y, kr10y
FROM fact_macro_daily
ORDER BY date;
```
