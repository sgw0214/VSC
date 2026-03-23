from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from new_strategy.paths import output_path


ROBUST_DIR = output_path("alpha_combo_research", "robust_phase2")
RESULTS_PATH = ROBUST_DIR / "global_combo_results_robust.csv"
OUTPUT_PATH = ROBUST_DIR / "deployable_global_shortlist.csv"
SUMMARY_PATH = ROBUST_DIR / "deployable_summary.md"
META_PATH = ROBUST_DIR / "deployable_meta.json"


def main() -> None:
    df = pd.read_csv(RESULTS_PATH)
    df = df[df["horizon_days"] == 20].copy()
    df = df[
        (df["obs"] >= 20000)
        & (df["median_return"] >= 0.003)
        & (df["win_rate"] >= 0.52)
        & (df["p10_return"] >= -0.12)
        & (df["condition_count"] <= 3)
    ].copy()
    df = df.sort_values(
        ["robust_score", "winsor_mean_return", "median_return", "win_rate", "obs"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    top = df.head(20).copy()
    lines = [
        "# Deployable Global Shortlist",
        "",
        "- filters:",
        "  - horizon_days == 20",
        "  - obs >= 20,000",
        "  - median_return >= 0.30%",
        "  - win_rate >= 52%",
        "  - p10_return >= -12%",
        "  - condition_count <= 3",
        "",
        f"- candidates: {len(df):,}",
        "",
        "## Top 20",
    ]
    if top.empty:
        lines.append("- no candidates")
    else:
        for _, row in top.iterrows():
            lines.append(
                f"- {row['condition_labels']} | obs {int(row['obs']):,} | robust {float(row['robust_score']):.3f} | winsor {float(row['winsor_mean_return']):+.2%} | median {float(row['median_return']):+.2%} | win {float(row['win_rate']):.2%}"
            )
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    META_PATH.write_text(
        json.dumps(
            {
                "source": str(RESULTS_PATH),
                "filters": {
                    "horizon_days": 20,
                    "min_obs": 20000,
                    "min_median_return": 0.003,
                    "min_win_rate": 0.52,
                    "min_p10_return": -0.12,
                    "max_condition_count": 3,
                },
                "candidates": int(len(df)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
