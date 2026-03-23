from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from new_strategy.paths import data_path, output_path


DEFAULT_SOURCE = data_path("macro_regime_v3_rec.csv")
DEFAULT_OUT_DIR = output_path("macro_correlation_research")

LEVEL_COLUMNS = [
    "kospi",
    "vix",
    "usdkrw",
    "us10y",
    "kr10y",
    "gold_kr_close",
    "risk_count",
    "exposure",
]
PCT_CHANGE_COLUMNS = {"kospi", "vix", "usdkrw", "gold_kr_close"}
DIFF_CHANGE_COLUMNS = {"us10y", "kr10y", "risk_count", "exposure", "regime_score"}
REGIME_MAP = {"risk_on": 1.0, "neutral": 0.0, "risk_off": -1.0}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze pairwise correlations among macro variables.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def load_source(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df


def build_level_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["date"]].copy()
    for col in LEVEL_COLUMNS:
        if col in df.columns:
            out[col] = pd.to_numeric(df[col], errors="coerce")
    if "regime" in df.columns:
        out["regime_score"] = df["regime"].astype(str).str.strip().str.lower().map(REGIME_MAP)
    out = out.dropna(axis=1, how="all")
    return out


def build_change_frame(level_df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"date": level_df["date"]})
    value_cols = [col for col in level_df.columns if col != "date"]
    for col in value_cols:
        if col in PCT_CHANGE_COLUMNS:
            out[f"{col}_ret_1d"] = pd.to_numeric(level_df[col], errors="coerce").pct_change()
        elif col in DIFF_CHANGE_COLUMNS:
            out[f"{col}_chg_1d"] = pd.to_numeric(level_df[col], errors="coerce").diff()
        else:
            out[f"{col}_chg_1d"] = pd.to_numeric(level_df[col], errors="coerce").diff()
    out = out.dropna(axis=1, how="all")
    return out


def compute_corr(df: pd.DataFrame, method: str) -> pd.DataFrame:
    value_df = df.drop(columns=["date"], errors="ignore")
    value_df = value_df.dropna(axis=1, how="all")
    return value_df.corr(method=method)


