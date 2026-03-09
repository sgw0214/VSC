# new_strategy

## 1) Build price panel
```bash
python new_strategy/build_price_panel.py --stock-dir stock --start-year 2015 --end-year 2025 --output new_strategy/data/price_panel.parquet
```

## 2) Build macro regime (optional)
Prepare `new_strategy/data/macro_daily.csv` with:
- `date,kospi,vix,usdkrw,us10y,kr10y`

Then run:
```bash
python new_strategy/macro_pipeline.py --input new_strategy/data/macro_daily.csv --output new_strategy/data/macro_regime.csv
```

## 3) Run walk-forward backtest
Without macro:
```bash
python new_strategy/backtest_walkforward.py --price-panel new_strategy/data/price_panel.csv --max-positions 5 --entry-top-n 10 --output new_strategy/output/walkforward_result_signal_top5.csv
```

With macro exposure:
```bash
python new_strategy/backtest_walkforward.py --price-panel new_strategy/data/price_panel.csv --macro new_strategy/data/macro_regime.csv --max-positions 5 --entry-top-n 10 --output new_strategy/output/walkforward_result_signal_top5.csv
```

## 4) Generate latest picks
```bash
python new_strategy/recommend_latest.py --price-panel new_strategy/data/price_panel.csv --top-n 10 --output new_strategy/output/latest_picks.csv
```

With macro gating:
```bash
python new_strategy/recommend_latest.py --price-panel new_strategy/data/price_panel.csv --macro new_strategy/data/macro_regime.csv --min-exposure 0.5 --top-n 10 --output new_strategy/output/latest_picks.csv
```

## 5) Fill macro data from Investing.com (network required)
```bash
python new_strategy/fetch_macro_investing.py --start 2015-01-01 --end 2026-12-31 --output new_strategy/data/macro_daily.csv --merge-existing
python new_strategy/macro_pipeline.py --input new_strategy/data/macro_daily.csv --output new_strategy/data/macro_regime.csv
```

## 6) Build integrated DB (price + macro + fundamentals)
```bash
python new_strategy/build_market_db.py --stock-dir stock --start-year 2015 --end-year 2025 --macro-csv new_strategy/data/macro_daily.csv --fundamental-csv new_strategy/data/fundamental_quarterly.csv --db-path new_strategy/data/market_data.db
```
- DB schema: `new_strategy/db_schema.md`

## 7) Run all pipeline once
```bash
python new_strategy/run_all_pipeline.py --stock-dir stock --start-year 2015 --end-year 2025
```
With macro/fundamental fetch:
```bash
python new_strategy/run_all_pipeline.py --stock-dir stock --start-year 2015 --end-year 2025 --fetch-macro --fetch-fundamental --dart-api-key YOUR_KEY
```

## Speed Tips
- First run is heavy because yearly cache is created.
- After first run, keep cache and rerun:
```bash
python new_strategy/build_price_panel.py --stock-dir stock --start-year 2015 --end-year 2025 --output new_strategy/data/price_panel.csv
python new_strategy/backtest_walkforward.py --price-panel new_strategy/data/price_panel.csv --output new_strategy/output/walkforward_result.csv
```
- For full rebuild (ignore cache), add `--no-cache`.

## Notes
- `2020.xlsx` extra column `소속부` is ignored.
- If market labels are missing in later years (for example 2024, 2025), they are backfilled by 2023 market classification for each code.
- Result columns are documented in `new_strategy/result_columns.md`.
- Default macro exposure map is `risk_on=1.0`, `neutral=0.4`, `risk_off=0.1`.
- Default macro exposure map is `risk_on=1.0`, `neutral=0.3`, `risk_off=0.1`.
- Signal backtest allows `0` positions (full cash) when exposure implies zero target positions.
- Trend defaults are weekly-style on daily data:
- `ma_short=25` (5-week), `ma_mid=50` (10-week), `ma_long=100` (20-week).
- Buy trend pattern: `5w > 10w > 20w` with positive slopes.
- Sell trend pattern: 5w and 10w turn down together (AND), with confirmation days.
- Entry risk defaults: `max_ret_5d=0.12`, `max_dist_ma_mid=0.18`.
