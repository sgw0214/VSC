from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from new_strategy.paths import output_path


SAFE_RETURN_COL = "안전수익률"


def _parse_percent_or_float(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.replace({"": np.nan, "nan": np.nan, "None": np.nan})
    has_percent = s.str.contains("%", regex=False, na=False)
    cleaned = s.str.replace("%", "", regex=False).str.replace(",", "", regex=False)
    numeric = pd.to_numeric(cleaned, errors="coerce")
    numeric.loc[has_percent] = numeric.loc[has_percent] / 100.0
    return numeric


def load_distribution(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    for col in [
        "ma_window",
        "stock_count",
        "avg_total_return",
        "median_total_return",
        "avg_max_drawdown",
        "stock_share",
        SAFE_RETURN_COL,
    ]:
        if col in {"ma_window", "stock_count"}:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = _parse_percent_or_float(df[col])
    return df


def load_native_returns(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"code": str})
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def build_safe_candidates(distribution_df: pd.DataFrame) -> pd.DataFrame:
    safe_df = distribution_df[
        (distribution_df["action_mode"] == "native_timeframe_close")
        & (distribution_df["ma_timeframe"].isin(["monthly", "weekly"]))
        & (distribution_df[SAFE_RETURN_COL] >= 0)
    ].copy()
    safe_df = safe_df.sort_values(
        ["ma_timeframe", SAFE_RETURN_COL, "median_total_return", "stock_share", "ma_window"],
        ascending=[True, False, False, False, True],
    ).reset_index(drop=True)
    return safe_df


def _timeframe_priority(series: pd.Series) -> pd.Series:
    return series.map({"monthly": 0, "weekly": 1}).fillna(9).astype(int)


def select_per_stock(native_df: pd.DataFrame, safe_df: pd.DataFrame) -> pd.DataFrame:
    eligible = native_df[native_df["ma_timeframe"].isin(["monthly", "weekly"])].copy()
    safe_keys = safe_df[["ma_timeframe", "ma_window"]].drop_duplicates().copy()
    safe_keys["is_safe_candidate"] = True

    dist_cols = [
        "ma_timeframe",
        "ma_window",
        "stock_count",
        "avg_total_return",
        "median_total_return",
        "avg_max_drawdown",
        "stock_share",
        SAFE_RETURN_COL,
    ]
    eligible = eligible.merge(safe_keys, on=["ma_timeframe", "ma_window"], how="left")
    eligible["is_safe_candidate"] = eligible["is_safe_candidate"].fillna(False)
    eligible = eligible.merge(
        safe_df[dist_cols],
        on=["ma_timeframe", "ma_window"],
        how="left",
        suffixes=("", "_dist"),
    )
    eligible["timeframe_priority"] = _timeframe_priority(eligible["ma_timeframe"])

    selected_rows = []
    for _, grp in eligible.groupby("code", sort=False):
        grp = grp.copy()
        safe_grp = grp[grp["is_safe_candidate"]]
        if not safe_grp.empty:
            ranked = safe_grp.sort_values(
                ["total_return", "annualized_return", "timeframe_priority", "ma_window"],
                ascending=[False, False, True, True],
            )
            chosen = ranked.iloc[0].copy()
            chosen["selection_source"] = "safe_candidate"
        else:
            ranked = grp.sort_values(
                ["total_return", "annualized_return", "timeframe_priority", "ma_window"],
                ascending=[False, False, True, True],
            )
            chosen = ranked.iloc[0].copy()
            chosen["selection_source"] = "fallback"
        selected_rows.append(chosen)

    selected_df = pd.DataFrame(selected_rows).reset_index(drop=True)
    selected_df = selected_df.rename(
        columns={
            "ma_timeframe": "selected_ma_timeframe",
            "ma_window": "selected_ma_window",
            "stock_count": "distribution_stock_count",
            "avg_total_return": "distribution_avg_total_return",
            "median_total_return": "distribution_median_total_return",
            "avg_max_drawdown": "distribution_avg_max_drawdown",
            "stock_share": "distribution_stock_share",
            SAFE_RETURN_COL: "distribution_safe_return",
        }
    )
    selected_df = selected_df.sort_values(["selection_source", "selected_ma_timeframe", "code"]).reset_index(drop=True)
    return selected_df


def build_strategy_ready(selected_df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "code",
        "name",
        "selected_ma_timeframe",
        "selected_ma_window",
        "selection_source",
        "distribution_safe_return",
        "distribution_stock_share",
        "total_return",
        "annualized_return",
        "max_drawdown",
        "trade_count",
        "win_rate",
        "test_start",
        "test_end",
    ]
    return selected_df[cols].copy()


def write_json(path: Path, frame: pd.DataFrame) -> None:
    records = frame.to_dict(orient="records")
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def build_markdown_summary(
    out_dir: Path,
    *,
    safe_df: pd.DataFrame,
    selected_df: pd.DataFrame,
) -> None:
    fallback_df = selected_df[selected_df["selection_source"] == "fallback"]
    safe_selected_df = selected_df[selected_df["selection_source"] == "safe_candidate"]

    lines: list[str] = []
    lines.append("# Strategy MA Selection Summary")
    lines.append("")
    lines.append("## Rule")
    lines.append("- input action mode: `native_timeframe_close` only")
    lines.append("- input timeframes: `monthly`, `weekly` only")
    lines.append(f"- safe candidate criterion: `{SAFE_RETURN_COL} >= 0` from reviewed distribution file")
    lines.append("- per-stock selection: choose the highest `total_return` within safe candidates")
    lines.append("- fallback: if no safe candidate exists for a stock, choose the highest `total_return` across monthly/weekly rows")
    lines.append("- tie break: higher `total_return` -> higher `annualized_return` -> `monthly` priority -> smaller window")
    lines.append("")
    lines.append("## Safe Candidate Coverage")
    if safe_df.empty:
        lines.append("- no safe candidates")
    else:
        coverage = (
            safe_df.groupby("ma_timeframe", as_index=False)
            .agg(
                safe_window_count=("ma_window", "count"),
                safe_stock_share_sum=("stock_share", "sum"),
            )
            .sort_values("ma_timeframe")
        )
        lines.append("| timeframe | safe_window_count | cumulative_stock_share |")
        lines.append("| --- | ---: | ---: |")
        for _, row in coverage.iterrows():
            lines.append(
                f"| {row['ma_timeframe']} | {int(row['safe_window_count'])} | {row['safe_stock_share_sum']:.4f} |"
            )
    lines.append("")
    lines.append("## Final Selection")
    lines.append(f"- selected stocks: `{selected_df['code'].nunique():,}`")
    lines.append(f"- safe-candidate selections: `{len(safe_selected_df):,}`")
    lines.append(f"- fallback selections: `{len(fallback_df):,}`")
    lines.append("")
    if not selected_df.empty:
        timeframe_mix = selected_df["selected_ma_timeframe"].value_counts()
        lines.append("### Timeframe Mix")
        for timeframe, count in timeframe_mix.items():
            lines.append(f"- {timeframe}: `{int(count)}`")
        lines.append("")
        top_windows = (
            selected_df.groupby(["selected_ma_timeframe", "selected_ma_window"], as_index=False)
            .agg(stock_count=("code", "nunique"))
            .sort_values(["selected_ma_timeframe", "stock_count", "selected_ma_window"], ascending=[True, False, True])
        )
        lines.append("### Top Selected Windows")
        lines.append("| timeframe | window | stocks |")
        lines.append("| --- | ---: | ---: |")
        for _, row in top_windows.head(12).iterrows():
            lines.append(f"| {row['selected_ma_timeframe']} | {int(row['selected_ma_window'])} | {int(row['stock_count'])} |")

    (out_dir / "summary_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build per-stock MA selection for strategy consumption from reviewed breakout outputs.")
    parser.add_argument(
        "--distribution",
        type=Path,
        default=output_path("ma_breakout_research", "best_window_distribution.csv"),
    )
    parser.add_argument(
        "--native-returns",
        type=Path,
        default=output_path("ma_breakout_research", "native_timeframe_close_returns_by_stock.csv"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=output_path("ma_breakout_strategy_selection"),
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    distribution_df = load_distribution(args.distribution)
    native_df = load_native_returns(args.native_returns)
    safe_df = build_safe_candidates(distribution_df)
    selected_df = select_per_stock(native_df, safe_df)
    fallback_df = selected_df[selected_df["selection_source"] == "fallback"].copy()
    strategy_ready_df = build_strategy_ready(selected_df)

    safe_df.to_csv(args.out_dir / "safe_candidate_windows.csv", index=False, encoding="utf-8-sig")
    selected_df.to_csv(args.out_dir / "stock_final_ma_selection.csv", index=False, encoding="utf-8-sig")
    fallback_df.to_csv(args.out_dir / "fallback_stocks.csv", index=False, encoding="utf-8-sig")
    strategy_ready_df.to_csv(args.out_dir / "strategy_ready_ma_selection.csv", index=False, encoding="utf-8-sig")
    write_json(args.out_dir / "strategy_ready_ma_selection.json", strategy_ready_df)

    meta = {
        "distribution_path": str(args.distribution),
        "native_returns_path": str(args.native_returns),
        "safe_candidate_count": int(len(safe_df)),
        "selected_stock_count": int(selected_df["code"].nunique()) if not selected_df.empty else 0,
        "fallback_stock_count": int(len(fallback_df)),
        "safe_return_column": SAFE_RETURN_COL,
        "selection_rule": "safe_candidate_first_then_fallback_by_total_return",
    }
    (args.out_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    build_markdown_summary(args.out_dir, safe_df=safe_df, selected_df=selected_df)
    print(f"[done] outputs written to {args.out_dir}")


if __name__ == "__main__":
    main()
