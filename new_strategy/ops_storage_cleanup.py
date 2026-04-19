from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from new_strategy.paths import (
    data_root,
    output_path,
    output_root,
    strategy_output_path,
    trend_data_subdir,
    trend_output_subdir,
)


@dataclass
class CleanupRecord:
    path: str
    rel_path: str
    kind: str
    size_mb: float
    last_write: str
    action: str
    reason: str


ROOT = data_root()
OUTPUT = output_root()
STRATEGY_OUT = strategy_output_path()
ARCHIVE_ROOT = output_path("_ops_archive")
INVENTORY_CSV = STRATEGY_OUT / "ops_data_inventory.csv"
INVENTORY_SUMMARY_JSON = STRATEGY_OUT / "ops_data_inventory_summary.json"

ROOT_KEEP = {
    "feature_daily.csv",
    "feature_daily.pkl",
    "price_panel.csv",
    "fundamental_quarterly_raw.csv",
    "fundamental_quarterly_multi.csv",
    "fundamental_quarterly_multi_request_log.csv",
    "macro_daily.csv",
    "macro_regime_v3_rec.csv",
    "gold_kr_daily.xlsx",
    "market_data.db",
    "output",
    "cache",
    trend_data_subdir(),
}

ROOT_ARCHIVE = {
    "feature_daily.parquet": "feature_daily.pkl/csv already cover runtime; parquet is not referenced by runtime paths.",
    "price_panel_sample.csv": "sample file; not used by runtime.",
    "price_panel_meta (1).json": "duplicate metadata file.",
    "refresh_runtime_metadata (1).json": "duplicate metadata file.",
}

OUTPUT_KEEP_DIRS = {
    "strategy_v2",
}

OUTPUT_ARCHIVE_DIR_PREFIXES = (
    "strategy_compare",
    "v2_candidate_rule_a_validation",
    "v2_weekly_fixed_window_compare",
    "v2_weekly_fixed_window_compare_2_4_6_8",
    "v2_weekly_lead_threshold_research",
    "v2_monthly_buy_weekly_sell_research",
    "v2_monthly_only_vs_optimal_vs_conditional",
    "v2_user_proposed_hybrid_rule",
    "v2_ratio_bucket_remediation",
    "v2_ratio_rootcause_multiaxis_analysis",
    "v2_ratio_bucket_macro_correlation",
    "v2_ratio_bucket_recent_return_trade_mdd",
    "v2_ratio_regime_shift_analysis",
    "v2_ratio_bucket_event_analysis",
    "v2_stock_check_skinnovation",
    "v2_leq",
    "ma_breakout_research_bench_50",
    "macro_correlation_research",
    "ma_window_research",
    "strategy_v1",
)

MA_BREAKOUT_KEEP = {
    "all_action_modes_returns_by_stock.csv",
    "native_timeframe_close_returns_by_stock.csv",
    "published",
}

MA_BREAKOUT_ARCHIVE = {
    "archive": "historical archive inside research output; not used by runtime.",
    "analysis": "research analysis output; not used by runtime.",
    "charts": "research chart output; not used by runtime.",
    "daily_close_action_returns_by_stock.csv": "daily-close variant not referenced by runtime.",
    "best_window_by_stock.csv": "selection helper file; not used by runtime.",
    "best_window_distribution.csv": "distribution helper file; not used by runtime.",
    "summary_report.md": "research summary; not used by runtime.",
    "run_meta.json": "research run metadata; not used by runtime.",
}

BEST_MODE_KEEP = {
    "best_mode_by_stock_full.csv",
}

BEST_MODE_ARCHIVE = {
    "stock_mode_window_results_full.csv": "large brute-force result table; runtime uses best_mode_by_stock_full.csv only.",
    "stock_mode_window_results_sample.csv": "sample brute-force result table.",
    "best_per_stock_mode_full.csv": "research comparison table; runtime does not read it.",
    "best_mode_by_stock_full.xlsx": "human-readable export; runtime reads CSV only.",
    "best_vs_monthly_by_stock.csv": "analysis output; runtime does not read it.",
    "best_vs_monthly_full.xlsx": "analysis output; runtime does not read it.",
    "four_timing_mode_grid_summary_full.xlsx": "analysis summary; runtime does not read it.",
    "benchmark_full.csv": "research benchmark only.",
    "benchmark_sample.csv": "research benchmark only.",
    "common_best_window_pairs_full.csv": "research summary only.",
    "run_meta_full.json": "research metadata only.",
    "run_meta_sample.json": "research metadata only.",
    "best_mode_distribution_full.csv": "research summary only.",
    "best_vs_monthly_summary.csv": "research summary only.",
    "mode_best_summary_full.csv": "research summary only.",
    "best_vs_monthly_by_best_mode.csv": "research summary only.",
    "mode_summary_sample.csv": "research summary only.",
    "mode_summary_full.csv": "research summary only.",
}

