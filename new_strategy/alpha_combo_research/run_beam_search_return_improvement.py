from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from new_strategy.alpha_combo_research.run_return_max_search_robust import (
    OUTPUT_DIR as ROBUST_OUTPUT_DIR,
    build_conditions,
    load_base_frame,
)
from new_strategy.paths import output_path


OUTPUT_DIR = output_path("alpha_combo_research", "beam_search_phase3")


@dataclass
class ComboResult:
    names: tuple[str, ...]
    labels: tuple[str, ...]
    obs: int
    winsor_mean_return: float
    median_return: float
    win_rate: float
    p10_return: float
    p25_return: float
    robust_score: float


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _winsorized_mean(series: pd.Series, lower: float = 0.05, upper: float = 0.95) -> float:
    clean = _to_num(series).dropna()
    if clean.empty:
        return float("nan")
    lo = clean.quantile(lower)
    hi = clean.quantile(upper)
    return float(clean.clip(lower=lo, upper=hi).mean())


def _score(values: pd.Series) -> tuple[float, float, float, float, float, float]:
    winsor_mean = _winsorized_mean(values)
    median = float(values.median())
    win_rate = float((values > 0).mean())
    p10 = float(values.quantile(0.10))
    p25 = float(values.quantile(0.25))
    robust_score = winsor_mean * 100 + median * 40 + win_rate * 8 + p25 * 20 + p10 * 10
    return winsor_mean, median, win_rate, p10, p25, robust_score


def _evaluate_combo(df: pd.DataFrame, names: tuple[str, ...], labels: tuple[str, ...], min_obs: int) -> ComboResult | None:
    target = _to_num(df["fwd_ret_20d"])
    mask = target.notna()
    for name in names:
        col = f"cond__{name}"
        if col not in df.columns:
            return None
        mask = mask & df[col].astype(bool)
    obs = int(mask.sum())
    if obs < min_obs:
        return None
    values = target[mask]
    winsor_mean, median, win_rate, p10, p25, robust_score = _score(values)
    return ComboResult(
        names=names,
        labels=labels,
        obs=obs,
        winsor_mean_return=winsor_mean,
        median_return=median,
        win_rate=win_rate,
        p10_return=p10,
        p25_return=p25,
        robust_score=robust_score,
    )


def _serialize(row: ComboResult, combo_size: int, parent_score: float | None = None) -> dict[str, object]:
    gain = None if parent_score is None else row.robust_score - parent_score
    return {
        "combo_size": combo_size,
        "condition_names": " + ".join(row.names),
        "condition_labels": " + ".join(row.labels),
        "obs": row.obs,
        "winsor_mean_return": row.winsor_mean_return,
        "median_return": row.median_return,
        "win_rate": row.win_rate,
        "p10_return": row.p10_return,
        "p25_return": row.p25_return,
        "robust_score": row.robust_score,
        "gain_vs_parent": gain,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-industries", type=int, default=15)
    parser.add_argument("--min-obs", type=int, default=20000)
    parser.add_argument("--beam-width", type=int, default=20)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--min-improvement", type=float, default=0.03)
    args = parser.parse_args()

    df = load_base_frame()
    top_industries = (
        df["industry"]
        .astype(str)
        .value_counts()
        .head(args.top_industries)
        .index
        .tolist()
    )
    conditions = build_conditions(df, top_industries)
    condition_map = {c.name: c for c in conditions}

    evaluated: dict[tuple[str, ...], ComboResult] = {}
    frontier: list[ComboResult] = []
    all_rows: list[dict[str, object]] = []

    for condition in conditions:
        result = _evaluate_combo(df, (condition.name,), (condition.label,), args.min_obs)
        if result is None:
            continue
        evaluated[result.names] = result
        frontier.append(result)
        all_rows.append(_serialize(result, combo_size=1))

    frontier = sorted(frontier, key=lambda r: (r.robust_score, r.winsor_mean_return, r.win_rate, r.obs), reverse=True)[: args.beam_width]

    depth_summary: list[dict[str, object]] = []
    if frontier:
        best = frontier[0]
        depth_summary.append({"combo_size": 1, "best_score": best.robust_score, "best_labels": " + ".join(best.labels)})

    for depth in range(2, args.max_depth + 1):
        candidates: list[tuple[ComboResult, float]] = []
        for parent in frontier:
            used = set(parent.names)
            for name, condition in condition_map.items():
                if name in used:
                    continue
                names = tuple(sorted((*parent.names, name)))
                if names in evaluated:
                    continue
                labels = tuple(condition_map[n].label for n in names)
                result = _evaluate_combo(df, names, labels, args.min_obs)
                if result is None:
                    continue
                evaluated[names] = result
                gain = result.robust_score - parent.robust_score
                if gain < args.min_improvement:
                    continue
                candidates.append((result, parent.robust_score))

        if not candidates:
            depth_summary.append({"combo_size": depth, "best_score": None, "best_labels": "", "stopped": True})
            break

        candidates = sorted(
            candidates,
            key=lambda item: (item[0].robust_score, item[0].winsor_mean_return, item[0].win_rate, item[0].obs),
            reverse=True,
        )
        frontier = [item[0] for item in candidates[: args.beam_width]]
        best = frontier[0]
        depth_summary.append({"combo_size": depth, "best_score": best.robust_score, "best_labels": " + ".join(best.labels)})
        for result, parent_score in candidates[: args.beam_width]:
            all_rows.append(_serialize(result, combo_size=depth, parent_score=parent_score))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows).sort_values(
        ["combo_size", "robust_score", "winsor_mean_return", "win_rate", "obs"],
        ascending=[True, False, False, False, False],
    ).to_csv(OUTPUT_DIR / "beam_search_results.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(depth_summary).to_csv(OUTPUT_DIR / "beam_search_depth_summary.csv", index=False, encoding="utf-8-sig")

    summary_lines = [
        "# Beam Search Phase 3",
        "",
        f"- min_obs: {args.min_obs}",
        f"- beam_width: {args.beam_width}",
        f"- max_depth: {args.max_depth}",
        f"- min_improvement: {args.min_improvement}",
        "",
        "## Depth Summary",
    ]
    for row in depth_summary:
        if row.get("stopped"):
            summary_lines.append(f"- depth {row['combo_size']}: stopped (no improvement >= {args.min_improvement})")
        else:
            summary_lines.append(
                f"- depth {row['combo_size']}: best_score {float(row['best_score']):.3f} | {row['best_labels']}"
            )
    (OUTPUT_DIR / "summary.md").write_text("\n".join(summary_lines), encoding="utf-8")
    (OUTPUT_DIR / "meta.json").write_text(
        json.dumps(
            {
                "source_feature_rows": int(len(df)),
                "source_stocks": int(df["code"].nunique()),
                "min_obs": int(args.min_obs),
                "beam_width": int(args.beam_width),
                "max_depth": int(args.max_depth),
                "min_improvement": float(args.min_improvement),
                "robust_source_dir": str(ROBUST_OUTPUT_DIR),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
