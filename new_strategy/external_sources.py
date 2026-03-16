from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List

import pandas as pd

from new_strategy.paths import data_path, external_path

DEFAULT_START_DATE = "2015-01-01"


@dataclass(frozen=True)
class ExternalSeriesSpec:
    indicator_id: str
    storage_file: str
    date_column: str
    value_columns: List[str]
    status: str
    priority: int
    collection_mode: str
    refresh_frequency: str
    primary_source: str
    fallback_source: str
    notes: str


def manifest_path() -> Path:
    return data_path("external_indicator_collection_manifest.csv")


def load_manifest() -> pd.DataFrame:
    return pd.read_csv(manifest_path(), encoding="utf-8-sig")


def iter_specs(priority: int | None = None) -> Iterable[ExternalSeriesSpec]:
    manifest = load_manifest()
    if priority is not None:
        manifest = manifest[manifest["priority"] == priority].copy()
    for row in manifest.to_dict("records"):
        yield ExternalSeriesSpec(
            indicator_id=str(row["indicator_id"]),
            storage_file=str(row["storage_file"]).replace("data/external/", ""),
            date_column=str(row["date_column"]),
            value_columns=str(row["value_columns"]).split("|"),
            status=str(row["status"]),
            priority=int(row["priority"]),
            collection_mode=str(row["collection_mode"]),
            refresh_frequency=str(row["refresh_frequency"]),
            primary_source=str(row["primary_source"] or ""),
            fallback_source=str(row["fallback_source"] or ""),
            notes=str(row["notes"] or ""),
        )


def ensure_external_dirs() -> None:
    external_path().mkdir(parents=True, exist_ok=True)


def resolve_storage_path(storage_file: str) -> Path:
    path = external_path(storage_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def initialize_empty_file(spec: ExternalSeriesSpec) -> Path:
    path = resolve_storage_path(spec.storage_file)
    if path.exists():
        return path
    cols = [spec.date_column] + spec.value_columns
    pd.DataFrame(columns=cols).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def today_str() -> str:
    return date.today().isoformat()


def normalize_dates(df: pd.DataFrame, date_column: str = "date") -> pd.DataFrame:
    out = df.copy()
    out[date_column] = pd.to_datetime(out[date_column], errors="coerce")
    out = out.dropna(subset=[date_column]).sort_values(date_column).reset_index(drop=True)
    out[date_column] = out[date_column].dt.strftime("%Y-%m-%d")
    return out


def load_existing(path: Path, date_column: str = "date") -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=[date_column])
    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    if date_column not in df.columns:
        raise ValueError(f"Missing `{date_column}` in {path}")
    return normalize_dates(df, date_column=date_column)


def upsert_by_date(path: Path, new_df: pd.DataFrame, date_column: str = "date") -> pd.DataFrame:
    if new_df.empty:
        existing = load_existing(path, date_column=date_column)
        if not path.exists():
            existing.to_csv(path, index=False, encoding="utf-8-sig")
        return existing
    existing = load_existing(path, date_column=date_column)
    new_df = normalize_dates(new_df, date_column=date_column)
    if existing.empty:
        merged = new_df.copy()
    else:
        overlap_cols = [c for c in new_df.columns if c in existing.columns and c != date_column]
        existing_renamed = existing.rename(columns={c: f"{c}__old" for c in overlap_cols})
        merged = existing_renamed.merge(new_df, on=date_column, how="outer")
        for col in overlap_cols:
            old_col = f"{col}__old"
            if old_col in merged.columns:
                merged[col] = merged[col].combine_first(merged[old_col])
                merged = merged.drop(columns=[old_col])
    merged = merged.sort_values(date_column).drop_duplicates(subset=[date_column], keep="last").reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(path, index=False, encoding="utf-8-sig")
    return merged
