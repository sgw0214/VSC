from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from new_strategy.paths import data_path, strategy_output_path

PRICE_PANEL_PATH = data_path("price_panel.csv")
PRICE_PANEL_META_PATH = data_path("price_panel_meta.json")
PRICE_SNAPSHOT_PATH = strategy_output_path("price_panel_latest_snapshot.csv")
PRICE_SNAPSHOT_META_PATH = strategy_output_path("price_panel_latest_snapshot_meta.json")
PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH = strategy_output_path("price_panel_industry_base.pkl")
PRICE_PANEL_INDUSTRY_SNAPSHOT_META_PATH = strategy_output_path("price_panel_industry_base_meta.json")
PRICE_SNAPSHOT_REQUIRED_COLS = ["date", "code", "name", "close", "volume", "market_cap", "industry"]
PRICE_PANEL_INDUSTRY_REQUIRED_COLS = ["date", "code", "industry", "close"]


def _file_stamp(path: Path) -> tuple[int, int]:
    if not path.exists():
        return (0, 0)
    stat = path.stat()
    return (int(stat.st_mtime_ns), int(stat.st_size))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _source_signature() -> dict[str, Any]:
    bounds = _read_json(PRICE_PANEL_META_PATH).get("bounds", {})
    mtime_ns, size = _file_stamp(PRICE_PANEL_PATH)
    return {
        "source_path": str(PRICE_PANEL_PATH),
        "source_mtime_ns": mtime_ns,
        "source_size": size,
        "date_max": str(bounds.get("date_max") or ""),
        "rows": int(bounds.get("rows") or 0),
        "codes": int(bounds.get("codes") or 0),
    }


def _snapshot_signature() -> dict[str, Any]:
    return _read_json(PRICE_SNAPSHOT_META_PATH)


def _industry_snapshot_signature() -> dict[str, Any]:
    return _read_json(PRICE_PANEL_INDUSTRY_SNAPSHOT_META_PATH)


def price_snapshot_is_current() -> bool:
    if not PRICE_SNAPSHOT_PATH.exists() or not PRICE_SNAPSHOT_META_PATH.exists():
        return False
    source = _source_signature()
    snap = _snapshot_signature()
    if not source["source_mtime_ns"] or not source["source_size"]:
        return False
    return (
        int(snap.get("source_mtime_ns") or 0) == int(source["source_mtime_ns"])
        and int(snap.get("source_size") or 0) == int(source["source_size"])
        and str(snap.get("date_max") or "") == str(source["date_max"])
    )


def price_panel_industry_snapshot_is_current() -> bool:
    if not PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH.exists() or not PRICE_PANEL_INDUSTRY_SNAPSHOT_META_PATH.exists():
        return False
    source = _source_signature()
    snap = _industry_snapshot_signature()
    if not source["source_mtime_ns"] or not source["source_size"]:
        return False
    return (
        int(snap.get("source_mtime_ns") or 0) == int(source["source_mtime_ns"])
        and int(snap.get("source_size") or 0) == int(source["source_size"])
        and str(snap.get("date_max") or "") == str(source["date_max"])
    )


def _normalize_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=PRICE_SNAPSHOT_REQUIRED_COLS)
    out = df.copy()
    for col in PRICE_SNAPSHOT_REQUIRED_COLS:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[PRICE_SNAPSHOT_REQUIRED_COLS].copy()
    out["code"] = out["code"].astype(str).str.zfill(6)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce")
    out["market_cap"] = pd.to_numeric(out["market_cap"], errors="coerce")
    out["industry"] = out["industry"].astype("string")
    return out


def _normalize_industry_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=PRICE_PANEL_INDUSTRY_REQUIRED_COLS)
    out = df.copy()
    for col in PRICE_PANEL_INDUSTRY_REQUIRED_COLS:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[PRICE_PANEL_INDUSTRY_REQUIRED_COLS].copy()
    out["code"] = out["code"].astype(str).str.zfill(6)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["industry"] = out["industry"].astype("string")
    out = out.dropna(subset=["date", "close"]).sort_values(["code", "date"]).reset_index(drop=True)
    return out


