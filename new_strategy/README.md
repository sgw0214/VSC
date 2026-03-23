# new_strategy

## Paths

- Code:
  - `E:\VSC\CODE\new_strategy`
- Strategy data:
  - `C:\Users\sgw02\OneDrive\python\new_strategy`
- Raw stock source:
  - `C:\Users\sgw02\OneDrive\python\Stock`

## 1) Build price panel

```bash
python new_strategy/build_price_panel.py --stock-dir C:\Users\sgw02\OneDrive\python\Stock --start-year 2015 --end-year 2025 --output C:\Users\sgw02\OneDrive\python\new_strategy\price_panel.csv
```

## 2) Fill macro data

```bash
python new_strategy/fetch_macro_investing.py --start 2015-01-01 --end 2026-12-31 --output C:\Users\sgw02\OneDrive\python\new_strategy\macro_daily.csv --merge-existing
```

## 3) Merge gold into macro_daily

```bash
python new_strategy/merge_gold_to_macro.py --macro C:\Users\sgw02\OneDrive\python\new_strategy\macro_daily.csv --gold C:\Users\sgw02\OneDrive\python\new_strategy\gold_kr_daily.xlsx --output C:\Users\sgw02\OneDrive\python\new_strategy\macro_daily.csv
```

## 4) Build macro regime

Required macro base columns:
- `date`
- `kospi`
- `vix`
- `usdkrw`
- `us10y`
- `kr10y`

Optional gold columns:
- `gold_kr_close`
- `gold_kr_ret`
- `gold_kr_volume`
- `gold_kr_trading_value`

```bash
python new_strategy/macro_pipeline.py --input C:\Users\sgw02\OneDrive\python\new_strategy\macro_daily.csv --output C:\Users\sgw02\OneDrive\python\new_strategy\macro_regime_v3_rec.csv
```

## 5) Run walk-forward backtest

Without macro:

```bash
python new_strategy/backtest_walkforward.py --price-panel C:\Users\sgw02\OneDrive\python\new_strategy\price_panel.csv --max-positions 5 --entry-top-n 10 --output C:\Users\sgw02\OneDrive\python\new_strategy\output\walkforward_result_signal_top5.csv
```

With macro exposure:

```bash
python new_strategy/backtest_walkforward.py --price-panel C:\Users\sgw02\OneDrive\python\new_strategy\price_panel.csv --macro C:\Users\sgw02\OneDrive\python\new_strategy\macro_regime_v3_rec.csv --max-positions 5 --entry-top-n 10 --output C:\Users\sgw02\OneDrive\python\new_strategy\output\walkforward_result_signal_top5.csv
```

## 6) Generate latest picks

```bash
python new_strategy/recommend_latest.py --price-panel C:\Users\sgw02\OneDrive\python\new_strategy\price_panel.csv --top-n 10 --output C:\Users\sgw02\OneDrive\python\new_strategy\output\latest_picks.csv
```

With macro gating:

```bash
python new_strategy/recommend_latest.py --price-panel C:\Users\sgw02\OneDrive\python\new_strategy\price_panel.csv --macro C:\Users\sgw02\OneDrive\python\new_strategy\macro_regime_v3_rec.csv --min-exposure 0.5 --top-n 10 --output C:\Users\sgw02\OneDrive\python\new_strategy\output\latest_picks.csv
```

## 7) Build integrated DB

```bash
python -m new_strategy.build_market_db --stock-dir C:\Users\sgw02\OneDrive\python\Stock --start-year 2015 --end-year 2025 --macro-csv C:\Users\sgw02\OneDrive\python\new_strategy\macro_daily.csv --fundamental-csv C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_multi.csv --db-path C:\Users\sgw02\OneDrive\python\new_strategy\market_data.db
```

- DB schema:
  - `new_strategy/docs/db_schema.md`

## 8) Run all pipeline once

```bash
python new_strategy/run_all_pipeline.py --stock-dir C:\Users\sgw02\OneDrive\python\Stock --start-year 2015 --end-year 2025
```

With macro/fundamental fetch:

```bash
python new_strategy/run_all_pipeline.py --stock-dir C:\Users\sgw02\OneDrive\python\Stock --start-year 2015 --end-year 2025 --fetch-macro --fetch-fundamental --dart-api-key YOUR_KEY
```

## Speed tips

- First run is heavy because yearly cache is created.
- Keep `cache\yearly\*.pkl` unless raw yearly xlsx changes.
- For full rebuild, add `--no-cache`.

## Notes

