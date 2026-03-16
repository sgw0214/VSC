# Session Thread

## Overview

This file summarizes the working thread for the KOSPI strategy and DART fundamental data pipeline so the work can be resumed on another machine.

## Scope

- Workspace root: `e:\VSC\CODE`
- Main working folder: `new_strategy`
- Code path:
  - `E:\VSC\CODE\new_strategy`
- Data path:
  - `C:\Users\sgw02\OneDrive\python\new_strategy`
- Raw stock source path:
  - `C:\Users\sgw02\OneDrive\python\Stock`
- Objective:
  - build and maintain KOSPI stock data
  - collect DART quarterly fundamentals
  - structure data so strategy/backtest/dashboard work can continue

## Key Decisions

- DART source uses `fnlttMultiAcnt.json`
- Request rate limit is capped at `90 per minute`
- Requests are made at `corp_code` level and then fanned out to mapped stock codes
- Preferred shares are mapped to the base issuer when needed
- Final working fundamental file is stock-code based, not pure corp-code based
- Quarterly trend analysis needs derived standalone quarter columns

## Final Fundamental Files

- Final stock-level file:
  - `C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_multi.csv`
- Raw accumulated DART response file:
  - `C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_raw.csv`
- Request log:
  - `C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_multi_request_log.csv`
- Corp-code cache:
  - `C:\Users\sgw02\OneDrive\python\new_strategy\dart_corp_codes.csv`

## Current Fundamental State

- DART collection completed for the main 2015-2026 sweep
- Additional latest refresh was run for `2025` `11011` filings
- Current final aggregated row count after rebuild:
  - `32998` rows in `fundamental_quarterly_multi.csv`
- Current `2025` annual report (`11011`) rows:
  - `48`

## Important Data Semantics

- `11013` = Q1 report
- `11012` = half-year report
- `11014` = Q3 report
- `11011` = annual report

For DART `fnlttMultiAcnt`:

- flow accounts in `thstrm_amount` behave as:
  - Q1: standalone
  - Q2/H1: standalone in this dataset
  - Q3: standalone in this dataset
  - annual: full-year cumulative
- Q4 standalone is derived as:
  - annual `thstrm_amount` minus Q3 cumulative `thstrm_add_amount`

## Added Derived Columns

These were added to `fundamental_quarterly_multi.csv`:

- `분기매출액`
- `분기영업이익`
- `분기당기순이익`
- `분기영업이익률`
- `분기ROE(단순)`

## Important Code Changes

Updated file:

- `new_strategy/fetch_fundamental_dart.py`

Main changes:

- skip duplicate requests using request log
- normalize `corp_code` before comparing keys
- accumulate raw results instead of overwriting per batch
- remove per-batch backup file creation
- support standalone quarter metric derivation
- support partial/latest refresh with:
  - `--report-codes`
  - `--ignore-skip-keys`

Auxiliary file created for chart rendering:

- `new_strategy/render_samsung_revenue_html.py`

## Visualization Outputs Created

- `new_strategy/output/samsung_005930_quarterly_revenue.png`
- `new_strategy/output/samsung_005930_quarterly_revenue.html`
- `new_strategy/output/samsung_005930_quarterly_op_income.png`
- `new_strategy/output/samsung_005930_quarterly_net_income.png`

## Notes About Duplicates and Missing Quarters

- `fundamental_quarterly_multi.csv` does not have duplicate rows by:
  - `종목코드 + 사업연도 + 보고서코드`
- apparent duplicates mostly come from:
  - multiple stock codes mapped to the same corp
- missing quarters can be caused by:
  - listing timing
  - filing timing
  - no DART response for that period
  - future or not-yet-filed reports

## Latest Refresh Command Pattern

Example for latest annual refresh:

```powershell
python new_strategy/fetch_fundamental_dart.py `
  --api-key "DART_API_KEY" `
  --price-panel C:\Users\sgw02\OneDrive\python\new_strategy\price_panel.csv `
  --start-year 2025 `
  --end-year 2025 `
  --report-codes 11011 `
  --ignore-skip-keys `
  --rpm 90 `
  --sleep-sec 0 `
  --max-requests 2000 `
  --raw-output C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_raw.csv `
  --output C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_multi.csv
```

After raw update, rebuild final aggregate if needed:

```powershell
python -c "import pandas as pd; import new_strategy.fetch_fundamental_dart as m; raw=pd.read_csv(r'C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_raw.csv', low_memory=False); q=m.build_quarterly(raw); q['code']=q['code'].astype(str).str.zfill(6); q['bsns_year']=pd.to_numeric(q['bsns_year'], errors='coerce'); q['reprt_code']=q['reprt_code'].map(m._norm_reprt_code); q=q.sort_values(['code','bsns_year','reprt_code','rcept_no']).drop_duplicates(subset=['code','bsns_year','reprt_code'], keep='last').reset_index(drop=True); q.rename(columns=m.KR_COLS).to_csv(r'C:\Users\sgw02\OneDrive\python\new_strategy\fundamental_quarterly_multi.csv', index=False, encoding='utf-8-sig')"
```

## Natural Next Steps

- build corp-level deduplicated fundamental file if needed
- create coverage diagnostics for missing quarters
- integrate fundamentals into ranking/strategy layer
- connect refreshed fundamentals to dashboard/report generation
