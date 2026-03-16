from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from new_strategy.external_sources import ensure_external_dirs, initialize_empty_file, iter_specs, resolve_storage_path
from new_strategy.paths import data_path


COMMON_MACRO_COLS = [
    "date",
    "kospi",
    "vix",
    "usdkrw",
    "us10y",
    "kr10y",
    "gold_kr_close",
    "gold_kr_ret",
    "gold_kr_volume",
    "gold_kr_trading_value",
]

REGIME_COLS = [
    "date",
    "risk_count",
    "regime",
    "exposure",
]


def export_common_macro() -> Path:
    macro_daily = pd.read_csv(data_path("macro_daily.csv"), encoding="utf-8-sig", low_memory=False)
    macro_regime = pd.read_csv(data_path("macro_regime_v3_rec.csv"), encoding="utf-8-sig", low_memory=False)
    macro_daily = macro_daily[[c for c in COMMON_MACRO_COLS if c in macro_daily.columns]].copy()
    macro_regime = macro_regime[[c for c in REGIME_COLS if c in macro_regime.columns]].copy()
    merged = macro_daily.merge(macro_regime, on="date", how="outer").sort_values("date").reset_index(drop=True)
    out = resolve_storage_path("common_market_macro.csv")
    merged.to_csv(out, index=False, encoding="utf-8-sig")
    return out


def build_priority1_status() -> Path:
    rows = []
    for spec in iter_specs(priority=1):
        path = initialize_empty_file(spec)
        rows.append(
            {
                "indicator_id": spec.indicator_id,
                "storage_file": str(path),
                "exists": path.exists(),
                "collection_mode": spec.collection_mode,
                "refresh_frequency": spec.refresh_frequency,
                "primary_source": spec.primary_source,
                "fallback_source": spec.fallback_source,
            }
        )
    out = resolve_storage_path("priority1_collection_status.csv")
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Initialize external priority-1 storage and export reusable common macro data.")
    p.add_argument("--skip-common-macro", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    ensure_external_dirs()
    if not args.skip_common_macro:
        out = export_common_macro()
        print(f"[saved] {out}")
    status_out = build_priority1_status()
    print(f"[saved] {status_out}")


if __name__ == "__main__":
    main()