- `2020.xlsx` extra column is ignored.
- If market labels are missing in later years, they are backfilled by 2023 market classification per code.
- Result columns are documented in `new_strategy/docs/result_columns.md`.
- Default macro exposure map is `risk_on=1.0`, `neutral=0.3`, `risk_off=0.1`.
- Signal backtest allows `0` positions when exposure implies full cash.
- Trend defaults are weekly-style on daily data:
  - `ma_short=25` (5-week)
  - `ma_mid=50` (10-week)
  - `ma_long=100` (20-week)

## 9) Earnings Signal Pipeline v2

Outputs are written under:

- `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2`

Run once:

```bash
python -m new_strategy.run_signal_pipeline
```

Run once with alerts:

```bash
python -m new_strategy.run_signal_pipeline --send-alerts
```

Run fast alert mode:

```bash
python -m new_strategy.run_signal_pipeline --send-alerts --fast-alerts
```

Run fast alert mode with automatic latest refresh:

```bash
python -m new_strategy.run_signal_pipeline --refresh-data --send-alerts --fast-alerts
```

Add macro/gold refresh too:

```bash
python -m new_strategy.run_signal_pipeline --refresh-data --refresh-gold --refresh-macro --send-alerts --fast-alerts
```

Main outputs:

- `data_health_summary.csv`
- `signal_daily.csv`
- `signal_daily_latest.csv`
- `decision_report_daily.csv`
- `trade_log.csv`
- `equity_curve.csv`
- `strategy_eval.csv`
- `research_condition_performance.csv`
- `research_condition_performance_by_industry.csv`
- `strategy_metadata.json`

## 10) Strategy Service

Run once:

```bash
python -m new_strategy.run_strategy_service --mode once --send-alerts
```

Run loop on home PC:

```bash
python -m new_strategy.run_strategy_service --mode loop --interval-seconds 300 --send-alerts
```

Run loop in fast alert mode:

```bash
python -m new_strategy.run_strategy_service --mode loop --interval-seconds 300 --send-alerts --fast-alerts
```

Run loop with automatic latest refresh before each fast alert cycle:

```bash
python -m new_strategy.run_strategy_service --mode loop --interval-seconds 300 --refresh-data --send-alerts --fast-alerts
```

Default market window:

- open: `08:55`
- close: `15:40`

Recommended home-PC schedule:

- intraday: every 30 minutes, fetch current quotes once and run `fast alert`
- pre-close risk check: one extra run at `15:20`
- post-close EOD refresh: one run at `16:10` with `--refresh-data`

Run the schedule service directly:

```bash
python -m new_strategy.run_market_schedule_service --poll-seconds 60 --intraday-open 09:00 --intraday-close 15:00 --intraday-interval-minutes 30 --preclose-time 15:20 --eod-time 16:10 --live-quotes C:\Users\sgw02\OneDrive\python\new_strategy\live_quotes.csv
```

Hidden launcher on Windows:

```powershell
E:\VSC\CODE\new_strategy\run_background_refresh_service.ps1
```

## 11) Streamlit Dashboard

```bash
streamlit run e:\VSC\CODE\new_strategy\streamlit_app.py
```

Pages:

- `Data Health`
- `Research Lab`
- `Strategy Builder`
- `Daily Decision`

## 12) Alert Environment Variables

Telegram:

- `NEW_STRATEGY_TELEGRAM_BOT_TOKEN`
- `NEW_STRATEGY_TELEGRAM_CHAT_ID`
- `NEW_STRATEGY_NOTIFIER_CHANNELS` (optional, e.g. `telegram`)

Email:

- `NEW_STRATEGY_EMAIL_HOST`
- `NEW_STRATEGY_EMAIL_PORT`
- `NEW_STRATEGY_EMAIL_USERNAME`
- `NEW_STRATEGY_EMAIL_PASSWORD`
- `NEW_STRATEGY_EMAIL_FROM`
- `NEW_STRATEGY_EMAIL_TO`

## 13) Telegram Alert Test

1. Create a bot with `@BotFather`
2. Send one message to your bot in Telegram
3. Get chat ids:

```bash
python -m new_strategy.telegram_helper list-chats --bot-token YOUR_BOT_TOKEN
```

4. Print PowerShell env commands:

```bash
python -m new_strategy.telegram_helper show-env --bot-token YOUR_BOT_TOKEN --chat-id YOUR_CHAT_ID
```

5. Send a test message:

```bash
python -m new_strategy.telegram_helper send-test --bot-token YOUR_BOT_TOKEN --chat-id YOUR_CHAT_ID --text "new_strategy telegram test"
```

6. Use Telegram only:

```powershell
$env:NEW_STRATEGY_NOTIFIER_CHANNELS="telegram"
```

