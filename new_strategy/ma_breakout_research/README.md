# MA Breakout Research

This folder contains isolated research code for moving-average breakout backtests.

Two action modes are evaluated independently:

1. Native timeframe action
   - monthly MA -> trade only on month-end closes
   - weekly MA -> trade only on week-end closes
   - daily MA -> trade on each daily close

2. Daily close action
   - monthly/weekly/daily MAs are evaluated against each daily close
   - weekly/monthly MAs are based on the latest completed weekly/monthly bar and are
     forward-filled to daily dates

This research is intentionally separated from the live strategy and dashboard logic.

