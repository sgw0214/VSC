from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from new_strategy.optimal_ma_publish_contract import (
    OPTIMAL_MA_ALLOWED_ACTION_MODES,
    OPTIMAL_MA_ALLOWED_TIMEFRAMES,
    OPTIMAL_MA_ALL_META_PATH,
    OPTIMAL_MA_ALL_SCHEMA_VERSION,
    OPTIMAL_MA_ALL_SELECTION_PATH,
    OPTIMAL_MA_META_PATH,
    OPTIMAL_MA_REQUIRED_COLUMNS,
    OPTIMAL_MA_SCHEMA_VERSION,
    OPTIMAL_MA_SELECTION_PATH,
)


def validate_selection(
    path: Path = OPTIMAL_MA_SELECTION_PATH,
    *,
    expected_scope: str = "monthly_weekly",
    expected_schema: str = OPTIMAL_MA_SCHEMA_VERSION,
) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"missing published selection: {path}")

    df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    missing = [col for col in OPTIMAL_MA_REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    if df.empty:
        raise ValueError("published selection is empty")

    bad_codes = df["code"].astype(str).map(lambda x: len(x) != 6 or not x.isalnum())
    if bad_codes.any():
        raise ValueError("code column contains values outside 6-character alphanumeric format")

    invalid_tf = sorted(set(df["ma_timeframe"].astype(str)) - OPTIMAL_MA_ALLOWED_TIMEFRAMES)
    if invalid_tf:
        raise ValueError(f"invalid ma_timeframe values: {invalid_tf}")

    invalid_modes = sorted(set(df["action_mode"].astype(str)) - OPTIMAL_MA_ALLOWED_ACTION_MODES)
    if invalid_modes:
        raise ValueError(f"invalid action_mode values: {invalid_modes}")

    if (df["selection_scope"].astype(str) != expected_scope).any():
        raise ValueError(f"selection_scope must be {expected_scope} for all rows")

    if expected_scope == "monthly_weekly":
        duplicate_codes = df["code"].astype(str).duplicated()
        if duplicate_codes.any():
            raise ValueError("published selection contains duplicate codes")
    else:
        duplicate_keys = df[["code", "ma_timeframe"]].astype(str).duplicated()
        if duplicate_keys.any():
            raise ValueError("published selection contains duplicate code+ma_timeframe keys")

    metrics = {
        "schema_version": expected_schema,
        "row_count": int(len(df)),
        "stock_count": int(df["code"].nunique()),
        "timeframe_counts": df["ma_timeframe"].value_counts().to_dict(),
        "action_mode_counts": df["action_mode"].value_counts().to_dict(),
    }
    return metrics


def validate_meta(path: Path = OPTIMAL_MA_META_PATH, *, expected_schema: str = OPTIMAL_MA_SCHEMA_VERSION) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"missing published meta: {path}")
    meta = json.loads(path.read_text(encoding="utf-8"))
    if meta.get("schema_version") != expected_schema:
        raise ValueError(f"schema_version mismatch: {meta.get('schema_version')!r}")
    return meta


def main() -> None:
    selection_metrics = validate_selection()
    meta = validate_meta()
    selection_all_metrics = validate_selection(
        OPTIMAL_MA_ALL_SELECTION_PATH,
        expected_scope="all_timeframes",
        expected_schema=OPTIMAL_MA_ALL_SCHEMA_VERSION,
    )
    meta_all = validate_meta(OPTIMAL_MA_ALL_META_PATH, expected_schema=OPTIMAL_MA_ALL_SCHEMA_VERSION)
    print(json.dumps({"selection": selection_metrics, "meta": meta, "selection_all": selection_all_metrics, "meta_all": meta_all}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
