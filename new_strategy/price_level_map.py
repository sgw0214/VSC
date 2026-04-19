from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from new_strategy.optimal_ma_publish_contract import OPTIMAL_MA_ALL_SELECTION_PATH
from new_strategy.paths import data_path


PRICE_PANEL_PATH = data_path("price_panel.csv")
DEFAULT_BUY_STOP_PCT = -0.10
DEFAULT_MA_STOP_PCT = -0.05


def normalize_price_level_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    return text.zfill(6) if text.isdigit() else text


@lru_cache(maxsize=4)
def _load_optimal_ma_all_cached(path_str: str, mtime: float) -> pd.DataFrame:
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).map(normalize_price_level_code)
    df["ma_timeframe"] = df["ma_timeframe"].astype(str).str.lower()
    return df


def optimal_ma_window_for_code(code: Any, timeframe: str) -> int | None:
    path = OPTIMAL_MA_ALL_SELECTION_PATH
    df = _load_optimal_ma_all_cached(str(path), path.stat().st_mtime if path.exists() else 0.0)
    if df.empty:
        return None
    norm = normalize_price_level_code(code)
    sub = df[(df["code"] == norm) & (df["ma_timeframe"] == str(timeframe).strip().lower())]
    if sub.empty:
        return None
    window = pd.to_numeric(pd.Series([sub.iloc[-1].get("ma_window")]), errors="coerce").iloc[0]
    return None if pd.isna(window) else int(window)


@lru_cache(maxsize=256)
def _load_code_close_history_cached(path_str: str, mtime: float, code: str) -> pd.DataFrame:
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame(columns=["date", "close"])

    frames: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        path,
        usecols=["date", "code", "close"],
        dtype={"code": str},
        chunksize=250000,
        low_memory=False,
    ):
        chunk["code"] = chunk["code"].astype(str).map(normalize_price_level_code)
        part = chunk[chunk["code"] == code][["date", "close"]]
        if not part.empty:
            frames.append(part)

    if not frames:
        return pd.DataFrame(columns=["date", "close"])

    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return df


def latest_period_ma_from_price_panel(code: Any, timeframe: str, window: int | None) -> float | None:
    norm = normalize_price_level_code(code)
    if not norm or window is None or window <= 0:
        return None
    path = PRICE_PANEL_PATH
    history = _load_code_close_history_cached(str(path), path.stat().st_mtime if path.exists() else 0.0, norm)
    if history.empty:
        return None
    alias_map = {"weekly": "W-FRI", "monthly": "M", "daily": "D"}
    alias = alias_map.get(str(timeframe).strip().lower())
    if alias is None:
        return None
    series = history.set_index("date")["close"].resample(alias).last().dropna()
    if series.empty:
        return None
    ma = series.rolling(window=int(window), min_periods=1).mean().iloc[-1]
    return None if pd.isna(ma) else float(ma)


def build_price_level_map(
    code: Any,
    *,
    buy_price: float | None = None,
    buy_stop_pct: float = DEFAULT_BUY_STOP_PCT,
    ma_stop_pct: float = DEFAULT_MA_STOP_PCT,
) -> dict[str, float | int | None]:
    norm = normalize_price_level_code(code)
    weekly_window = optimal_ma_window_for_code(norm, "weekly")
    monthly_window = optimal_ma_window_for_code(norm, "monthly")
    weekly_ma_price = latest_period_ma_from_price_panel(norm, "weekly", weekly_window)
    monthly_ma_price = latest_period_ma_from_price_panel(norm, "monthly", monthly_window)
    buy_stop_price = buy_price * (1.0 + buy_stop_pct) if buy_price is not None else None
    weekly_ma_stop_price = weekly_ma_price * (1.0 + ma_stop_pct) if weekly_ma_price is not None else None
    monthly_ma_stop_price = monthly_ma_price * (1.0 + ma_stop_pct) if monthly_ma_price is not None else None
    return {
        "code": norm,
        "buy_price": buy_price,
        "buy_stop_pct": buy_stop_pct,
        "buy_stop_price": buy_stop_price,
        "weekly_window": weekly_window,
        "weekly_ma_price": weekly_ma_price,
        "weekly_ma_stop_pct": ma_stop_pct,
        "weekly_ma_stop_price": weekly_ma_stop_price,
        "monthly_window": monthly_window,
        "monthly_ma_price": monthly_ma_price,
        "monthly_ma_stop_pct": ma_stop_pct,
        "monthly_ma_stop_price": monthly_ma_stop_price,
    }


def build_contract_price_level_map(
    code: Any,
    *,
    current_price: float | None = None,
    buy_price: float | None = None,
    buy_stop_pct: float = DEFAULT_BUY_STOP_PCT,
    ma_stop_pct: float = DEFAULT_MA_STOP_PCT,
    buy_timeframe: str | None = None,
    buy_window: int | None = None,
    sell_timeframe: str | None = None,
    sell_window: int | None = None,
    buy_ma_price_override: float | None = None,
    sell_ma_price_override: float | None = None,
) -> dict[str, float | int | None | str]:
    norm = normalize_price_level_code(code)
    buy_contract_ma_price = buy_ma_price_override
    if buy_contract_ma_price is None or pd.isna(buy_contract_ma_price):
        buy_contract_ma_price = latest_period_ma_from_price_panel(norm, str(buy_timeframe or "").strip().lower(), buy_window)
    sell_contract_ma_price = sell_ma_price_override
    if sell_contract_ma_price is None or pd.isna(sell_contract_ma_price):
        sell_contract_ma_price = latest_period_ma_from_price_panel(norm, str(sell_timeframe or "").strip().lower(), sell_window)
    buy_stop_price = buy_price * (1.0 + buy_stop_pct) if buy_price is not None else None
    buy_contract_stop_price = buy_contract_ma_price * (1.0 + ma_stop_pct) if buy_contract_ma_price is not None else None
    sell_contract_stop_price = sell_contract_ma_price * (1.0 + ma_stop_pct) if sell_contract_ma_price is not None else None
    buy_contract_dist = None
    sell_contract_dist = None
    if current_price is not None and buy_contract_ma_price not in {None, 0}:
        buy_contract_dist = float(current_price) / float(buy_contract_ma_price) - 1.0
    if current_price is not None and sell_contract_ma_price not in {None, 0}:
        sell_contract_dist = float(current_price) / float(sell_contract_ma_price) - 1.0
    return {
        "code": norm,
        "buy_price": buy_price,
        "buy_stop_pct": buy_stop_pct,
        "buy_stop_price": buy_stop_price,
        "buy_timeframe": str(buy_timeframe or "").strip().lower() or None,
        "buy_window": None if buy_window is None else int(buy_window),
        "buy_contract_ma_price": buy_contract_ma_price,
        "buy_contract_stop_price": buy_contract_stop_price,
        "buy_contract_dist": buy_contract_dist,
        "sell_timeframe": str(sell_timeframe or "").strip().lower() or None,
        "sell_window": None if sell_window is None else int(sell_window),
        "sell_contract_ma_price": sell_contract_ma_price,
        "sell_contract_stop_price": sell_contract_stop_price,
        "sell_contract_dist": sell_contract_dist,
    }
