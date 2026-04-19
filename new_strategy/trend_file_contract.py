from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from new_strategy.paths import trend_data_path, trend_output_path


TrendFileKind = Literal["data", "output"]
TREND_FILE_PREFIX = "trend_"


@dataclass(frozen=True)
class TrendFileSpec:
    key: str
    kind: TrendFileKind
    name: str
    required: bool
    description: str

    @property
    def path(self) -> Path:
        if self.kind == "data":
            return trend_data_path(self.name)
        return trend_output_path(self.name)


def trend_file_specs() -> list[TrendFileSpec]:
    # Keep names explicit and prefixed so cleanup/migration cannot confuse
    # trend-lab files with strategy runtime contracts.
    return [
        TrendFileSpec(
            key="keyword_taxonomy",
            kind="data",
            name="trend_keyword_taxonomy.csv",
            required=True,
            description="Canonical keyword taxonomy and label contract.",
        ),
        TrendFileSpec(
            key="keyword_industry_seed_map",
            kind="data",
            name="trend_keyword_industry_map.csv",
            required=True,
            description="Seed keyword-to-industry mapping (manual baseline).",
        ),
        TrendFileSpec(
            key="keyword_aliases",
            kind="data",
            name="trend_keyword_aliases.csv",
            required=False,
            description="Synonym/alias normalization map.",
        ),
        TrendFileSpec(
            key="unclassified_keywords",
            kind="data",
            name="trend_unclassified_keywords.csv",
            required=True,
            description="Queue for new keywords that failed auto classification.",
        ),
        TrendFileSpec(
            key="snapshot",
            kind="output",
            name="trend_global_snapshot.json",
            required=True,
            description="Daily trend sensing snapshot for Streamlit view.",
        ),
        TrendFileSpec(
            key="news_mentions_rolling",
            kind="output",
            name="trend_news_mentions_rolling.csv",
            required=True,
            description="Rolling raw news mention rows (35-day retention).",
        ),
        TrendFileSpec(
            key="keyword_daily_scores",
            kind="output",
            name="trend_keyword_daily_scores.csv",
            required=True,
            description="Per-keyword daily scores and component metrics.",
        ),
        TrendFileSpec(
            key="keyword_industry_links",
            kind="output",
            name="trend_keyword_industry_links.csv",
            required=True,
            description="Data-driven keyword-industry links with strength/confidence.",
        ),
        TrendFileSpec(
            key="holding_exposure",
            kind="output",
            name="trend_holding_exposure.csv",
            required=True,
            description="Holdings linked to trend keywords and exposure score.",
        ),
        TrendFileSpec(
            key="collection_status",
            kind="output",
            name="trend_collection_status.csv",
            required=False,
            description="Collection/processing status and error summary.",
        ),
        TrendFileSpec(
            key="classification_log",
            kind="output",
            name="trend_classification_log.csv",
            required=False,
            description="Auto-classification decision history for audit.",
        ),
    ]


def resolve_trend_file(key: str) -> Path:
    lookup = {spec.key: spec for spec in trend_file_specs()}
    if key not in lookup:
        raise KeyError(f"Unknown trend file key: {key}")
    return lookup[key].path


def ensure_trend_lab_dirs() -> tuple[Path, Path]:
    data_dir = trend_data_path()
    out_dir = trend_output_path()
    data_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    return data_dir, out_dir


def validate_trend_file_name(name: str) -> bool:
    text = str(name or "").strip()
    return bool(text) and text.startswith(TREND_FILE_PREFIX)
