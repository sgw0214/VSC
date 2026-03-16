# MA Window Research

This folder contains isolated research code for finding per-stock moving-average windows
that minimize close-to-moving-average tracking error across daily, weekly, and monthly
frequencies.

It is intentionally separated from the live strategy, dashboard, and existing signal
pipeline so that experimentation here does not change current production logic.

Primary entrypoint:

- `analyze_optimal_ma_windows.py`

Generated files are written to:

- `output/ma_window_research/` under the configured `NEW_STRATEGY_OUTPUT_ROOT`

