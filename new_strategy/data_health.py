from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List

import pandas as pd

from new_strategy.paths import data_path, output_path


def _summarize_csv(
    name: str,
    path: Path,
    date_col: str,
    code_col: str = "",
    extra_non_null_cols: List[str] | None = None,
    read_kwargs: Dict[str, object] | None = None,
) -> Dict[str, object]:
    read_kwargs = read_kwargs or {}
    if not path.exists():
        return {"dataset": name, "path": str(path), "exists": False}

    df = pd.read_csv(path, low_memory=False, **read_kwargs)
    out: Dict[str, object] = {
        "dataset": name,
        "path": str(path),
        "exists": True,
        "rows": int(len(df)),
    }
    if date_col in df.columns:
        dt = pd.to_datetime(df[date_col], errors="coerce")
        out["date_min"] = None if dt.dropna().empty else str(dt.min().date())
        out["date_max"] = None if dt.dropna().empty else str(dt.max().date())
    if code_col and code_col in df.columns:
        out["codes"] = int(df[code_col].astype(str).nunique())
    if extra_non_null_cols:
        for col in extra_non_null_cols:
            if col in df.columns:
                out[f"non_null_{col}"] = int(df[col].notna().sum())
    return out


def _summarize_pickle(name: str, path: Path, date_col: str, code_col: str = "") -> Dict[str, object]:
    if not path.exists():
        return {"dataset": name, "path": str(path), "exists": False}
    df = pd.read_pickle(path)
    out: Dict[str, object] = {
        "dataset": name,
        "path": str(path),
        "exists": True,
        "rows": int(len(df)),
    }
    if date_col in df.columns:
        dt = pd.to_datetime(df[date_col], errors="coerce")
        out["date_min"] = None if dt.dropna().empty else str(dt.min().date())
        out["date_max"] = None if dt.dropna().empty else str(dt.max().date())
    if code_col and code_col in df.columns:
        out["codes"] = int(df[code_col].astype(str).nunique())
    return out


def _summarize_sqlite(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"dataset": "market_data_db", "path": str(path), "exists": False}
    conn = sqlite3.connect(str(path))
    try:
        tables = {
            "dim_symbol": "SELECT COUNT(*) FROM dim_symbol",
            "fact_price_daily": "SELECT COUNT(*) FROM fact_price_daily",
            "fact_macro_daily": "SELECT COUNT(*) FROM fact_macro_daily",
            "fact_fundamental_quarterly": "SELECT COUNT(*) FROM fact_fundamental_quarterly",
        }
        out = {"dataset": "market_data_db", "path": str(path), "exists": True}
        for key, sql in tables.items():
            out[key] = int(conn.execute(sql).fetchone()[0])
        out["price_date_max"] = conn.execute("SELECT MAX(date) FROM fact_price_daily").fetchone()[0]
        out["macro_date_max"] = conn.execute("SELECT MAX(date) FROM fact_macro_daily").fetchone()[0]
        out["fund_date_max"] = conn.execute("SELECT MAX(rcept_dt) FROM fact_fundamental_quarterly").fetchone()[0]
        return out
    finally:
        conn.close()


def build_data_health(output_dir: Path | None = None) -> Dict[str, Path]:
    output_dir = output_dir or output_path("strategy_v1")
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        _summarize_csv("price_panel", data_path("price_panel.csv"), "date", "code"),
        _summarize_pickle("feature_daily", data_path("feature_daily.pkl"), "date", "code"),
        _summarize_csv(
            "macro_daily",
            data_path("macro_daily.csv"),
            "date",
            extra_non_null_cols=["kospi", "vix", "usdkrw", "us10y", "kr10y", "gold_kr_close"],
        ),
        _summarize_csv(
            "macro_regime",
            data_path("macro_regime_v3_rec.csv"),
            "date",
            extra_non_null_cols=["exposure", "risk_count"],
        ),
        _summarize_csv(
            "fundamental_quarterly_multi",
            data_path("fundamental_quarterly_multi.csv"),
            "공시일",
            "종목코드",
        ),
        _summarize_sqlite(data_path("market_data.db")),
    ]

    df = pd.DataFrame(rows)
    csv_path = output_dir / "data_health_summary.csv"
    json_path = output_dir / "data_health_summary.json"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"csv": csv_path, "json": json_path}
