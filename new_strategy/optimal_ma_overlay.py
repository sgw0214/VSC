from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from new_strategy.ma_breakout_research.backtest_ma_breakout_modes import (
    _map_period_ma_to_daily,
    _rolling_mean,
    build_completed_period_frame,
)
from new_strategy.optimal_ma_publish_contract import (
    ACTION_MODE_LABELS,
    OPTIMAL_MA_META_PATH,
    OPTIMAL_MA_REQUIRED_COLUMNS,
    OPTIMAL_MA_SCHEMA_VERSION,
    OPTIMAL_MA_SELECTION_COLUMNS,
    OPTIMAL_MA_SELECTION_PATH,
    TIMEFRAME_LABELS,
    normalize_optimal_ma_code,
)
from new_strategy.paths import data_path, output_path, strategy_output_path


APP_DIR = strategy_output_path()
PRICE_PANEL_PATH = data_path("price_panel.csv")
MA_RAW_PATH = output_path("ma_breakout_research", "all_action_modes_returns_by_stock.csv")
OVERLAY_SNAPSHOT_PATH = APP_DIR / "optimal_ma_monthly_weekly_snapshot.pkl"
MA_SELECTION_PATH = OPTIMAL_MA_SELECTION_PATH


def _action_mode_priority(series: pd.Series) -> pd.Series:
    return series.map({"native_timeframe_close": 0, "daily_close_action": 1}).fillna(9).astype(int)


def _timeframe_priority(series: pd.Series) -> pd.Series:
    return series.map({"monthly": 0, "weekly": 1, "daily": 2}).fillna(9).astype(int)


def _read_selection_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).map(normalize_optimal_ma_code)
    return df


def _published_schema_ready(
    selection_path: Path = OPTIMAL_MA_SELECTION_PATH,
    meta_path: Path = OPTIMAL_MA_META_PATH,
) -> bool:
    if not selection_path.exists() or not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return str(meta.get("schema_version") or "") == OPTIMAL_MA_SCHEMA_VERSION


def _selection_from_raw(df: pd.DataFrame, allowed_timeframes: tuple[str, ...]) -> pd.DataFrame:
    allowed = {str(x).strip().lower() for x in allowed_timeframes}
    scoped = df.loc[df["ma_timeframe"].astype(str).str.lower().isin(allowed)].copy()
    scoped = scoped.loc[pd.to_numeric(scoped["ma_window"], errors="coerce").ge(2)].copy()
    if scoped.empty:
        return scoped
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
    return selected[OPTIMAL_MA_SELECTION_COLUMNS].copy()


def load_optimal_ma_selection(
    path: Path = OPTIMAL_MA_SELECTION_PATH,
    allowed_timeframes: tuple[str, ...] = ("monthly", "weekly"),
) -> pd.DataFrame:
    selection_path = path if _published_schema_ready(path, OPTIMAL_MA_META_PATH) else MA_RAW_PATH
    df = _read_selection_frame(selection_path)
    if df.empty:
        return df
    if all(col in df.columns for col in OPTIMAL_MA_REQUIRED_COLUMNS):
        out = df[OPTIMAL_MA_SELECTION_COLUMNS].copy()
    else:
        out = _selection_from_raw(df, allowed_timeframes)
    out["code"] = out["code"].astype(str).map(normalize_optimal_ma_code)
    return out


def _load_price_history_for_codes(price_path: Path, codes: set[str]) -> pd.DataFrame:
    if not price_path.exists() or not codes:
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    reader = pd.read_csv(
        price_path,
        usecols=["date", "code", "name", "close"],
        dtype={"code": str},
        low_memory=False,
        chunksize=300_000,
    )
    for chunk in reader:
        chunk["code"] = chunk["code"].astype(str).map(normalize_optimal_ma_code)
        chunk = chunk.loc[chunk["code"].isin(codes)].copy()
        if chunk.empty:
            continue
        chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce")
        chunk["close"] = pd.to_numeric(chunk["close"], errors="coerce")
        chunk = chunk.dropna(subset=["date", "close"])
        if not chunk.empty:
            frames.append(chunk)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["code", "date"]).reset_index(drop=True)


def _latest_valid(values: np.ndarray) -> int | None:
    valid = np.flatnonzero(np.isfinite(values))
    if valid.size == 0:
        return None
    return int(valid[-1])


