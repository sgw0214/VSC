# Session 2026-03-16 Clean Optimal MA Compare

## Scope

- Save the conversation around optimal MA integration status, fixed 10-MA remnants, and the clean re-run of the comparison.
- Keep this separate from live-strategy code changes.

## Conversation Summary

### 1. Main strategy vs optimal MA status

- User asked whether optimal MA was actually reflected in the main strategy.
- Inspection confirmed:
  - main strategy logic is in `new_strategy/earnings_signal_engine.py`
  - the main live engine is not using per-stock optimal MA as the decision backbone
  - current outputs still contain fixed helper fields such as:
    - `monthly_main_ok`
    - `weekly_aux_ok`
    - `month_10_ma`
    - `week_10_ma`

- Clarification was important:
  - optimal MA exists in research/comparison and overlay paths
  - it is not directly integrated into the main live decision engine

### 2. Fixed 10-MA concern

- User pointed out that fixed `10` moving averages should be removed and that main strategy should not be treated as if optimal MA were blended into it.
- Re-check showed:
  - current runtime metadata uses `legacy_mid`
  - the main decision core is still `ma_mid`-based
  - fixed `month_10/week_10` fields remain in the pipeline and reporting outputs as residual helper fields

- Correct interpretation:
  - fixed `10` MA is not the main live trend backbone
  - but fixed `10` MA remnants still exist in the pipeline and can create confusion/noise

### 3. What was actually done yesterday

- User clarified the exact three-way comparison performed yesterday:
  1. existing logic
  2. existing logic + optimal MA blend
  3. existing logic, with optimal MA shown only as a separate indicator

- Existing result files were verified under:
  - `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_compare_optimal_ma`
  - `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_compare_optimal_ma_scope`

- Verified findings from those files:
  - hard blending degraded portfolio performance
  - indicator-only review still showed directional value

### 4. User concern about noise in the old blend test

- User raised a valid concern:
  - the old blend comparison might have been contaminated by fixed `10` MA related noise
- Re-inspection showed:
  - `compare_strategy_with_optimal_ma.py` forces `trend_mode = legacy_mid`
  - direct blend logic uses `optimal_ma_ok` to gate `buy_candidate`, `watch_candidate`, and also modifies `ma_mid`
  - however, the strategy frame still carried fixed `month_10/week_10` derived fields
  - `timing_score` was part of ML assist inputs
  - runtime metadata from the older run showed ML backend was active

- Conclusion before rerun:
  - the prior comparison was not fully clean
  - the most defensible retest was:
    - keep `legacy_mid`
    - force `ml_backend = none`
    - reuse the same optimal MA selection table
    - rerun baseline vs blend vs indicator-only review

## Clean Re-Run

### Run setup

- A clean rerun was executed with:
  - `trend_mode = legacy_mid`
  - `ml_backend = none`
  - reused selection file from the prior comparison:
    - `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_compare_optimal_ma\optimal_ma_selection.csv`

- New outputs were written to:
  - `C:\Users\sgw02\Desktop\data\python\new_strategy\output\strategy_compare_optimal_ma_clean_noml`

### Clean re-run result

- Baseline:
  - CAGR: `6.11%`
  - MDD: `-52.51%`
  - Sharpe: `0.378`
  - file:
    - `C:\Users\sgw02\Desktop\data\python\new_strategy\output\strategy_compare_optimal_ma_clean_noml\baseline\portfolio_summary.csv`

- Baseline + optimal MA blend:
  - CAGR: `2.57%`
  - MDD: `-54.05%`
  - Sharpe: `0.225`
  - file:
    - `C:\Users\sgw02\Desktop\data\python\new_strategy\output\strategy_compare_optimal_ma_clean_noml\baseline_plus_optimal_ma\portfolio_summary.csv`

- Indicator-only review:
  - file:
    - `C:\Users\sgw02\Desktop\data\python\new_strategy\output\strategy_compare_optimal_ma_clean_noml\indicator_review_summary.csv`
  - 20-day forward return summary:
    - BUY agree: `+0.41%`
    - BUY disagree: `-0.01%`
    - SELL agree: `-0.05%`
    - SELL disagree: `+1.47%`

### Clean re-run conclusion

- Even after removing ML-related indirect noise, the hard blend still underperformed the baseline.
- The indicator-only interpretation still retained directional usefulness.
- Therefore the more defensible statement is:
  - hard blending was worse even in the clean rerun
  - optimal MA still has value as a separate review/confirmation indicator

## Important Clarification

- User explicitly stated:
  - do not assume main strategy is blended with optimal MA
  - fixed `10` MA should be removed rather than treated as the intended design

- Current working interpretation after the conversation:
  - main live logic should not be described as optimal-MA-blended
  - previous blend experiment should not be confused with live strategy
  - fixed `10` MA remnants are a cleanup target

## Files Mentioned

- Main engine:
  - `C:\Users\sgw02\python\new_strategy\earnings_signal_engine.py`
- Comparison script:
  - `C:\Users\sgw02\python\new_strategy\compare_strategy_with_optimal_ma.py`
- Previous scope comparison:
  - `C:\Users\sgw02\python\new_strategy\compare_optimal_ma_scope.py`
- Existing selection:
  - `C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_compare_optimal_ma\optimal_ma_selection.csv`
- Clean rerun output root:
  - `C:\Users\sgw02\Desktop\data\python\new_strategy\output\strategy_compare_optimal_ma_clean_noml`

## Final State For Handoff

- Conversation saved.
- No live strategy logic was changed in this step.
- Clean comparison outputs now exist separately from the older run.