def read_price_latest_snapshot(*, allow_refresh: bool = False) -> pd.DataFrame:
    if price_snapshot_is_current():
        try:
            return _normalize_snapshot(
                pd.read_csv(
                    PRICE_SNAPSHOT_PATH,
                    usecols=PRICE_SNAPSHOT_REQUIRED_COLS,
                    dtype={"code": str},
                    low_memory=False,
                )
            )
        except Exception:
            if not allow_refresh:
                return pd.DataFrame(columns=PRICE_SNAPSHOT_REQUIRED_COLS)
    elif PRICE_SNAPSHOT_PATH.exists() and not allow_refresh:
        try:
            return _normalize_snapshot(
                pd.read_csv(
                    PRICE_SNAPSHOT_PATH,
                    usecols=PRICE_SNAPSHOT_REQUIRED_COLS,
                    dtype={"code": str},
                    low_memory=False,
                )
            )
        except Exception:
            return pd.DataFrame(columns=PRICE_SNAPSHOT_REQUIRED_COLS)

    if not allow_refresh:
        return pd.DataFrame(columns=PRICE_SNAPSHOT_REQUIRED_COLS)
    return refresh_price_latest_snapshot(force=True)


def read_price_panel_industry_snapshot(*, allow_refresh: bool = False) -> pd.DataFrame:
    if price_panel_industry_snapshot_is_current():
        try:
            return _normalize_industry_snapshot(pd.read_pickle(PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH))
        except Exception:
            if not allow_refresh:
                return pd.DataFrame(columns=PRICE_PANEL_INDUSTRY_REQUIRED_COLS)
    elif PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH.exists() and not allow_refresh:
        try:
            return _normalize_industry_snapshot(pd.read_pickle(PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH))
        except Exception:
            return pd.DataFrame(columns=PRICE_PANEL_INDUSTRY_REQUIRED_COLS)

    if not allow_refresh:
        return pd.DataFrame(columns=PRICE_PANEL_INDUSTRY_REQUIRED_COLS)
    return refresh_price_panel_industry_snapshot(force=True)


def refresh_price_latest_snapshot(*, force: bool = False) -> pd.DataFrame:
    if not force and price_snapshot_is_current():
        return read_price_latest_snapshot(allow_refresh=False)
    if not PRICE_PANEL_PATH.exists():
        return pd.DataFrame(columns=PRICE_SNAPSHOT_REQUIRED_COLS)
    df = pd.read_csv(
        PRICE_PANEL_PATH,
        usecols=PRICE_SNAPSHOT_REQUIRED_COLS,
        dtype={"code": str},
        low_memory=False,
    )
    if df.empty:
        return pd.DataFrame(columns=PRICE_SNAPSHOT_REQUIRED_COLS)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["market_cap"] = pd.to_numeric(df["market_cap"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values(["code", "date"])
    latest = df.groupby("code", as_index=False).tail(1).copy()
    latest["code"] = latest["code"].astype(str).str.zfill(6)
    latest = _normalize_snapshot(latest)
    PRICE_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    latest.to_csv(PRICE_SNAPSHOT_PATH, index=False, encoding="utf-8-sig")
    payload = {
        **_source_signature(),
        "snapshot_path": str(PRICE_SNAPSHOT_PATH),
        "snapshot_rows": int(len(latest)),
        "snapshot_codes": int(latest["code"].nunique()),
        "snapshot_built_at": datetime.now().isoformat(timespec="seconds"),
    }
    PRICE_SNAPSHOT_META_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return latest


def refresh_price_panel_industry_snapshot(*, force: bool = False) -> pd.DataFrame:
    if not force and price_panel_industry_snapshot_is_current():
        return read_price_panel_industry_snapshot(allow_refresh=False)
    if not PRICE_PANEL_PATH.exists():
        return pd.DataFrame(columns=PRICE_PANEL_INDUSTRY_REQUIRED_COLS)
    df = pd.read_csv(
        PRICE_PANEL_PATH,
        usecols=PRICE_PANEL_INDUSTRY_REQUIRED_COLS,
        dtype={"code": str},
        low_memory=False,
    )
    if df.empty:
        return pd.DataFrame(columns=PRICE_PANEL_INDUSTRY_REQUIRED_COLS)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values(["code", "date"]).reset_index(drop=True)
    latest = _normalize_industry_snapshot(df)
    PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    latest.to_pickle(PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH)
    payload = {
        **_source_signature(),
        "snapshot_path": str(PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH),
        "snapshot_rows": int(len(latest)),
        "snapshot_codes": int(latest["code"].nunique()),
        "snapshot_built_at": datetime.now().isoformat(timespec="seconds"),
    }
    PRICE_PANEL_INDUSTRY_SNAPSHOT_META_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return latest
