from __future__ import annotations

from pathlib import Path

import pandas as pd

from new_strategy.paths import output_path


PUBLISHED_SELECTION = output_path(
    "ma_breakout_research",
    "published",
    "optimal_ma_selection_all_timeframes.csv",
)
CANDIDATE_RESULTS = output_path(
    "ma_breakout_research",
    "all_action_modes_returns_by_stock.csv",
)
OUT_DIR = output_path("v2_monthly_plateau_rule_shift")


def _ratio_bucket(value: float) -> str:
    if pd.isna(value):
        return "unknown"
    if value <= 0.1:
        return "<=0.1"
    if value <= 0.2:
        return "0.1~0.2"
    if value <= 0.3:
        return "0.2~0.3"
    if value <= 0.4:
        return "0.3~0.4"
    if value <= 0.5:
        return "0.4~0.5"
    if value <= 1.0:
        return "0.5~1.0"
    if value <= 1.5:
        return "1.0~1.5"
    return ">1.5"


def _threshold_value(best_total: float, keep_ratio: float) -> float:
    if best_total >= 0:
        return best_total * keep_ratio
    return best_total / keep_ratio


def _choose_shortest_within_total(group: pd.DataFrame, keep_ratio: float) -> pd.Series:
    best_total = float(group["total_return"].max())
    threshold = _threshold_value(best_total, keep_ratio)
    eligible = group.loc[group["total_return"] >= threshold].copy()
    if eligible.empty:
        eligible = group.copy()
    eligible = eligible.sort_values(
        ["ma_window", "excess_return", "max_drawdown", "annualized_return"],
        ascending=[True, False, False, False],
    )
    return eligible.iloc[0]


def _choose_mean_within_total(group: pd.DataFrame, keep_ratio: float) -> pd.Series:
    best_total = float(group["total_return"].max())
    threshold = _threshold_value(best_total, keep_ratio)
    eligible = group.loc[group["total_return"] >= threshold].copy()
    if eligible.empty:
        eligible = group.copy()
    mean_window = float(eligible["ma_window"].mean())
    eligible["distance_to_mean"] = (eligible["ma_window"] - mean_window).abs()
    eligible = eligible.sort_values(
        ["distance_to_mean", "ma_window", "excess_return", "max_drawdown", "annualized_return"],
        ascending=[True, True, False, False, False],
    )
    return eligible.iloc[0]


def _load_published() -> pd.DataFrame:
    df = pd.read_csv(PUBLISHED_SELECTION, dtype={"code": str}, low_memory=False)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["ma_window"] = pd.to_numeric(df["ma_window"], errors="coerce")
    work = df.loc[
        (df["action_mode"] == "native_timeframe_close")
        & (df["ma_timeframe"].isin(["monthly", "weekly"]))
    ].copy()
    monthly = (
        work.loc[work["ma_timeframe"] == "monthly", ["code", "name", "ma_window"]]
        .rename(columns={"ma_window": "monthly_window_current"})
        .drop_duplicates(subset=["code"])
    )
    weekly = (
        work.loc[work["ma_timeframe"] == "weekly", ["code", "ma_window"]]
        .rename(columns={"ma_window": "weekly_window"})
        .drop_duplicates(subset=["code"])
    )
    return monthly.merge(weekly, on="code", how="inner")


