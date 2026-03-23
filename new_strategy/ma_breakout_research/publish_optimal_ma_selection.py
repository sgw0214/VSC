from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from new_strategy.ma_breakout_research.validate_optimal_ma_publish import (
    validate_selection,
)
from new_strategy.optimal_ma_publish_contract import (
    OPTIMAL_MA_ALL_META_PATH,
    OPTIMAL_MA_ALL_README_PATH,
    OPTIMAL_MA_ALL_SCHEMA_VERSION,
    OPTIMAL_MA_ALL_SELECTION_PATH,
    OPTIMAL_MA_README_PATH,
    OPTIMAL_MA_REQUIRED_COLUMNS,
    OPTIMAL_MA_SCHEMA_VERSION,
    OPTIMAL_MA_SELECTION_COLUMNS,
    OPTIMAL_MA_SELECTION_PATH,
    OPTIMAL_MA_META_PATH,
    OPTIMAL_MA_PUBLISHED_DIR,
)
from new_strategy.paths import output_path


RAW_PATH = output_path("ma_breakout_research", "all_action_modes_returns_by_stock.csv")
PUBLISHED_DIR = OPTIMAL_MA_PUBLISHED_DIR
SELECTION_PATH = OPTIMAL_MA_SELECTION_PATH
META_PATH = OPTIMAL_MA_META_PATH
README_PATH = OPTIMAL_MA_README_PATH
ALL_SELECTION_PATH = OPTIMAL_MA_ALL_SELECTION_PATH
ALL_META_PATH = OPTIMAL_MA_ALL_META_PATH
ALL_README_PATH = OPTIMAL_MA_ALL_README_PATH


def _action_mode_priority(series: pd.Series) -> pd.Series:
    return series.map({"native_timeframe_close": 0, "daily_close_action": 1}).fillna(9).astype(int)


def _timeframe_priority(series: pd.Series) -> pd.Series:
    return series.map({"monthly": 0, "weekly": 1, "daily": 2}).fillna(9).astype(int)


def _filter_allowed_action_modes(df: pd.DataFrame, allowed_action_modes: tuple[str, ...] | None) -> pd.DataFrame:
    if not allowed_action_modes:
        return df
    allowed = {str(x).strip().lower() for x in allowed_action_modes}
    return df.loc[df["action_mode"].astype(str).str.lower().isin(allowed)].copy()


def _filter_min_window(df: pd.DataFrame, *, min_window: int = 2) -> pd.DataFrame:
    return df.loc[pd.to_numeric(df["ma_window"], errors="coerce").ge(min_window)].copy()


