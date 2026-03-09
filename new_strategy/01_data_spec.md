# KOSPI Strategy Data Spec

## Scope
- Price source files: `stock/2015.xlsx` ... `stock/2025.xlsx`
- Universe: `시장구분 == "KOSPI"`
- Note: `2020.xlsx` contains extra `소속부` column and it is ignored.

## Required Columns
- `종목코드`
- `종목명`
- `종가`
- `시가`
- `고가`
- `저가`
- `거래량`
- `거래대금`
- `시가총액`
- `상장주식수`
- `일자`
- `시장구분`
- `업종명`

## Cleaning Rules
1. Keep required columns only (ignore unknown columns).
2. `종목코드` is zero-padded to 6 chars.
3. Parse `일자` as `%Y%m%d` date.
4. Numeric columns are converted with `errors="coerce"`.
5. Trading-day flag:
- `is_trading_day = (종가 not null) and (거래량 > 0)`
6. Backtest uses trading rows only by default.

## Output Schema (`price_panel.parquet` / `.csv`)
- `date` (datetime)
- `code` (str, 6-digit)
- `name` (str)
- `market` (str)
- `industry` (str)
- `close`, `open`, `high`, `low` (float)
- `volume`, `trading_value`, `market_cap`, `shares_outstanding` (float)
- `is_trading_day` (bool)

## Strategy Trend Defaults
- Trend filter uses weekly-style moving averages on daily data:
- `5-week ~= 25 trading days` (`ma_short`)
- `10-week ~= 50 trading days` (`ma_mid`)
- `20-week ~= 100 trading days` (`ma_long`)
- Buy signal trend pattern: `ma_short > ma_mid > ma_long` and positive slopes.
- Sell signal trend pattern: 5w and 10w direction turn down together (AND), with confirmation days.

## Macro Input Schema (`macro_daily.csv`)
- `date` (YYYY-MM-DD)
- `kospi`
- `vix`
- `usdkrw`
- `us10y`
- `kr10y`
