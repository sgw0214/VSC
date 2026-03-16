from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from new_strategy.paths import data_path, output_path


def _parse_window_range(text: str) -> list[int]:
    start_text, end_text = text.split("-", 1)
    start = int(start_text)
    end = int(end_text)
    if start <= 0 or end < start:
        raise ValueError(f"invalid window range: {text}")
    return list(range(start, end + 1))


def _resample_close(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    rule = {
        "daily": None,
        "weekly": "W-FRI",
        "monthly": "M",
    }[timeframe]

    if timeframe == "daily":
        return frame[["date", "close"]].dropna().sort_values("date").reset_index(drop=True)

    ts = (
        frame.set_index("date")["close"]
        .sort_index()
        .resample(rule)
        .last()
        .dropna()
        .rename("close")
        .reset_index()
    )
    return ts


def _evaluate_windows(
    closes: np.ndarray,
    windows: Iterable[int],
    *,
    min_valid_points: int,
) -> list[dict[str, float]]:
    values = np.asarray(closes, dtype=float)
    n = len(values)
    if n == 0:
        return []

    csum = np.concatenate(([0.0], np.cumsum(values, dtype=float)))
    results: list[dict[str, float]] = []
    for window in windows:
        valid_count = n - window + 1
        required_valid = max(min_valid_points, window)
        if valid_count < required_valid:
            continue

        ma = (csum[window:] - csum[:-window]) / float(window)
        close = values[window - 1 :]
        abs_err = np.abs(close - ma)
        abs_pct = np.abs(close / ma - 1.0)

        results.append(
            {
                "window": int(window),
                "valid_points": int(valid_count),
                "mean_abs_error": float(np.mean(abs_err)),
                "median_abs_error": float(np.median(abs_err)),
                "rmse_error": float(np.sqrt(np.mean(np.square(close - ma)))),
                "mean_abs_pct_error": float(np.mean(abs_pct)),
                "median_abs_pct_error": float(np.median(abs_pct)),
                "rmse_pct_error": float(np.sqrt(np.mean(np.square(close / ma - 1.0)))),
            }
        )
    return results


def analyze_stock(
    code: str,
    name: str,
    frame: pd.DataFrame,
    *,
    daily_windows: list[int],
    weekly_windows: list[int],
    monthly_windows: list[int],
    min_valid_points: int,
    top_k: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    summary_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []

    for timeframe, windows in (
        ("daily", daily_windows),
        ("weekly", weekly_windows),
        ("monthly", monthly_windows),
    ):
        period_df = _resample_close(frame, timeframe)
        if period_df.empty:
            continue

        metrics = _evaluate_windows(
            period_df["close"].to_numpy(dtype=float),
            windows,
            min_valid_points=min_valid_points,
        )
        if not metrics:
            continue

        ranked = sorted(
            metrics,
            key=lambda row: (
                row["mean_abs_pct_error"],
                row["mean_abs_error"],
                row["window"],
            ),
        )
        best = ranked[0]
        summary_rows.append(
            {
                "code": code,
                "name": name,
                "timeframe": timeframe,
                "best_window": int(best["window"]),
                "best_mean_abs_pct_error": float(best["mean_abs_pct_error"]),
                "best_mean_abs_error": float(best["mean_abs_error"]),
                "best_rmse_pct_error": float(best["rmse_pct_error"]),
                "series_points": int(len(period_df)),
                "series_start": period_df["date"].min().date().isoformat(),
                "series_end": period_df["date"].max().date().isoformat(),
            }
        )

        for rank, row in enumerate(ranked[:top_k], start=1):
            candidate_rows.append(
                {
                    "code": code,
                    "name": name,
                    "timeframe": timeframe,
                    "rank": rank,
                    **row,
                }
            )

    return summary_rows, candidate_rows


def build_report(
    summary_df: pd.DataFrame,
    distribution_df: pd.DataFrame,
    out_dir: Path,
    *,
    min_valid_points: int,
    daily_range: str,
    weekly_range: str,
    monthly_range: str,
    source_path: Path,
) -> None:
    lines: list[str] = []
    lines.append("# Optimal Moving Average Window Research")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- source dataset: `{source_path}`")
    lines.append(f"- metric for ranking: `mean_abs_pct_error = mean(abs(close / ma - 1))`")
    lines.append(f"- min valid points per window: `{min_valid_points}`")
    lines.append(f"- daily candidate windows: `{daily_range}`")
    lines.append(f"- weekly candidate windows: `{weekly_range}`")
    lines.append(f"- monthly candidate windows: `{monthly_range}`")
    lines.append("")
    lines.append("## Important Caveat")
    lines.append("- this objective measures `how tightly the moving average tracks close`, not `how useful it is for trading`")
    lines.append("- because of that, shorter windows are structurally favored and may dominate the ranking")
    lines.append("- treat this output as a tracking-error study, not as a direct replacement for strategy windows")
    lines.append("")
    lines.append("## Coverage")
    lines.append(f"- analyzed stock-timeframe rows: `{len(summary_df):,}`")
    if not summary_df.empty:
        stock_count = summary_df["code"].nunique()
        lines.append(f"- analyzed stocks: `{stock_count:,}`")
        lines.append(
            f"- data span: `{summary_df['series_start'].min()}` -> `{summary_df['series_end'].max()}`"
        )
    lines.append("")
    lines.append("## Most Common Best Windows")
    if distribution_df.empty:
        lines.append("- no distribution rows")
    else:
        for timeframe in ["daily", "weekly", "monthly"]:
            subset = distribution_df[distribution_df["timeframe"] == timeframe].head(10)
            lines.append(f"### {timeframe}")
            if subset.empty:
                lines.append("- no rows")
                continue
            lines.append("| rank | window | stocks | share | avg_best_error_pct | median_best_error_pct |")
            lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
            for idx, (_, row) in enumerate(subset.iterrows(), start=1):
                lines.append(
                    f"| {idx} | {int(row['best_window'])} | {int(row['stock_count'])} | "
                    f"{row['stock_share']:.4f} | {row['avg_best_error_pct']:.6f} | {row['median_best_error_pct']:.6f} |"
                )
            lines.append("")

    (out_dir / "summary_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find per-stock MA windows with the smallest close-tracking error by timeframe."
    )
    parser.add_argument("--source", type=Path, default=data_path("feature_daily.pkl"))
    parser.add_argument("--out-dir", type=Path, default=output_path("ma_window_research"))
    parser.add_argument("--daily-range", default="5-240")
    parser.add_argument("--weekly-range", default="4-60")
    parser.add_argument("--monthly-range", default="3-36")
    parser.add_argument("--min-valid-points", type=int, default=24)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit-codes", type=int, default=0, help="debug/test limit on stock count")
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    daily_windows = _parse_window_range(args.daily_range)
    weekly_windows = _parse_window_range(args.weekly_range)
    monthly_windows = _parse_window_range(args.monthly_range)

    df = pd.read_pickle(args.source)
    cols = [c for c in ["date", "code", "name", "close"] if c in df.columns]
    df = df[cols].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["code"] = df["code"].astype(str).str.zfill(6)
    df = df.dropna(subset=["date", "code", "close"]).sort_values(["code", "date"]).reset_index(drop=True)

    if args.limit_codes > 0:
        keep_codes = df["code"].drop_duplicates().head(args.limit_codes)
        df = df[df["code"].isin(set(keep_codes))].copy()

    summary_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []

    grouped = df.groupby("code", sort=False)
    total_codes = grouped.ngroups
    for idx, (code, grp) in enumerate(grouped, start=1):
        name = str(grp["name"].dropna().iloc[-1]) if grp["name"].notna().any() else code
        stock_summary, stock_candidates = analyze_stock(
            code,
            name,
            grp[["date", "close"]].assign(name=name),
            daily_windows=daily_windows,
            weekly_windows=weekly_windows,
            monthly_windows=monthly_windows,
            min_valid_points=args.min_valid_points,
            top_k=args.top_k,
        )
        summary_rows.extend(stock_summary)
        candidate_rows.extend(stock_candidates)

        if idx % 200 == 0 or idx == total_codes:
            print(f"[progress] {idx}/{total_codes} codes processed")

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(["timeframe", "code"]).reset_index(drop=True)

    candidates_df = pd.DataFrame(candidate_rows)
    if not candidates_df.empty:
        candidates_df = candidates_df.sort_values(["timeframe", "code", "rank"]).reset_index(drop=True)

    if summary_df.empty:
        distribution_df = pd.DataFrame(
            columns=[
                "timeframe",
                "best_window",
                "stock_count",
                "avg_best_error_pct",
                "median_best_error_pct",
                "stock_share",
            ]
        )
    else:
        distribution_df = (
            summary_df.groupby(["timeframe", "best_window"], as_index=False)
            .agg(
                stock_count=("code", "nunique"),
                avg_best_error_pct=("best_mean_abs_pct_error", "mean"),
                median_best_error_pct=("best_mean_abs_pct_error", "median"),
            )
            .sort_values(["timeframe", "stock_count", "best_window"], ascending=[True, False, True])
            .reset_index(drop=True)
        )
        totals = distribution_df.groupby("timeframe")["stock_count"].transform("sum")
        distribution_df["stock_share"] = distribution_df["stock_count"] / totals

    meta = {
        "source": str(args.source),
        "out_dir": str(out_dir),
        "daily_range": args.daily_range,
        "weekly_range": args.weekly_range,
        "monthly_range": args.monthly_range,
        "min_valid_points": args.min_valid_points,
        "top_k": args.top_k,
        "limit_codes": args.limit_codes,
        "codes_analyzed": int(summary_df["code"].nunique()) if not summary_df.empty else 0,
        "stock_timeframe_rows": int(len(summary_df)),
    }

    summary_df.to_csv(out_dir / "best_ma_by_stock.csv", index=False, encoding="utf-8-sig")
    candidates_df.to_csv(out_dir / "top_ma_candidates_by_stock.csv", index=False, encoding="utf-8-sig")
    distribution_df.to_csv(out_dir / "best_window_distribution.csv", index=False, encoding="utf-8-sig")
    (out_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    build_report(
        summary_df,
        distribution_df,
        out_dir,
        min_valid_points=args.min_valid_points,
        daily_range=args.daily_range,
        weekly_range=args.weekly_range,
        monthly_range=args.monthly_range,
        source_path=args.source,
    )

    print(f"[done] outputs written to {out_dir}")


if __name__ == "__main__":
    main()
