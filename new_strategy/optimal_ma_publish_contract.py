from __future__ import annotations

from pathlib import Path

from new_strategy.paths import output_path


OPTIMAL_MA_SCHEMA_VERSION = "optimal_ma_monthly_weekly_v2"
OPTIMAL_MA_ALL_SCHEMA_VERSION = "optimal_ma_all_timeframes_v2"

OPTIMAL_MA_PUBLISHED_DIR = output_path("ma_breakout_research", "published")
OPTIMAL_MA_SELECTION_PATH = OPTIMAL_MA_PUBLISHED_DIR / "optimal_ma_selection_monthly_weekly.csv"
OPTIMAL_MA_META_PATH = OPTIMAL_MA_PUBLISHED_DIR / "optimal_ma_selection_monthly_weekly_meta.json"
OPTIMAL_MA_README_PATH = OPTIMAL_MA_PUBLISHED_DIR / "optimal_ma_selection_monthly_weekly.md"
OPTIMAL_MA_ALL_SELECTION_PATH = OPTIMAL_MA_PUBLISHED_DIR / "optimal_ma_selection_all_timeframes.csv"
OPTIMAL_MA_ALL_META_PATH = OPTIMAL_MA_PUBLISHED_DIR / "optimal_ma_selection_all_timeframes_meta.json"
OPTIMAL_MA_ALL_README_PATH = OPTIMAL_MA_PUBLISHED_DIR / "optimal_ma_selection_all_timeframes.md"

OPTIMAL_MA_SELECTION_COLUMNS = [
    "code",
    "name",
    "ma_timeframe",
    "action_mode",
    "ma_window",
    "total_return",
    "buy_hold_return",
    "excess_return",
    "annualized_return",
    "max_drawdown",
    "win_rate",
    "completed_trade_count",
    "trade_count",
    "exposure_ratio",
]

OPTIMAL_MA_REQUIRED_COLUMNS = [
    *OPTIMAL_MA_SELECTION_COLUMNS,
    "selection_scope",
    "published_source",
]

OPTIMAL_MA_ALLOWED_TIMEFRAMES = {"monthly", "weekly", "daily"}
OPTIMAL_MA_ALLOWED_ACTION_MODES = {"native_timeframe_close", "daily_close_action"}

TIMEFRAME_LABELS = {"monthly": "월봉", "weekly": "주봉", "daily": "일봉"}
ACTION_MODE_LABELS = {
    "native_timeframe_close": "봉마감형",
    "daily_close_action": "일별판정형",
}


def normalize_optimal_ma_code(value: object) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    return text.zfill(6)
