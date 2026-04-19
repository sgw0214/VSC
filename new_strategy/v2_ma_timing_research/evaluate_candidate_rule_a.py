from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from new_strategy.ma_breakout_research.backtest_ma_breakout_modes import (
    _rolling_mean,
    backtest_from_signal,
    build_completed_period_frame,
)
from new_strategy.paths import data_path, output_path
from new_strategy.v2_ma_timing_research.simulate_monthly_buy_weekly_sell_thresholds import (
    _build_buy_events,
    _build_monthly_frame,
    _build_sell_events,
    _build_weekly_frame,
    _simulate_daily_from_events,
)


BUY_THRESHOLD = 0.0
SELL_THRESHOLD = -0.05
MONTHLY_WINDOWS = list(range(2, 121))
WEEKLY_WINDOWS = list(range(2, 121))
MIN_BARS = 24


def _load_price_frame(source: Path) -> pd.DataFrame:
    df = pd.read_pickle(source)[["date", "code", "name", "open", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["code"] = df["code"].astype(str).str.zfill(6)
    for col in ["open", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return (
        df.dropna(subset=["date", "code", "close"])
        .sort_values(["code", "date"])
        .reset_index(drop=True)
    )


def _load_base_results(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def _load_weekly_only_results(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def _bucket_order(text: str) -> int:
    return {"<=0.5": 0, "0.5~1.0": 1, "1.0~1.5": 2, ">1.5": 3}.get(str(text), 99)


def _exclude_event_windows(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    work = frame[["date", "open", "close"]].copy().sort_values("date").reset_index(drop=True)
    work["prev_close"] = work["close"].shift(1)
    work["ret_1d"] = work["close"] / work["prev_close"] - 1.0
    work["gap_oc"] = work["open"] / work["prev_close"] - 1.0
    work["week_period"] = work["date"].dt.to_period("W-FRI")
    work["month_period"] = work["date"].dt.to_period("M")

    week_close = (
        work.groupby("week_period", as_index=False)
        .agg(close=("close", "last"))
        .sort_values("week_period")
        .reset_index(drop=True)
    )
    week_close["weekly_ret"] = week_close["close"].pct_change()
    event_weeks = set(week_close.loc[week_close["weekly_ret"].abs() >= 0.30, "week_period"].tolist())

    month_close = (
        work.groupby("month_period", as_index=False)
        .agg(close=("close", "last"))
        .sort_values("month_period")
        .reset_index(drop=True)
    )
    month_close["monthly_ret"] = month_close["close"].pct_change()
    event_months = set(month_close.loc[month_close["monthly_ret"].abs() >= 0.50, "month_period"].tolist())

    daily_event = (work["ret_1d"].abs() >= 0.15) | (work["gap_oc"].abs() >= 0.10)
    week_event = work["week_period"].isin(event_weeks)
    month_event = work["month_period"].isin(event_months)
    exclude_mask = daily_event.fillna(False) | week_event | month_event

    cleaned = work.loc[~exclude_mask, ["date", "close"]].copy().reset_index(drop=True)
    meta = {
        "excluded_days": int(exclude_mask.sum()),
        "excluded_daily_events": int(daily_event.fillna(False).sum()),
        "excluded_weeks": int(len(event_weeks)),
        "excluded_months": int(len(event_months)),
        "clean_rows": int(len(cleaned)),
    }
    return cleaned, meta


def _select_best_window(
    frame: pd.DataFrame,
    *,
    timeframe: str,
    windows: list[int],
    today: pd.Timestamp,
) -> tuple[int | None, dict[str, float] | None]:
    period_df = build_completed_period_frame(frame[["date", "close"]], timeframe, today=today)
    if len(period_df) < MIN_BARS:
        return None, None

    dates = period_df["decision_date"].to_numpy()
    prices = period_df["close"].to_numpy(dtype=float)
    periods_per_year = 12 if timeframe == "monthly" else 52
    rows: list[dict[str, float]] = []
    for window in windows:
        ma = _rolling_mean(prices, int(window))
        metrics = backtest_from_signal(dates, prices, ma, periods_per_year=periods_per_year)
        if not metrics:
            continue
        rows.append({"ma_window": int(window), **metrics})

    if not rows:
        return None, None

    ranked = pd.DataFrame(rows).sort_values(
        ["total_return", "max_drawdown", "completed_trade_count", "annualized_return", "win_rate", "ma_window"],
        ascending=[False, False, False, False, False, True],
    )
    best = ranked.iloc[0].to_dict()
    return int(best["ma_window"]), best


def _simulate_mixed_with_windows(
    stock_df: pd.DataFrame,
    *,
    monthly_window: int,
    weekly_window: int,
) -> dict[str, object]:
    base = stock_df[["date", "close"]].copy().sort_values("date").reset_index(drop=True)
    monthly_df = _build_monthly_frame(base)
    weekly_df = _build_weekly_frame(base)
    monthly_ma = _rolling_mean(monthly_df["close"].to_numpy(dtype=float), monthly_window)
    valid_monthly_dates = monthly_df.loc[np.isfinite(monthly_ma), "decision_date"]
    if valid_monthly_dates.empty:
        return {}
    start_date = pd.Timestamp(valid_monthly_dates.iloc[0])
    buy_events = _build_buy_events(monthly_df, monthly_window, BUY_THRESHOLD)
    sell_events = _build_sell_events(weekly_df, weekly_window, SELL_THRESHOLD)
    return _simulate_daily_from_events(base, buy_events, sell_events, start_date=start_date)


def _candidate_summary(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    grouped = df.groupby(group_cols, as_index=False)
    out = grouped.agg(
        stock_count=("code", "nunique"),
        avg_total_return=("total_return", "mean"),
        median_total_return=("total_return", "median"),
        avg_excess_return=("excess_return", "mean"),
        avg_annualized_return=("annualized_return", "mean"),
        avg_max_drawdown=("max_drawdown", "mean"),
        avg_trade_count=("trade_count", "mean"),
        avg_win_rate=("win_rate", "mean"),
        avg_exposure_ratio=("exposure_ratio", "mean"),
        p10_total_return=("total_return", lambda s: float(s.quantile(0.10))),
        p10_excess_return=("excess_return", lambda s: float(s.quantile(0.10))),
        p10_max_drawdown=("max_drawdown", lambda s: float(s.quantile(0.10))),
        positive_excess_share=("excess_return", lambda s: float((s > 0).mean())),
    )
    return out


def _write_report(
    out_path: Path,
    *,
    overall_summary: pd.DataFrame,
    bucket_summary: pd.DataFrame,
    reselection_meta: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Candidate Rule A Validation")
    lines.append("")
    lines.append("## Candidate Rule")
    lines.append("- `<=0.5`: event-excluded re-estimation, then monthly-buy / weekly-sell")
    lines.append("- `0.5~1.0`: monthly-buy / weekly-sell (mixed)")
    lines.append("- `1.0~1.5`: monthly-only")
    lines.append("- `>1.5`: weekly-only")
    lines.append("")
    lines.append("## Event Exclusion Rule for `<=0.5`")
    lines.append("- exclude days with absolute daily return >= 15%")
    lines.append("- exclude days with absolute open gap vs previous close >= 10%")
    lines.append("- exclude full weeks with absolute weekly return >= 30%")
    lines.append("- exclude full months with absolute monthly return >= 50%")
    lines.append("")
    lines.append("## Overall Summary")
    lines.append("| strategy | stock_count | avg_total_return | median_total_return | avg_excess_return | avg_max_drawdown | avg_trade_count | avg_win_rate | avg_exposure_ratio | p10_total_return | p10_max_drawdown | positive_excess_share |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in overall_summary.itertuples(index=False):
        lines.append(
            f"| {row.strategy} | {int(row.stock_count)} | {row.avg_total_return:.4f} | {row.median_total_return:.4f} | "
            f"{row.avg_excess_return:.4f} | {row.avg_max_drawdown:.4f} | {row.avg_trade_count:.2f} | "
            f"{row.avg_win_rate:.4f} | {row.avg_exposure_ratio:.4f} | {row.p10_total_return:.4f} | "
            f"{row.p10_max_drawdown:.4f} | {row.positive_excess_share:.4f} |"
        )
    lines.append("")
    lines.append("## Candidate A By Bucket")
    lines.append("| ratio_bucket | stock_count | avg_total_return | median_total_return | avg_excess_return | avg_max_drawdown | avg_trade_count | avg_win_rate | avg_exposure_ratio | p10_total_return | p10_max_drawdown | positive_excess_share |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    bucket_order = {"<=0.5": 0, "0.5~1.0": 1, "1.0~1.5": 2, ">1.5": 3}
    bucket_summary = bucket_summary.sort_values("ratio_bucket", key=lambda s: s.map(bucket_order))
    for row in bucket_summary.itertuples(index=False):
        lines.append(
            f"| {row.ratio_bucket} | {int(row.stock_count)} | {row.avg_total_return:.4f} | {row.median_total_return:.4f} | "
            f"{row.avg_excess_return:.4f} | {row.avg_max_drawdown:.4f} | {row.avg_trade_count:.2f} | "
            f"{row.avg_win_rate:.4f} | {row.avg_exposure_ratio:.4f} | {row.p10_total_return:.4f} | "
            f"{row.p10_max_drawdown:.4f} | {row.positive_excess_share:.4f} |"
        )
    lines.append("")
    lines.append("## `<=0.5` Re-estimation Coverage")
    lines.append("| stock_count | avg_excluded_days | median_excluded_days | avg_excluded_weeks | avg_excluded_months | avg_original_ratio | avg_reselected_ratio | improved_to_gt_0.5_share | fallback_share |")
    lines.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    if not reselection_meta.empty:
        row = reselection_meta.iloc[0]
        lines.append(
            f"| {int(row['stock_count'])} | {row['avg_excluded_days']:.2f} | {row['median_excluded_days']:.2f} | "
            f"{row['avg_excluded_weeks']:.2f} | {row['avg_excluded_months']:.2f} | {row['avg_original_ratio']:.4f} | "
            f"{row['avg_reselected_ratio']:.4f} | {row['improved_to_gt_0_5_share']:.4f} | {row['fallback_share']:.4f} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    price_source = data_path("feature_daily.pkl")
    monthly_mixed_source = output_path("v2_monthly_only_vs_optimal_vs_conditional", "stock_results.csv")
    weekly_only_source = output_path("v2_weekly_only_same_engine", "stock_weekly_only_results.csv")
    out_dir = output_path("v2_candidate_rule_a_validation")
    out_dir.mkdir(parents=True, exist_ok=True)

    prices = _load_price_frame(price_source)
    base = _load_base_results(monthly_mixed_source)
    weekly_only = _load_weekly_only_results(weekly_only_source)
    today = pd.Timestamp.today().normalize()

    mixed = base.loc[base["mode"] == "monthly_plus_weekly_optimal"].copy()
    monthly_only = base.loc[base["mode"] == "monthly_only"].copy()

    base_lookup = mixed[
        ["code", "name", "monthly_window", "optimal_weekly_window", "ratio_optimal_weekly_to_month_equiv", "ratio_bucket"]
    ].copy()
    base_lookup = base_lookup.rename(
        columns={
            "optimal_weekly_window": "weekly_window",
            "ratio_optimal_weekly_to_month_equiv": "ratio",
        }
    )

    leq_mask = base_lookup["ratio_bucket"] == "<=0.5"
    leq_codes = base_lookup.loc[leq_mask, "code"].tolist()
    total = len(leq_codes)
    reselection_rows: list[dict[str, object]] = []

    for idx, code in enumerate(leq_codes, start=1):
        meta_row = base_lookup.loc[base_lookup["code"] == code].iloc[0]
        stock_df = prices.loc[prices["code"] == code, ["date", "open", "close"]].copy()
        clean_df, clean_meta = _exclude_event_windows(stock_df)

        selected_monthly, monthly_meta = _select_best_window(clean_df, timeframe="monthly", windows=MONTHLY_WINDOWS, today=today)
        selected_weekly, weekly_meta = _select_best_window(clean_df, timeframe="weekly", windows=WEEKLY_WINDOWS, today=today)

        fallback_used = False
        if selected_monthly is None:
            selected_monthly = int(meta_row["monthly_window"])
            fallback_used = True
        if selected_weekly is None:
            selected_weekly = int(meta_row["weekly_window"])
            fallback_used = True

        metrics = _simulate_mixed_with_windows(
            stock_df,
            monthly_window=int(selected_monthly),
            weekly_window=int(selected_weekly),
        )
        if not metrics:
            continue

        reselection_rows.append(
            {
                "code": code,
                "name": meta_row["name"],
                "ratio_bucket": "<=0.5",
                "original_monthly_window": int(meta_row["monthly_window"]),
                "original_weekly_window": int(meta_row["weekly_window"]),
                "original_ratio": float(meta_row["ratio"]),
                "reselected_monthly_window": int(selected_monthly),
                "reselected_weekly_window": int(selected_weekly),
                "reselected_ratio": float(int(selected_weekly) / (int(selected_monthly) * 4.345)),
                "fallback_used": bool(fallback_used),
                **clean_meta,
                "monthly_selection_total_return": np.nan if monthly_meta is None else float(monthly_meta["total_return"]),
                "weekly_selection_total_return": np.nan if weekly_meta is None else float(weekly_meta["total_return"]),
                "strategy": "candidate_rule_a",
                "strategy_branch": "event_reselected_mixed",
                **metrics,
            }
        )

        if idx % 50 == 0 or idx == total:
            print(f"[reselection] {idx}/{total} codes processed")

    reselection_df = pd.DataFrame(reselection_rows)
    reselection_df.to_csv(out_dir / "leq05_event_reselected_stock_results.csv", index=False, encoding="utf-8-sig")

    monthly_only_fmt = monthly_only.copy()
    monthly_only_fmt["strategy"] = "monthly_only_baseline"
    monthly_only_fmt["strategy_branch"] = "monthly_only"
    monthly_only_fmt["weekly_window"] = monthly_only_fmt["optimal_weekly_window"]
    monthly_only_fmt["ratio"] = monthly_only_fmt["ratio_optimal_weekly_to_month_equiv"]

    mixed_fmt = mixed.copy()
    mixed_fmt["strategy"] = "mixed_baseline"
    mixed_fmt["strategy_branch"] = "mixed"
    mixed_fmt["weekly_window"] = mixed_fmt["optimal_weekly_window"]
    mixed_fmt["ratio"] = mixed_fmt["ratio_optimal_weekly_to_month_equiv"]

    weekly_fmt = weekly_only.copy()
    weekly_fmt["strategy"] = "weekly_only_baseline"
    weekly_fmt["strategy_branch"] = "weekly_only"

    candidate_parts: list[pd.DataFrame] = []
    candidate_parts.append(reselection_df.copy())
    candidate_parts.append(
        mixed_fmt.loc[mixed_fmt["ratio_bucket"] == "0.5~1.0", [
            "code","name","ratio_bucket","monthly_window","weekly_window","ratio","test_start","test_end","bars","total_return","buy_hold_return","excess_return","annualized_return","max_drawdown","trade_count","completed_trade_count","win_rate","exposure_ratio"
        ]].assign(strategy="candidate_rule_a", strategy_branch="mixed")
    )
    candidate_parts.append(
        monthly_only_fmt.loc[monthly_only_fmt["ratio_bucket"] == "1.0~1.5", [
            "code","name","ratio_bucket","monthly_window","weekly_window","ratio","test_start","test_end","bars","total_return","buy_hold_return","excess_return","annualized_return","max_drawdown","trade_count","completed_trade_count","win_rate","exposure_ratio"
        ]].assign(strategy="candidate_rule_a", strategy_branch="monthly_only")
    )
    candidate_parts.append(
        weekly_fmt.loc[weekly_fmt["ratio_bucket"] == ">1.5", [
            "code","name","ratio_bucket","monthly_window","weekly_window","ratio","test_start","test_end","bars","total_return","buy_hold_return","excess_return","annualized_return","max_drawdown","trade_count","completed_trade_count","win_rate","exposure_ratio"
        ]].assign(strategy="candidate_rule_a", strategy_branch="weekly_only")
    )
    candidate = pd.concat(candidate_parts, ignore_index=True)
    candidate["bucket_sort"] = candidate["ratio_bucket"].map(_bucket_order)
    candidate = candidate.sort_values(["bucket_sort", "code"]).drop(columns=["bucket_sort"]).reset_index(drop=True)
    candidate.to_csv(out_dir / "candidate_rule_a_stock_results.csv", index=False, encoding="utf-8-sig")

    baseline_monthly = monthly_only_fmt[[
        "code","name","ratio_bucket","monthly_window","weekly_window","ratio","test_start","test_end","bars","total_return","buy_hold_return","excess_return","annualized_return","max_drawdown","trade_count","completed_trade_count","win_rate","exposure_ratio","strategy","strategy_branch"
    ]].copy()
    baseline_mixed = mixed_fmt[[
        "code","name","ratio_bucket","monthly_window","weekly_window","ratio","test_start","test_end","bars","total_return","buy_hold_return","excess_return","annualized_return","max_drawdown","trade_count","completed_trade_count","win_rate","exposure_ratio","strategy","strategy_branch"
    ]].copy()
    baseline_weekly = weekly_fmt[[
        "code","name","ratio_bucket","monthly_window","weekly_window","ratio","test_start","test_end","bars","total_return","buy_hold_return","excess_return","annualized_return","max_drawdown","trade_count","completed_trade_count","win_rate","exposure_ratio","strategy","strategy_branch"
    ]].copy()

    combined = pd.concat([candidate, baseline_monthly, baseline_mixed, baseline_weekly], ignore_index=True)
    combined.to_csv(out_dir / "all_strategy_stock_results.csv", index=False, encoding="utf-8-sig")

    overall_summary = _candidate_summary(combined, ["strategy"]).sort_values("avg_total_return", ascending=False)
    overall_summary.to_csv(out_dir / "overall_strategy_summary.csv", index=False, encoding="utf-8-sig")

    candidate_bucket_summary = _candidate_summary(candidate, ["ratio_bucket"])
    candidate_bucket_summary.to_csv(out_dir / "candidate_rule_a_bucket_summary.csv", index=False, encoding="utf-8-sig")

    reselection_meta = pd.DataFrame(
        [
            {
                "stock_count": int(len(reselection_df)),
                "avg_excluded_days": float(reselection_df["excluded_days"].mean()) if not reselection_df.empty else np.nan,
                "median_excluded_days": float(reselection_df["excluded_days"].median()) if not reselection_df.empty else np.nan,
                "avg_excluded_weeks": float(reselection_df["excluded_weeks"].mean()) if not reselection_df.empty else np.nan,
                "avg_excluded_months": float(reselection_df["excluded_months"].mean()) if not reselection_df.empty else np.nan,
                "avg_original_ratio": float(reselection_df["original_ratio"].mean()) if not reselection_df.empty else np.nan,
                "avg_reselected_ratio": float(reselection_df["reselected_ratio"].mean()) if not reselection_df.empty else np.nan,
                "improved_to_gt_0_5_share": float((reselection_df["reselected_ratio"] > 0.5).mean()) if not reselection_df.empty else np.nan,
                "fallback_share": float(reselection_df["fallback_used"].mean()) if not reselection_df.empty else np.nan,
            }
        ]
    )
    reselection_meta.to_csv(out_dir / "leq05_reselection_summary.csv", index=False, encoding="utf-8-sig")

    _write_report(
        out_dir / "summary_report.md",
        overall_summary=overall_summary,
        bucket_summary=candidate_bucket_summary,
        reselection_meta=reselection_meta,
    )

    run_meta = {
        "price_source": str(price_source),
        "monthly_mixed_source": str(monthly_mixed_source),
        "weekly_only_source": str(weekly_only_source),
        "buy_threshold": BUY_THRESHOLD,
        "sell_threshold": SELL_THRESHOLD,
        "monthly_window_range": [MONTHLY_WINDOWS[0], MONTHLY_WINDOWS[-1]],
        "weekly_window_range": [WEEKLY_WINDOWS[0], WEEKLY_WINDOWS[-1]],
        "min_bars": MIN_BARS,
        "candidate_rule": {
            "<=0.5": "event_reselected_mixed",
            "0.5~1.0": "mixed",
            "1.0~1.5": "monthly_only",
            ">1.5": "weekly_only",
        },
        "event_exclusion_rule": {
            "abs_daily_return_ge": 0.15,
            "abs_gap_open_prev_close_ge": 0.10,
            "abs_weekly_return_ge": 0.30,
            "abs_monthly_return_ge": 0.50,
        },
        "candidate_stock_count": int(candidate["code"].nunique()),
        "reselected_stock_count": int(reselection_df["code"].nunique()),
    }
    (out_dir / "run_meta.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] outputs written to {out_dir}")


if __name__ == "__main__":
    main()