7. Run the live pipeline:

```bash
python -m new_strategy.run_signal_pipeline --send-alerts
```

## 13-1) Telegram Bridge Design

- Free-conversation Telegram bridge design:
  - `new_strategy/docs/TELEGRAM_BRIDGE_DESIGN.md`

## 13-2) Telegram Free-Conversation Bridge

Required environment variables:

- `NEW_STRATEGY_TELEGRAM_BOT_TOKEN`
- `NEW_STRATEGY_TELEGRAM_BRIDGE_ALLOWED_CHAT_IDS`
  - if omitted, falls back to `NEW_STRATEGY_TELEGRAM_CHAT_ID`
- `OPENAI_API_KEY`

Optional:

- `NEW_STRATEGY_TELEGRAM_BRIDGE_MODEL`
- `NEW_STRATEGY_TELEGRAM_BRIDGE_POLL_SECONDS`
- `NEW_STRATEGY_TELEGRAM_BRIDGE_HISTORY_TURNS`

Run once to process queued messages:

```bash
python -m new_strategy.telegram_bridge_service --once
```

Run as a continuous service:

```bash
python -m new_strategy.telegram_bridge_service
```

Supported interactions:

- `/help`
- `/status`
- `/latest`
- `/alerts`
- `/health`
- six-digit code query, e.g. `005930 왜 HOLD야?`
- free conversation when `OPENAI_API_KEY` is set
- execution requests:
  - `fast alert 다시 돌려줘`
  - `주가 최신화해줘`
  - `매크로까지 다시 받아서 전체 돌려줘`

Confirmation flow for risky jobs:

- bridge replies with `job_id`
- execute by sending:

```text
confirm 1001
```

- cancel by sending:

```text
reject 1001
```

Bridge logs are written under:

- `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\telegram_bridge`

Supported portfolio commands:

- `매수 005930 70000 10`
- `매도 005930 73000 5`
- `/portfolio` or `보유현황`
- `/mytrades` or `내 거래내역`
- `/pending` or `미처리 요청`
- `/bridgeoff`
- `/streamliton`
- `/streamlitoff`

Behavior:

- Manual trades update a bridge-only actual position ledger.
- `/status` includes actual holding status for the current Telegram chat.
- Questions the bridge cannot answer are logged automatically and can be reviewed with `/pending`.

## 14) Live Quote Overlay for Intraday Use

Current KRX daily refresh updates only when the daily source publishes data. If you want intraday signal recalculation, provide a live quote file and fast alert mode will build a synthetic current-day snapshot.

Default path:

- `C:\Users\sgw02\OneDrive\python\new_strategy\live_quotes.csv`

Supported columns:

- `code` or `종목코드`
- `date` or `일자`
- `close` or `현재가`
- optional: `open`, `high`, `low`, `volume`, `trading_value`, `quote_time`

Example:

```csv
date,code,close,open,high,low,volume,trading_value,quote_time
2026-03-12,005930,81200,80800,81400,80700,523441,42388200000,2026-03-12 10:15:00
2026-03-12,000660,214500,213000,215000,212500,318220,68190100000,2026-03-12 10:15:00
```

Run fast alert with live quotes:

```bash
python -m new_strategy.run_signal_pipeline --refresh-data --send-alerts --fast-alerts --live-quotes C:\Users\sgw02\OneDrive\python\new_strategy\live_quotes.csv
```

## 15) Kiwoom REST Live Quotes

Default credential directory:

- `C:\Users\sgw02\OneDrive\python\키움API`

Required files:

- `국내_*_appkey.txt`
- `국내_*_secretkey.txt`

The helper automatically finds that directory under `OneDrive\python`, issues an access token with `POST /oauth2/token`, and fetches current quotes with:

- `POST https://api.kiwoom.com/api/dostk/mrkcond`
- header: `Authorization: Bearer ...`
- header: `api-id: ka10007`

Run once:

```bash
python -m new_strategy.fetch_live_quotes_kiwoom_rest --codes 005930,000660 --once
```

Run in a loop and keep `live_quotes.csv` updated:

```bash
python -m new_strategy.fetch_live_quotes_kiwoom_rest --interval-seconds 30
```

Hidden PowerShell launcher:

```powershell
E:\VSC\CODE\new_strategy\run_kiwoom_live_quotes.ps1
```

Current behavior:

- manual portfolio codes are included
- latest strategy `BUY/HOLD/WATCH` codes are included
- output file is `C:\Users\sgw02\OneDrive\python\new_strategy\live_quotes.csv`
- production-safe default pacing is `0.50s` between requests, which stays below the `5 requests / second` limit