STRATEGY_V2_ARCHIVE_EXACT = {
    "alert_log_kakao_legacy.csv": "legacy kakao log.",
    "data_health_summary (1).json": "duplicate metadata file.",
    "refresh_runtime_metadata (1).json": "duplicate metadata file.",
    "fast_position_state.pre_v2_reset_20260322_014429.csv": "pre-v2 reset backup; keep only if manual rollback needed.",
}


def _size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return round(path.stat().st_size / 1_048_576, 2)
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return round(total / 1_048_576, 2)


def _record(path: Path, *, action: str, reason: str) -> CleanupRecord:
    rel = path.relative_to(ROOT)
    kind = "dir" if path.is_dir() else "file"
    last_write = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if path.exists() else ""
    return CleanupRecord(
        path=str(path),
        rel_path=str(rel),
        kind=kind,
        size_mb=_size_mb(path),
        last_write=last_write,
        action=action,
        reason=reason,
    )


def build_inventory() -> list[CleanupRecord]:
    records: list[CleanupRecord] = []

    for child in ROOT.iterdir():
        name = child.name
        if name in ROOT_KEEP:
            records.append(_record(child, action="keep", reason="runtime/core data"))
            continue
        if name in ROOT_ARCHIVE:
            records.append(_record(child, action="archive_candidate", reason=ROOT_ARCHIVE[name]))
            continue
        if child.is_dir() and name == "__pycache__":
            records.append(_record(child, action="archive_candidate", reason="cache-like folder under data root"))
            continue
        records.append(_record(child, action="review", reason="not classified"))

    if OUTPUT.exists():
        for child in OUTPUT.iterdir():
            name = child.name
            if name in OUTPUT_KEEP_DIRS:
                continue
            if name == "ma_breakout_research":
                records.extend(_build_ma_breakout_records(child))
                continue
            if name == "v2_four_timing_mode_grid":
                records.extend(_build_best_mode_records(child))
                continue
            if child.is_dir() and any(name.startswith(prefix) for prefix in OUTPUT_ARCHIVE_DIR_PREFIXES):
                records.append(_record(child, action="archive_candidate", reason="research output not used by live runtime"))
                continue
            if child.is_dir():
                records.append(_record(child, action="review", reason="output dir not classified"))
            else:
                records.append(_record(child, action="review", reason="output file not classified"))

    if STRATEGY_OUT.exists():
        records.extend(_build_strategy_v2_records())

    return sorted(records, key=lambda x: ({"archive_candidate": 0, "review": 1, "keep": 2}.get(x.action, 9), -x.size_mb, x.rel_path))


def _build_ma_breakout_records(root: Path) -> list[CleanupRecord]:
    records: list[CleanupRecord] = []
    for child in root.iterdir():
        name = child.name
        if name in MA_BREAKOUT_KEEP:
            records.append(_record(child, action="keep", reason="referenced by runtime/best-ma contract paths"))
        elif name in MA_BREAKOUT_ARCHIVE:
            records.append(_record(child, action="archive_candidate", reason=MA_BREAKOUT_ARCHIVE[name]))
        else:
            records.append(_record(child, action="review", reason="ma_breakout_research item not classified"))
    return records


def _build_best_mode_records(root: Path) -> list[CleanupRecord]:
    records: list[CleanupRecord] = []
    for child in root.iterdir():
        name = child.name
        if name in BEST_MODE_KEEP:
            records.append(_record(child, action="keep", reason="live engine reads this contract file"))
        elif name in BEST_MODE_ARCHIVE:
            records.append(_record(child, action="archive_candidate", reason=BEST_MODE_ARCHIVE[name]))
        else:
            records.append(_record(child, action="review", reason="v2_four_timing_mode_grid item not classified"))
    return records