def load_raw_results(path: Path = RAW_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def select_monthly_weekly_optimal(
    df: pd.DataFrame,
    *,
    allowed_action_modes: tuple[str, ...] | None = ("native_timeframe_close",),
) -> pd.DataFrame:
    scoped = _filter_allowed_action_modes(df, allowed_action_modes)
    scoped = _filter_min_window(scoped, min_window=2)
    scoped = scoped.loc[scoped["ma_timeframe"].astype(str).str.lower().isin({"monthly", "weekly"})].copy()
    if scoped.empty:
        return pd.DataFrame(columns=OPTIMAL_MA_SELECTION_COLUMNS)

    scoped["action_mode_priority"] = _action_mode_priority(scoped["action_mode"])
    scoped["timeframe_priority"] = _timeframe_priority(scoped["ma_timeframe"])
    ranked = scoped.sort_values(
        [
            "code",
            "total_return",
            "max_drawdown",
            "completed_trade_count",
            "annualized_return",
            "win_rate",
            "action_mode_priority",
            "timeframe_priority",
            "ma_window",
        ],
        ascending=[True, False, False, False, False, False, True, True, True],
    )
    selected = ranked.groupby("code", as_index=False).head(1).reset_index(drop=True)
    out = selected[OPTIMAL_MA_SELECTION_COLUMNS].copy()
    out["selection_scope"] = "monthly_weekly"
    out["published_source"] = "all_action_modes_returns_by_stock.csv"
    return out


def select_all_timeframe_optimal(
    df: pd.DataFrame,
    *,
    allowed_action_modes: tuple[str, ...] | None = ("native_timeframe_close",),
) -> pd.DataFrame:
    scoped = _filter_allowed_action_modes(df, allowed_action_modes)
    scoped = _filter_min_window(scoped, min_window=2)
    if scoped.empty:
        return pd.DataFrame(columns=OPTIMAL_MA_SELECTION_COLUMNS)

    scoped["action_mode_priority"] = _action_mode_priority(scoped["action_mode"])
    scoped["timeframe_priority"] = _timeframe_priority(scoped["ma_timeframe"])
    ranked = scoped.sort_values(
        [
            "code",
            "total_return",
            "max_drawdown",
            "completed_trade_count",
            "annualized_return",
            "win_rate",
            "action_mode_priority",
            "timeframe_priority",
            "ma_window",
        ],
        ascending=[True, False, False, False, False, False, True, True, True],
    )
    selected = ranked.groupby(["code", "ma_timeframe"], as_index=False).head(1).reset_index(drop=True)
    out = selected[OPTIMAL_MA_SELECTION_COLUMNS].copy()
    out["selection_scope"] = "all_timeframes"
    out["published_source"] = "all_action_modes_returns_by_stock.csv"
    return out


def build_readme(selection_df: pd.DataFrame) -> str:
    tf_counts = selection_df["ma_timeframe"].value_counts().to_dict() if not selection_df.empty else {}
    mode_counts = selection_df["action_mode"].value_counts().to_dict() if not selection_df.empty else {}
    lines = [
        "# Optimal MA Monthly/Weekly Publish",
        "",
        "## Purpose",
        "- live strategy and dashboard consumption only",
        "- monthly/weekly optimal MA selection",
        "- generated from all_action_modes_returns_by_stock.csv",
        "",
        "## Selection Rule",
        "- scope: monthly, weekly",
        "- exclude: ma_window = 1",
        "- ranking: total_return > max_drawdown > completed_trade_count > annualized_return > win_rate",
        "- action mode: native_timeframe_close only",
        "- tie-break: monthly > weekly > smaller window",
        "",
        "## Counts",
        f"- rows: {len(selection_df):,}",
        f"- unique stocks: {selection_df['code'].nunique() if not selection_df.empty else 0:,}",
        "",
        "## Timeframe Mix",
    ]
    if tf_counts:
        for key, value in tf_counts.items():
            lines.append(f"- {key}: {int(value)}")
    else:
        lines.append("- no rows")
    lines += ["", "## Action Mode Mix"]
    if mode_counts:
        for key, value in mode_counts.items():
            lines.append(f"- {key}: {int(value)}")
    else:
        lines.append("- no rows")
    lines.append("")
    return "\n".join(lines)


def build_all_timeframe_readme(selection_df: pd.DataFrame) -> str:
    tf_counts = selection_df["ma_timeframe"].value_counts().to_dict() if not selection_df.empty else {}
    mode_counts = selection_df["action_mode"].value_counts().to_dict() if not selection_df.empty else {}
    lines = [
        "# Optimal MA All-Timeframe Publish",
        "",
        "## Purpose",
        "- chart display consumption only",
        "- one optimal MA per stock per timeframe",
        "- generated from all_action_modes_returns_by_stock.csv",
        "",
        "## Selection Rule",
        "- scope: daily, weekly, monthly",
        "- one best row per code + ma_timeframe",
        "- exclude: ma_window = 1",
        "- ranking: total_return > max_drawdown > completed_trade_count > annualized_return > win_rate",
        "- action mode: native_timeframe_close only",
        "- tie-break: monthly > weekly > daily > smaller window",
        "",
        "## Counts",
        f"- rows: {len(selection_df):,}",
        f"- unique stocks: {selection_df['code'].nunique() if not selection_df.empty else 0:,}",
        "",
        "## Timeframe Mix",
    ]
    if tf_counts:
        for key, value in tf_counts.items():
            lines.append(f"- {key}: {int(value)}")
    else:
        lines.append("- no rows")
    lines += ["", "## Action Mode Mix"]
    if mode_counts:
        for key, value in mode_counts.items():
            lines.append(f"- {key}: {int(value)}")
    else:
        lines.append("- no rows")
    lines.append("")
    return "\n".join(lines)


def publish(
    path: Path = RAW_PATH,
    *,
    allowed_action_modes: tuple[str, ...] | None = ("native_timeframe_close",),
) -> None:
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    raw = load_raw_results(path)
    selection = select_monthly_weekly_optimal(raw, allowed_action_modes=allowed_action_modes)
    selection_all = select_all_timeframe_optimal(raw, allowed_action_modes=allowed_action_modes)
    selection.to_csv(SELECTION_PATH, index=False, encoding="utf-8-sig")
    selection_all.to_csv(ALL_SELECTION_PATH, index=False, encoding="utf-8-sig")
    missing = [col for col in OPTIMAL_MA_REQUIRED_COLUMNS if col not in selection.columns]
    if missing:
        raise ValueError(f"publish output missing columns: {missing}")
    missing_all = [col for col in OPTIMAL_MA_REQUIRED_COLUMNS if col not in selection_all.columns]
    if missing_all:
        raise ValueError(f"publish output missing columns (all timeframe): {missing_all}")

    meta = {
        "published_at": datetime.now().isoformat(timespec="seconds"),
        "schema_version": OPTIMAL_MA_SCHEMA_VERSION,
        "source_path": str(path),
        "selection_path": str(SELECTION_PATH),
        "selection_scope": "monthly_weekly",
        "row_count": int(len(selection)),
        "stock_count": int(selection["code"].nunique()) if not selection.empty else 0,
        "selection_rule": "native_timeframe_close only; exclude ma_window=1; total_return > max_drawdown > completed_trade_count > annualized_return > win_rate > timeframe_priority > ma_window",
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    README_PATH.write_text(build_readme(selection), encoding="utf-8")
    meta_all = {
        "published_at": datetime.now().isoformat(timespec="seconds"),
        "schema_version": OPTIMAL_MA_ALL_SCHEMA_VERSION,
        "source_path": str(path),
        "selection_path": str(ALL_SELECTION_PATH),
        "selection_scope": "all_timeframes",
        "row_count": int(len(selection_all)),
        "stock_count": int(selection_all["code"].nunique()) if not selection_all.empty else 0,
        "selection_rule": "native_timeframe_close only; exclude ma_window=1; per code+timeframe: total_return > max_drawdown > completed_trade_count > annualized_return > win_rate > timeframe_priority > ma_window",
    }
    ALL_META_PATH.write_text(json.dumps(meta_all, ensure_ascii=False, indent=2), encoding="utf-8")
    ALL_README_PATH.write_text(build_all_timeframe_readme(selection_all), encoding="utf-8")
    validate_selection(SELECTION_PATH)
    validate_selection(ALL_SELECTION_PATH, expected_scope="all_timeframes", expected_schema=OPTIMAL_MA_ALL_SCHEMA_VERSION)
    print(f"[done] published optimal MA selection -> {SELECTION_PATH}")
    print(f"[done] published chart optimal MA selection -> {ALL_SELECTION_PATH}")


if __name__ == "__main__":
    publish()