def _load_monthly_candidates() -> pd.DataFrame:
    df = pd.read_csv(CANDIDATE_RESULTS, dtype={"code": str}, low_memory=False)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["ma_window"] = pd.to_numeric(df["ma_window"], errors="coerce")
    numeric_cols = [
        "total_return",
        "buy_hold_return",
        "excess_return",
        "annualized_return",
        "max_drawdown",
        "win_rate",
        "completed_trade_count",
        "trade_count",
        "exposure_ratio",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.loc[
        (df["action_mode"] == "native_timeframe_close")
        & (df["ma_timeframe"] == "monthly")
        & (df["ma_window"] >= 1)
    ].copy()


def _build_rule_selection(candidates: pd.DataFrame, keep_ratio: float, rule_name: str) -> pd.DataFrame:
    rows = []
    for _, group in candidates.groupby("code", sort=False):
        rows.append(_choose_shortest_within_total(group, keep_ratio))
    chosen = pd.DataFrame(rows)
    return chosen.rename(
        columns={
            "ma_window": f"monthly_window_{rule_name}",
            "total_return": f"monthly_total_return_{rule_name}",
            "excess_return": f"monthly_excess_return_{rule_name}",
        }
    )[
        [
            "code",
            f"monthly_window_{rule_name}",
            f"monthly_total_return_{rule_name}",
            f"monthly_excess_return_{rule_name}",
        ]
    ]


def _build_mean_rule_selection(candidates: pd.DataFrame, keep_ratio: float, rule_name: str) -> pd.DataFrame:
    rows = []
    for _, group in candidates.groupby("code", sort=False):
        rows.append(_choose_mean_within_total(group, keep_ratio))
    chosen = pd.DataFrame(rows)
    return chosen.rename(
        columns={
            "ma_window": f"monthly_window_{rule_name}",
            "total_return": f"monthly_total_return_{rule_name}",
            "excess_return": f"monthly_excess_return_{rule_name}",
        }
    )[
        [
            "code",
            f"monthly_window_{rule_name}",
            f"monthly_total_return_{rule_name}",
            f"monthly_excess_return_{rule_name}",
        ]
    ]


def _make_ratio_frame(base: pd.DataFrame) -> pd.DataFrame:
    out = base.copy()
    for col in [
        "monthly_window_current",
        "monthly_window_short95",
        "monthly_window_short90",
        "monthly_window_mean95",
    ]:
        ratio_col = col.replace("monthly_window_", "ratio_")
        bucket_col = col.replace("monthly_window_", "bucket_")
        out[ratio_col] = out["weekly_window"] / (out[col] * 4.345)
        out[bucket_col] = out[ratio_col].map(_ratio_bucket)
    return out


def _build_bucket_summary(frame: pd.DataFrame, prefix: str, label: str) -> pd.DataFrame:
    bucket_col = f"bucket_{prefix}"
    ratio_col = f"ratio_{prefix}"
    window_col = f"monthly_window_{prefix}"
    summary = (
        frame.groupby(bucket_col, as_index=False)
        .agg(
            stock_count=("code", "nunique"),
            ratio_mean=(ratio_col, "mean"),
            ratio_median=(ratio_col, "median"),
            monthly_window_mean=(window_col, "mean"),
            monthly_window_median=(window_col, "median"),
        )
        .rename(columns={bucket_col: "ratio_bucket"})
    )
    summary["rule"] = label
    order = {
        "<=0.1": 0,
        "0.1~0.2": 1,
        "0.2~0.3": 2,
        "0.3~0.4": 3,
        "0.4~0.5": 4,
        "0.5~1.0": 5,
        "1.0~1.5": 6,
        ">1.5": 7,
    }
    return summary.sort_values("ratio_bucket", key=lambda s: s.map(order)).reset_index(drop=True)


def _headline_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for prefix, label in [
        ("current", "current"),
        ("short95", "short95"),
        ("short90", "short90"),
        ("mean95", "mean95"),
    ]:
        bucket_col = f"bucket_{prefix}"
        rows.append(
            {
                "rule": label,
                "stock_count": int(frame["code"].nunique()),
                "share_leq_01": float((frame[bucket_col] == "<=0.1").mean()),
                "share_leq_05": float(frame[bucket_col].isin(["<=0.1", "0.1~0.2", "0.2~0.3", "0.3~0.4", "0.4~0.5"]).mean()),
                "median_monthly_window": float(frame[f"monthly_window_{prefix}"].median()),
                "median_ratio": float(frame[f"ratio_{prefix}"].median()),
            }
        )
    return pd.DataFrame(rows)


def _migration_summary(frame: pd.DataFrame, target_prefix: str) -> pd.DataFrame:
    current = "bucket_current"
    target = f"bucket_{target_prefix}"
    pivot = (
        frame.groupby([current, target], as_index=False)
        .agg(stock_count=("code", "nunique"))
        .rename(columns={current: "from_bucket", target: "to_bucket"})
    )
    return pivot


def _top_changes(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    out = frame[
        [
            "code",
            "name",
            "weekly_window",
            "monthly_window_current",
            f"monthly_window_{prefix}",
            "ratio_current",
            f"ratio_{prefix}",
            "bucket_current",
            f"bucket_{prefix}",
        ]
    ].copy()
    out["monthly_window_delta"] = out[f"monthly_window_{prefix}"] - out["monthly_window_current"]
    out["ratio_delta"] = out[f"ratio_{prefix}"] - out["ratio_current"]
    out["abs_ratio_delta"] = out["ratio_delta"].abs()
    return out.sort_values(["abs_ratio_delta", "monthly_window_delta"], ascending=[False, True]).reset_index(drop=True)


def _write_markdown(
    path: Path,
    headline: pd.DataFrame,
    bucket_summary: pd.DataFrame,
    migration_95: pd.DataFrame,
    migration_90: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Monthly Plateau Rule Shift")
    lines.append("")
    lines.append("## Rules")
    lines.append("- `current`: published monthly selection")
    lines.append("- `short95`: among monthly candidates within 95% of the best monthly total return, choose the shortest monthly window")
    lines.append("- `short90`: among monthly candidates within 90% of the best monthly total return, choose the shortest monthly window")
    lines.append("- `mean95`: among monthly candidates within 95% of the best monthly total return, choose the monthly window nearest to the mean of that plateau")
    lines.append("- weekly window stays unchanged")
    lines.append("")
    lines.append("## Headline")
    lines.append("| rule | stock_count | share_leq_01 | share_leq_05 | median_monthly_window | median_ratio |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for row in headline.itertuples(index=False):
        lines.append(
            f"| {row.rule} | {int(row.stock_count)} | {row.share_leq_01:.4f} | {row.share_leq_05:.4f} | {row.median_monthly_window:.1f} | {row.median_ratio:.4f} |"
        )
    lines.append("")
    lines.append("## Bucket Summary")
    lines.append("| rule | ratio_bucket | stock_count | ratio_median | monthly_window_median |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    for row in bucket_summary.itertuples(index=False):
        lines.append(
            f"| {row.rule} | {row.ratio_bucket} | {int(row.stock_count)} | {row.ratio_median:.4f} | {row.monthly_window_median:.1f} |"
        )
    lines.append("")
    lines.append("## Migration: current -> short95")
    lines.append("| from_bucket | to_bucket | stock_count |")
    lines.append("| --- | --- | ---: |")
    for row in migration_95.itertuples(index=False):
        lines.append(f"| {row.from_bucket} | {row.to_bucket} | {int(row.stock_count)} |")
    lines.append("")
    lines.append("## Migration: current -> short90")
    lines.append("| from_bucket | to_bucket | stock_count |")
    lines.append("| --- | --- | ---: |")
    for row in migration_90.itertuples(index=False):
        lines.append(f"| {row.from_bucket} | {row.to_bucket} | {int(row.stock_count)} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    published = _load_published()
    monthly_candidates = _load_monthly_candidates()

    short95 = _build_rule_selection(monthly_candidates, 0.95, "short95")
    short90 = _build_rule_selection(monthly_candidates, 0.90, "short90")
    mean95 = _build_mean_rule_selection(monthly_candidates, 0.95, "mean95")

    merged = (
        published.merge(short95, on="code", how="left")
        .merge(short90, on="code", how="left")
        .merge(mean95, on="code", how="left")
    )
    merged = _make_ratio_frame(merged)

    headline = _headline_summary(merged)
    bucket_parts = [
        _build_bucket_summary(merged, "current", "current"),
        _build_bucket_summary(merged, "short95", "short95"),
        _build_bucket_summary(merged, "short90", "short90"),
        _build_bucket_summary(merged, "mean95", "mean95"),
    ]
    bucket_summary = pd.concat(bucket_parts, ignore_index=True)
    migration_95 = _migration_summary(merged, "short95")
    migration_90 = _migration_summary(merged, "short90")
    top_changes_95 = _top_changes(merged, "short95")
    top_changes_90 = _top_changes(merged, "short90")
    top_changes_mean95 = _top_changes(merged, "mean95")

    merged.to_csv(OUT_DIR / "monthly_rule_shift_by_stock.csv", index=False, encoding="utf-8-sig")
    headline.to_csv(OUT_DIR / "headline_summary.csv", index=False, encoding="utf-8-sig")
    bucket_summary.to_csv(OUT_DIR / "bucket_summary.csv", index=False, encoding="utf-8-sig")
    migration_95.to_csv(OUT_DIR / "migration_current_to_short95.csv", index=False, encoding="utf-8-sig")
    migration_90.to_csv(OUT_DIR / "migration_current_to_short90.csv", index=False, encoding="utf-8-sig")
    top_changes_95.to_csv(OUT_DIR / "top_changes_short95.csv", index=False, encoding="utf-8-sig")
    top_changes_90.to_csv(OUT_DIR / "top_changes_short90.csv", index=False, encoding="utf-8-sig")
    top_changes_mean95.to_csv(OUT_DIR / "top_changes_mean95.csv", index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(OUT_DIR / "monthly_rule_shift_analysis.xlsx", engine="openpyxl") as writer:
        headline.to_excel(writer, index=False, sheet_name="headline")
        bucket_summary.to_excel(writer, index=False, sheet_name="bucket_summary")
        migration_95.to_excel(writer, index=False, sheet_name="migration_95")
        migration_90.to_excel(writer, index=False, sheet_name="migration_90")
        top_changes_95.head(100).to_excel(writer, index=False, sheet_name="top_changes_95")
        top_changes_90.head(100).to_excel(writer, index=False, sheet_name="top_changes_90")
        top_changes_mean95.head(100).to_excel(writer, index=False, sheet_name="top_changes_mean95")

    _write_markdown(
        OUT_DIR / "summary_report.md",
        headline=headline,
        bucket_summary=bucket_summary,
        migration_95=migration_95,
        migration_90=migration_90,
    )


if __name__ == "__main__":
    main()