def flatten_top_pairs(corr: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    cols = list(corr.columns)
    for i, left in enumerate(cols):
        for right in cols[i + 1 :]:
            value = corr.loc[left, right]
            if pd.isna(value):
                continue
            rows.append(
                {
                    "left": left,
                    "right": right,
                    "correlation": float(value),
                    "abs_correlation": float(abs(value)),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["left", "right", "correlation", "abs_correlation"])
    out = pd.DataFrame(rows).sort_values(["abs_correlation", "correlation"], ascending=[False, False]).reset_index(drop=True)
    return out.head(top_n).copy()


def render_heatmap(corr: pd.DataFrame, title: str, out_path: Path) -> None:
    if corr.empty:
        return
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(10, 8), dpi=160)
    im = ax.imshow(corr.to_numpy(), cmap="coolwarm", vmin=-1.0, vmax=1.0)
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.index)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right")
    ax.set_yticklabels(corr.index)
    ax.set_title(title, fontsize=13, fontweight="bold")
    for i in range(len(corr.index)):
        for j in range(len(corr.columns)):
            value = corr.iloc[i, j]
            if pd.isna(value):
                continue
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", color="black", fontsize=7)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def write_summary(
    out_dir: Path,
    *,
    source_path: Path,
    level_df: pd.DataFrame,
    change_df: pd.DataFrame,
    level_pearson: pd.DataFrame,
    change_pearson: pd.DataFrame,
    level_top: pd.DataFrame,
    change_top: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Macro Correlation Research")
    lines.append("")
    lines.append("## Source")
    lines.append(f"- source: `{source_path}`")
    lines.append(f"- date range: `{level_df['date'].min().date()}` ~ `{level_df['date'].max().date()}`")
    lines.append(f"- level rows: `{len(level_df):,}`")
    lines.append(f"- change rows: `{len(change_df):,}`")
    lines.append("")
    lines.append("## Variables")
    for col in level_df.columns:
        if col == "date":
            continue
        lines.append(f"- {col}")
    lines.append("")
    lines.append("## Notes")
    lines.append("- `level` correlation can be inflated by long-term trends.")
    lines.append("- `change` correlation is usually more useful for short-term co-movement.")
    lines.append("- `regime_score`: `risk_on=1`, `neutral=0`, `risk_off=-1`")
    lines.append("")
    lines.append("## Top Absolute Correlations: Level Pearson")
    if level_top.empty:
        lines.append("- no rows")
    else:
        for row in level_top.itertuples(index=False):
            lines.append(f"- {row.left} vs {row.right}: {row.correlation:.4f}")
    lines.append("")
    lines.append("## Top Absolute Correlations: Change Pearson")
    if change_top.empty:
        lines.append("- no rows")
    else:
        for row in change_top.itertuples(index=False):
            lines.append(f"- {row.left} vs {row.right}: {row.correlation:.4f}")
    lines.append("")
    lines.append("## Quick Read")
    if not level_pearson.empty and "exposure" in level_pearson.columns:
        exposure_pairs = (
            level_pearson["exposure"]
            .drop(labels=["exposure"], errors="ignore")
            .dropna()
            .sort_values(key=lambda s: s.abs(), ascending=False)
            .head(5)
        )
        for name, value in exposure_pairs.items():
            lines.append(f"- exposure(level) vs {name}: {value:.4f}")
    if not change_pearson.empty:
        exposure_change_cols = [c for c in change_pearson.columns if c.startswith("exposure_")]
        if exposure_change_cols:
            col = exposure_change_cols[0]
            pairs = (
                change_pearson[col]
                .drop(labels=[col], errors="ignore")
                .dropna()
                .sort_values(key=lambda s: s.abs(), ascending=False)
                .head(5)
            )
            for name, value in pairs.items():
                lines.append(f"- {col} vs {name}: {value:.4f}")
    (out_dir / "summary_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = load_source(args.source)
    level_df = build_level_frame(raw)
    change_df = build_change_frame(level_df)

    level_pearson = compute_corr(level_df, "pearson")
    level_spearman = compute_corr(level_df, "spearman")
    change_pearson = compute_corr(change_df, "pearson")
    change_spearman = compute_corr(change_df, "spearman")

    level_top = flatten_top_pairs(level_pearson, top_n=20)
    change_top = flatten_top_pairs(change_pearson, top_n=20)

    level_df.to_csv(out_dir / "macro_level_frame.csv", index=False, encoding="utf-8-sig")
    change_df.to_csv(out_dir / "macro_change_frame.csv", index=False, encoding="utf-8-sig")
    level_pearson.to_csv(out_dir / "macro_level_pearson.csv", encoding="utf-8-sig")
    level_spearman.to_csv(out_dir / "macro_level_spearman.csv", encoding="utf-8-sig")
    change_pearson.to_csv(out_dir / "macro_change_pearson.csv", encoding="utf-8-sig")
    change_spearman.to_csv(out_dir / "macro_change_spearman.csv", encoding="utf-8-sig")
    level_top.to_csv(out_dir / "top_abs_level_pearson_pairs.csv", index=False, encoding="utf-8-sig")
    change_top.to_csv(out_dir / "top_abs_change_pearson_pairs.csv", index=False, encoding="utf-8-sig")

    render_heatmap(level_pearson, "Macro Level Correlation (Pearson)", out_dir / "macro_level_pearson_heatmap.png")
    render_heatmap(change_pearson, "Macro Change Correlation (Pearson)", out_dir / "macro_change_pearson_heatmap.png")

    meta = {
        "source": str(args.source),
        "out_dir": str(out_dir),
        "date_min": str(level_df["date"].min().date()) if not level_df.empty else "",
        "date_max": str(level_df["date"].max().date()) if not level_df.empty else "",
        "level_rows": int(len(level_df)),
        "change_rows": int(len(change_df)),
        "level_columns": [col for col in level_df.columns if col != "date"],
        "change_columns": [col for col in change_df.columns if col != "date"],
    }
    (out_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    write_summary(
        out_dir,
        source_path=args.source,
        level_df=level_df,
        change_df=change_df,
        level_pearson=level_pearson,
        change_pearson=change_pearson,
        level_top=level_top,
        change_top=change_top,
    )
    print(f"[done] outputs written to {out_dir}")


if __name__ == "__main__":
    main()
