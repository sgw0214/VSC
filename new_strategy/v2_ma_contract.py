from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


V2_MONTH_DISPLAY_DIST = "v2_month_display_dist"
V2_WEEK_DISPLAY_DIST = "v2_week_display_dist"
V2_CONTRACT_MODE = "v2_contract_mode"
V2_BUY_TIMEFRAME = "v2_buy_timeframe"
V2_SELL_TIMEFRAME = "v2_sell_timeframe"
V2_BUY_WINDOW = "v2_buy_window"
V2_SELL_WINDOW = "v2_sell_window"

TIMEFRAME_LABELS = {"monthly": "월봉", "weekly": "주봉", "daily": "일봉"}
TIMEFRAME_SHORT_LABELS = {"monthly": "월", "weekly": "주", "daily": "일"}
MODE_LABELS = {
    "monthly_buy_weekly_sell": "월봉매수 / 주봉매도",
    "weekly_buy_monthly_sell": "주봉매수 / 월봉매도",
    "monthly_buy_monthly_sell": "월봉매수 / 월봉매도",
    "weekly_buy_weekly_sell": "주봉매수 / 주봉매도",
}


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype="float64")


def _text_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(pd.NA, index=frame.index, dtype="string")
    series = frame[column].astype("string").str.strip().str.lower()
    return series.replace({"": pd.NA, "nan": pd.NA, "none": pd.NA, "nat": pd.NA})


def normalize_v2_ma_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    out = frame.copy()
    out["v2_month_window"] = (
        _numeric_series(out, "v2_month_window")
        .combine_first(_numeric_series(out, "monthly_optimal_window"))
        .combine_first(_numeric_series(out, "monthly_window"))
    )
    out["v2_week_window"] = (
        _numeric_series(out, "v2_week_window")
        .combine_first(_numeric_series(out, "weekly_optimal_window"))
        .combine_first(_numeric_series(out, "weekly_window"))
    )
    out["v2_month_ma"] = _numeric_series(out, "v2_month_ma").combine_first(_numeric_series(out, "monthly_ma_price"))
    out["v2_week_ma"] = _numeric_series(out, "v2_week_ma").combine_first(_numeric_series(out, "weekly_ma_price"))
    out[V2_MONTH_DISPLAY_DIST] = (
        _numeric_series(out, "v2_month_live_dist")
        .combine_first(_numeric_series(out, "v2_month_period_dist"))
        .combine_first(_numeric_series(out, "monthly_dist"))
    )
    out[V2_WEEK_DISPLAY_DIST] = (
        _numeric_series(out, "v2_week_live_dist")
        .combine_first(_numeric_series(out, "v2_week_period_dist"))
        .combine_first(_numeric_series(out, "weekly_dist"))
    )
    return out


def normalize_v2_mode_contract_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    out = frame.copy()
    out[V2_CONTRACT_MODE] = _text_series(out, V2_CONTRACT_MODE).combine_first(_text_series(out, "mode"))
    out[V2_BUY_TIMEFRAME] = _text_series(out, V2_BUY_TIMEFRAME).combine_first(_text_series(out, "buy_timeframe"))
    out[V2_SELL_TIMEFRAME] = _text_series(out, V2_SELL_TIMEFRAME).combine_first(_text_series(out, "sell_timeframe"))
    out[V2_BUY_WINDOW] = _numeric_series(out, V2_BUY_WINDOW).combine_first(_numeric_series(out, "buy_window"))
    out[V2_SELL_WINDOW] = _numeric_series(out, V2_SELL_WINDOW).combine_first(_numeric_series(out, "sell_window"))
    return out


def _row_text(row: pd.Series | dict[str, Any], *columns: str) -> str | None:
    for column in columns:
        value = row.get(column)
        if value is None or pd.isna(value):
            continue
        text = str(value).strip().lower()
        if text and text not in {"nan", "none", "nat"}:
            return text
    return None


def _row_numeric(row: pd.Series | dict[str, Any], *columns: str) -> float | None:
    for column in columns:
        value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
        if pd.notna(value):
            return float(value)
    return None


def _resolve_contract_window(
    timeframe: str | None,
    explicit_window: float | None,
    month_window: float | None,
    week_window: float | None,
) -> int | None:
    if explicit_window is not None:
        return int(explicit_window)
    if timeframe == "monthly" and month_window is not None:
        return int(month_window)
    if timeframe == "weekly" and week_window is not None:
        return int(week_window)
    return None