def _build_row_for_code(code: str, grp: pd.DataFrame, selected: dict[str, Any], today: pd.Timestamp) -> dict[str, Any]:
    grp = grp.sort_values("date").reset_index(drop=True)
    code = normalize_optimal_ma_code(code)
    if selected.get("name"):
        name = str(selected["name"])
    elif grp["name"].notna().any():
        name = str(grp["name"].dropna().iloc[-1])
    else:
        name = code

    timeframe = str(selected["ma_timeframe"]).strip().lower()
    action_mode = str(selected["action_mode"]).strip()
    window = int(selected["ma_window"])
    dates = grp["date"].to_numpy()
    prices = grp["close"].to_numpy(dtype=float)
    latest_date = pd.Timestamp(dates[-1]).date().isoformat()
    latest_close = float(prices[-1])

    period_df = build_completed_period_frame(grp[["date", "close"]], timeframe, today=today)
    ma_value = np.nan
    basis_price = np.nan
    basis_date = pd.NaT
    ok_value: bool | float = np.nan
    basis_label = "-"
    rule_text = "최적 MA 기준선을 계산할 수 없습니다."

    if not period_df.empty:
        period_dates = period_df["decision_date"].to_numpy()
        period_prices = period_df["close"].to_numpy(dtype=float)
        period_ma = _rolling_mean(period_prices, window)

        if action_mode == "daily_close_action":
            mapped_ma = _map_period_ma_to_daily(dates, period_dates, period_ma)
            idx = _latest_valid(mapped_ma)
            basis_label = "일별 종가"
            if idx is not None:
                ma_value = float(mapped_ma[idx])
                basis_price = float(prices[idx])
                basis_date = pd.Timestamp(dates[idx])
                ok_value = bool(basis_price > ma_value)
        else:
            idx = _latest_valid(period_ma)
            basis_label = f"{TIMEFRAME_LABELS.get(timeframe, timeframe)} 종가"
            if idx is not None:
                ma_value = float(period_ma[idx])
                basis_price = float(period_prices[idx])
                basis_date = pd.Timestamp(period_dates[idx])
                ok_value = bool(basis_price > ma_value)

        if pd.notna(ma_value):
            tf_label = TIMEFRAME_LABELS.get(timeframe, timeframe)
            rule_text = f"{basis_label}가 {tf_label} {window}이평 {ma_value:,.0f}원 위면 매수 우세, 아래면 매도 경계입니다."

    return {
        "code": code,
        "name": name,
        "latest_date": latest_date,
        "latest_close": latest_close,
        "optimal_ma_timeframe": timeframe,
        "optimal_ma_timeframe_ko": TIMEFRAME_LABELS.get(timeframe, timeframe),
        "optimal_ma_action_mode": action_mode,
        "optimal_ma_action_mode_ko": ACTION_MODE_LABELS.get(action_mode, action_mode),
        "optimal_ma_window": window,
        "optimal_ma_ok": ok_value,
        "optimal_ma_signal_ko": "매수 우세" if ok_value is True else ("매도 경계" if ok_value is False else "데이터 없음"),
        "optimal_ma_basis_label": basis_label,
        "optimal_ma_basis_price": basis_price,
        "optimal_ma_basis_date": basis_date.isoformat() if pd.notna(basis_date) else "",
        "optimal_ma_line_price": ma_value,
        "optimal_ma_rule_text": rule_text,
        "optimal_ma_total_return": selected.get("total_return"),
        "optimal_ma_buy_hold_return": selected.get("buy_hold_return"),
        "optimal_ma_excess_return": selected.get("excess_return"),
        "optimal_ma_annualized_return": selected.get("annualized_return"),
        "optimal_ma_max_drawdown": selected.get("max_drawdown"),
        "optimal_ma_win_rate": selected.get("win_rate"),
        "optimal_ma_completed_trade_count": selected.get("completed_trade_count"),
        "optimal_ma_trade_count": selected.get("trade_count"),
        "optimal_ma_exposure_ratio": selected.get("exposure_ratio"),
    }


def build_latest_optimal_ma_snapshot(
    price_path: Path = PRICE_PANEL_PATH,
    selection_path: Path = OPTIMAL_MA_SELECTION_PATH,
    snapshot_path: Path = OVERLAY_SNAPSHOT_PATH,
) -> pd.DataFrame:
    selection_df = load_optimal_ma_selection(selection_path, allowed_timeframes=("monthly", "weekly"))
    if selection_df.empty:
        return selection_df
    codes = set(selection_df["code"].astype(str).map(normalize_optimal_ma_code))
    price_df = _load_price_history_for_codes(price_path, codes)
    if price_df.empty:
        return pd.DataFrame()
    today = pd.Timestamp(price_df["date"].max())
    selection_map = selection_df.set_index("code").to_dict(orient="index")
    rows = [
        _build_row_for_code(code, grp, selection_map[code], today)
        for code, grp in price_df.groupby("code", sort=False)
        if code in selection_map
    ]
    out = pd.DataFrame(rows)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_pickle(snapshot_path)
    return out


def load_latest_optimal_ma_snapshot(
    price_path: Path = PRICE_PANEL_PATH,
    selection_path: Path = OPTIMAL_MA_SELECTION_PATH,
    snapshot_path: Path = OVERLAY_SNAPSHOT_PATH,
) -> pd.DataFrame:
    needs_rebuild = not snapshot_path.exists()
    if not needs_rebuild:
        snapshot_mtime = snapshot_path.stat().st_mtime
        needs_rebuild = (
            (price_path.exists() and snapshot_mtime < price_path.stat().st_mtime)
            or (selection_path.exists() and snapshot_mtime < selection_path.stat().st_mtime)
        )
    if needs_rebuild:
        return build_latest_optimal_ma_snapshot(price_path, selection_path, snapshot_path)
    try:
        df = pd.read_pickle(snapshot_path)
    except Exception:
        return build_latest_optimal_ma_snapshot(price_path, selection_path, snapshot_path)
    if not df.empty:
        df["code"] = df["code"].astype(str).map(normalize_optimal_ma_code)
    return df


def optimal_ma_alignment(signal: Any, optimal_ma_ok: Any) -> str:
    if pd.isna(optimal_ma_ok):
        return "데이터 없음"
    signal_text = str(signal or "").strip().upper()
    if signal_text in {"SELL", "SELL_WATCH"}:
        return "일치" if (not bool(optimal_ma_ok)) else "불일치"
    return "일치" if bool(optimal_ma_ok) else "불일치"


def optimal_ma_soft_delta(signal: Any, optimal_ma_ok: Any, magnitude: float = 0.02) -> float:
    alignment = optimal_ma_alignment(signal, optimal_ma_ok)
    if alignment == "일치":
        return float(magnitude)
    if alignment == "불일치":
        return float(-magnitude)
    return 0.0