def _build_strategy_v2_records() -> list[CleanupRecord]:
    records: list[CleanupRecord] = []
    for child in STRATEGY_OUT.iterdir():
        name = child.name
        if name == trend_output_subdir():
            records.append(_record(child, action="keep", reason="trend-lab isolated scope (separate from strategy runtime contracts)"))
            continue
        if name in STRATEGY_V2_ARCHIVE_EXACT:
            records.append(_record(child, action="archive_candidate", reason=STRATEGY_V2_ARCHIVE_EXACT[name]))
            continue
        if name == "telegram_bridge":
            records.extend(_build_telegram_bridge_records(child))
            continue
        if name == "dashboard_pipeline_runs":
            records.append(_record(child, action="retention_candidate", reason="old pipeline run logs can be pruned by age"))
            continue
        if child.name.endswith(".log"):
            records.append(_record(child, action="retention_candidate", reason="runtime log; prune by age/size rather than delete immediately"))
            continue
    return records


def _build_telegram_bridge_records(root: Path) -> list[CleanupRecord]:
    records: list[CleanupRecord] = []
    for child in root.iterdir():
        name = child.name
        if name in {"briefings", "mockups", "jobs"}:
            records.append(_record(child, action="retention_candidate", reason="image/job artifacts; prune by age"))
            continue
        if name in {"telegram_image_test.png", "telegram_bridge_unhandled_log_archive_20260313_174945.csv"}:
            records.append(_record(child, action="archive_candidate", reason="legacy/manual test artifact"))
            continue
        if child.name.endswith(".log"):
            records.append(_record(child, action="retention_candidate", reason="bridge log; prune by age/size"))
    return records


def write_inventory(records: Iterable[CleanupRecord]) -> None:
    STRATEGY_OUT.mkdir(parents=True, exist_ok=True)
    rows = [asdict(rec) for rec in records]
    with INVENTORY_CSV.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()) if rows else ["path", "rel_path", "kind", "size_mb", "last_write", "action", "reason"])
        writer.writeheader()
        writer.writerows(rows)
    summary: dict[str, dict[str, float | int]] = {}
    for rec in records:
        bucket = summary.setdefault(rec.action, {"count": 0, "size_mb": 0.0})
        bucket["count"] = int(bucket["count"]) + 1
        bucket["size_mb"] = round(float(bucket["size_mb"]) + rec.size_mb, 2)
    INVENTORY_SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def archive_candidates(records: Iterable[CleanupRecord]) -> list[tuple[str, str]]:
    archive_root = ARCHIVE_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    moved: list[tuple[str, str]] = []
    for rec in records:
        if rec.action != "archive_candidate":
            continue
        src = Path(rec.path)
        if not src.exists():
            continue
        dst = archive_root / rec.rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved.append((str(src), str(dst)))
    return moved


def prune_runtime(retention_days: int) -> list[str]:
    removed: list[str] = []
    cutoff = datetime.now() - timedelta(days=retention_days)

    targets = [
        STRATEGY_OUT / "dashboard_pipeline_runs",
        STRATEGY_OUT / "telegram_bridge" / "briefings",
        STRATEGY_OUT / "telegram_bridge" / "mockups",
    ]
    for root in targets:
        if not root.exists():
            continue
        for item in root.rglob("*"):
            if not item.is_file():
                continue
            if datetime.fromtimestamp(item.stat().st_mtime) < cutoff:
                item.unlink()
                removed.append(str(item))

    for pattern_root in [STRATEGY_OUT, STRATEGY_OUT / "telegram_bridge"]:
        if not pattern_root.exists():
            continue
        for item in pattern_root.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() == ".log" and datetime.fromtimestamp(item.stat().st_mtime) < cutoff:
                item.unlink()
                removed.append(str(item))
    return removed


def main() -> None:
    p = argparse.ArgumentParser(description="Inventory and safe archival helper for OneDrive operational data.")
    p.add_argument("--apply-archive", action="store_true", help="Move archive_candidate items into output/_ops_archive/<timestamp>/")
    p.add_argument("--prune-runtime-days", type=int, default=0, help="Delete runtime image/log artifacts older than N days.")
    args = p.parse_args()

    records = build_inventory()
    write_inventory(records)

    moved: list[tuple[str, str]] = []
    if args.apply_archive:
        moved = archive_candidates(records)

    removed: list[str] = []
    if args.prune_runtime_days > 0:
        removed = prune_runtime(args.prune_runtime_days)

    summary = {
        "inventory_csv": str(INVENTORY_CSV),
        "inventory_summary_json": str(INVENTORY_SUMMARY_JSON),
        "archive_applied": bool(args.apply_archive),
        "archive_moved_count": len(moved),
        "pruned_count": len(removed),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