def _fallback_timeframe(preferred: str, month_window: float | None, week_window: float | None) -> str | None:
    if preferred == "monthly" and month_window is not None:
        return "monthly"
    if preferred == "weekly" and week_window is not None:
        return "weekly"
    if preferred == "monthly" and week_window is not None:
        return "weekly"
    if preferred == "weekly" and month_window is not None:
        return "monthly"
    return None


def v2_mode_contract_context(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    month_window = _row_numeric(row, "v2_month_window", "monthly_optimal_window", "monthly_window")
    week_window = _row_numeric(row, "v2_week_window", "weekly_optimal_window", "weekly_window")

    buy_timeframe = _row_text(row, V2_BUY_TIMEFRAME, "buy_timeframe")
    sell_timeframe = _row_text(row, V2_SELL_TIMEFRAME, "sell_timeframe")
    if buy_timeframe not in TIMEFRAME_LABELS:
        buy_timeframe = _fallback_timeframe("monthly", month_window, week_window)
    if sell_timeframe not in TIMEFRAME_LABELS:
        sell_timeframe = _fallback_timeframe("weekly", month_window, week_window)

    buy_window = _resolve_contract_window(
        buy_timeframe,
        _row_numeric(row, V2_BUY_WINDOW, "buy_window"),
        month_window,
        week_window,
    )
    sell_window = _resolve_contract_window(
        sell_timeframe,
        _row_numeric(row, V2_SELL_WINDOW, "sell_window"),
        month_window,
        week_window,
    )

    mode = _row_text(row, V2_CONTRACT_MODE, "mode")
    if not mode and buy_timeframe and sell_timeframe:
        mode = f"{buy_timeframe}_buy_{sell_timeframe}_sell"
    mode_label = None
    if buy_timeframe or sell_timeframe:
        mode_label = MODE_LABELS.get(
            str(mode or ""),
            f"{TIMEFRAME_LABELS.get(str(buy_timeframe or ''), '기준없음')}매수 / {TIMEFRAME_LABELS.get(str(sell_timeframe or ''), '기준없음')}매도",
        )

    return {
        "mode": mode,
        "mode_label": mode_label,
        "buy_timeframe": buy_timeframe,
        "sell_timeframe": sell_timeframe,
        "buy_window": buy_window,
        "sell_window": sell_window,
        "buy_label": TIMEFRAME_LABELS.get(str(buy_timeframe or "")),
        "sell_label": TIMEFRAME_LABELS.get(str(sell_timeframe or "")),
        "buy_short_label": TIMEFRAME_SHORT_LABELS.get(str(buy_timeframe or "")),
        "sell_short_label": TIMEFRAME_SHORT_LABELS.get(str(sell_timeframe or "")),
    }


def v2_ma_context(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    month_window = _row_numeric(row, "v2_month_window", "monthly_optimal_window", "monthly_window")
    week_window = _row_numeric(row, "v2_week_window", "weekly_optimal_window", "weekly_window")
    month_ma = _row_numeric(row, "v2_month_ma", "monthly_ma_price")
    week_ma = _row_numeric(row, "v2_week_ma", "weekly_ma_price")
    month_dist = _row_numeric(row, V2_MONTH_DISPLAY_DIST, "v2_month_live_dist", "v2_month_period_dist", "monthly_dist")
    week_dist = _row_numeric(row, V2_WEEK_DISPLAY_DIST, "v2_week_live_dist", "v2_week_period_dist", "weekly_dist")
    return {
        "month_window": None if month_window is None else int(month_window),
        "week_window": None if week_window is None else int(week_window),
        "month_ma": month_ma,
        "week_ma": week_ma,
        "month_dist": month_dist,
        "week_dist": week_dist,
        "month_buy_ready": bool(row.get("v2_month_buy_ready", row.get("monthly_main_ok", False))),
        "month_buy_cross": bool(row.get("v2_month_buy_cross", False)),
        "month_sell_cross": bool(row.get("v2_month_sell_cross", False)),
        "month_above_maintain": bool(row.get("v2_month_above_maintain", False)),
        "week_sell_trigger": bool(row.get("v2_week_sell_trigger", False)),
        "week_sell_watch": bool(row.get("v2_week_sell_watch", False)),
    }
