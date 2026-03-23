from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from new_strategy.paths import data_path, output_path


def _load_daily_prices(source: Path) -> pd.DataFrame:
    df = pd.read_pickle(source)[["date", "code", "name", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["date", "code", "close"]).sort_values(["code", "date"]).reset_index(drop=True)


def _select_best_monthly_windows(path: Path, *, min_window: int = 2) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    work = df[
        (df["action_mode"] == "native_timeframe_close")
        & (df["ma_timeframe"] == "monthly")
        & (pd.to_numeric(df["ma_window"], errors="coerce") >= min_window)
    ].copy()
    if work.empty:
        return work

    work["ma_window"] = pd.to_numeric(work["ma_window"], errors="coerce").astype(int)
    ranked = work.sort_values(
        [
            "code",
            "total_return",
            "max_drawdown",
            "completed_trade_count",
            "annualized_return",
            "win_rate",
            "ma_window",
        ],
        ascending=[True, False, False, False, False, False, True],
    )
    return ranked.groupby("code", as_index=False).head(1).reset_index(drop=True)


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=float)
    if len(values) < window:
        return out
    csum = np.concatenate(([0.0], np.cumsum(values, dtype=float)))
    out[window - 1 :] = (csum[window:] - csum[:-window]) / float(window)
    return out


def _build_monthly_frame(frame: pd.DataFrame) -> pd.DataFrame:
    temp = frame[["date", "close"]].copy()
    temp["month_period"] = temp["date"].dt.to_period("M")
    out = (
        temp.groupby("month_period", as_index=False)
        .agg(decision_date=("date", "max"), close=("close", "last"))
        .sort_values("decision_date")
        .reset_index(drop=True)
    )
    out["month_ord"] = out["month_period"].dt.year * 12 + out["month_period"].dt.month
    return out


def _build_weekly_frame(frame: pd.DataFrame) -> pd.DataFrame:
    temp = frame[["date", "close"]].copy()
    temp["week_period"] = temp["date"].dt.to_period("W-FRI")
    out = (
        temp.groupby("week_period", as_index=False)
        .agg(decision_date=("date", "max"), close=("close", "last"))
        .sort_values("decision_date")
        .reset_index(drop=True)
    )
    out["month_period"] = out["decision_date"].dt.to_period("M")
    out["month_ord"] = out["month_period"].dt.year * 12 + out["month_period"].dt.month
    return out


def _completed_month_states(monthly_df: pd.DataFrame, window: int) -> pd.DataFrame:
    out = monthly_df.copy()
    prices = out["close"].to_numpy(dtype=float)
    ma = _rolling_mean(prices, window)
    out["monthly_ma"] = ma
    out["state"] = np.where(np.isfinite(ma), prices > ma, np.nan)
    return out


def _month_end_events(monthly_state_df: pd.DataFrame) -> pd.DataFrame:
    valid = monthly_state_df.dropna(subset=["state"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=["decision_date", "new_state", "source"])
    valid["prev_state"] = valid["state"].shift(1)
    valid = valid.dropna(subset=["prev_state"]).copy()
    valid["state"] = valid["state"].astype(bool)
    valid["prev_state"] = valid["prev_state"].astype(bool)
    events = valid.loc[valid["state"] != valid["prev_state"], ["decision_date", "state"]].copy()
    if events.empty:
        return pd.DataFrame(columns=["decision_date", "new_state", "source"])
    events = events.rename(columns={"state": "new_state"})
    events["source"] = "month_end"
    return events.reset_index(drop=True)


def _weekly_early_events(monthly_state_df: pd.DataFrame, weekly_df: pd.DataFrame, window: int) -> pd.DataFrame:
    monthly_valid = monthly_state_df.dropna(subset=["state"]).copy()
    if monthly_valid.empty or weekly_df.empty:
        return pd.DataFrame(columns=["decision_date", "new_state", "source"])

    completed_ord = monthly_state_df["month_ord"].to_numpy(dtype=int)
    completed_close = monthly_state_df["close"].to_numpy(dtype=float)
    monthly_state_map = {
        int(row.month_ord): bool(row.state)
        for row in monthly_valid.itertuples(index=False)
    }

    week_rows: list[dict[str, object]] = []
    for row in weekly_df.itertuples(index=False):
        month_ord = int(row.month_ord)
        prior_count = int(np.searchsorted(completed_ord, month_ord, side="left"))
        if prior_count < window - 1:
            continue
        prior_slice = completed_close[prior_count - (window - 1) : prior_count]
        if len(prior_slice) != window - 1 or not np.all(np.isfinite(prior_slice)):
            continue
        provisional_ma = (float(np.sum(prior_slice)) + float(row.close)) / float(window)
        current_state = bool(float(row.close) > provisional_ma)
        week_rows.append(
            {
                "decision_date": pd.Timestamp(row.decision_date),
                "month_ord": month_ord,
                "state": current_state,
                "provisional_ma": provisional_ma,
            }
        )

    if not week_rows:
        return pd.DataFrame(columns=["decision_date", "new_state", "source"])

    weekly_state_df = pd.DataFrame(week_rows).sort_values("decision_date").reset_index(drop=True)

    events: list[dict[str, object]] = []
    executed_state: bool | None = None
    emitted_months: set[int] = set()
    for row in weekly_state_df.itertuples(index=False):
        month_ord = int(row.month_ord)
        current_state = bool(row.state)

        if executed_state is None:
            prev_month_state = monthly_state_map.get(month_ord - 1)
            if prev_month_state is None:
                continue
            executed_state = bool(prev_month_state)

        if current_state == executed_state:
            continue

        if month_ord in emitted_months:
            continue

        events.append(
            {
                "decision_date": pd.Timestamp(row.decision_date),
                "new_state": current_state,
                "source": "weekly_early",
            }
        )
        emitted_months.add(month_ord)
        executed_state = current_state

    return pd.DataFrame(events)


def _simulate_daily_from_events(
    daily_df: pd.DataFrame,
    events: pd.DataFrame,
    *,
    common_start: pd.Timestamp,
) -> dict[str, object]:
    work = daily_df.loc[daily_df["date"] >= common_start, ["date", "close"]].copy().reset_index(drop=True)
    if len(work) < 2:
        return {}

    event_state_map = {
        pd.Timestamp(row.decision_date).normalize(): bool(row.new_state)
        for row in events.itertuples(index=False)
    }

    dates = work["date"].to_numpy()
    prices = work["close"].to_numpy(dtype=float)
    position = np.zeros(len(work), dtype=float)
    current_state = 0.0

    for idx in range(1, len(work)):
        prev_date = pd.Timestamp(dates[idx - 1]).normalize()
        if prev_date in event_state_map:
            current_state = 1.0 if event_state_map[prev_date] else 0.0
        position[idx] = current_state

    bar_ret = np.zeros(len(work), dtype=float)
    bar_ret[1:] = position[1:] * (prices[1:] / prices[:-1] - 1.0)
    equity = np.cumprod(1.0 + bar_ret)
    running_peak = np.maximum.accumulate(equity)
    drawdown = equity / running_peak - 1.0

    entries = np.flatnonzero((position[1:] == 1.0) & (position[:-1] == 0.0)) + 1
    exits = np.flatnonzero((position[1:] == 0.0) & (position[:-1] == 1.0)) + 1

    completed = 0
    wins = 0
    for entry_idx in entries:
        later_exits = exits[exits > entry_idx]
        if later_exits.size == 0:
            continue
        exit_idx = int(later_exits[0])
        trade_ret = prices[exit_idx] / prices[entry_idx] - 1.0
        completed += 1
        if trade_ret > 0:
            wins += 1

    intervals = max(len(work) - 1, 1)
    total_return = float(equity[-1] - 1.0)
    annualized_return = float(equity[-1] ** (252 / intervals) - 1.0) if equity[-1] > 0 else -1.0
    buy_hold_return = float(prices[-1] / prices[0] - 1.0)
    max_drawdown = float(np.min(drawdown))
    exposure_ratio = float(np.mean(position[1:])) if len(position) > 1 else 0.0

    return {
        "test_start": pd.Timestamp(dates[0]).date().isoformat(),
        "test_end": pd.Timestamp(dates[-1]).date().isoformat(),
        "bars": int(len(work)),
        "total_return": total_return,
        "buy_hold_return": buy_hold_return,
        "excess_return": total_return - buy_hold_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
        "trade_count": int(len(entries)),
        "completed_trade_count": int(completed),
        "win_rate": float(wins / completed) if completed else np.nan,
        "exposure_ratio": exposure_ratio,
        "signal_count": int(len(events)),
    }


def evaluate_stock(frame: pd.DataFrame, *, monthly_window: int) -> dict[str, object]:
    daily_df = frame[["date", "close"]].copy().sort_values("date").reset_index(drop=True)
    monthly_df = _build_monthly_frame(daily_df)
    weekly_df = _build_weekly_frame(daily_df)
    monthly_state_df = _completed_month_states(monthly_df, monthly_window)

    month_end_events = _month_end_events(monthly_state_df)
    weekly_early_events = _weekly_early_events(monthly_state_df, weekly_df, monthly_window)

    weekly_valid = weekly_early_events["decision_date"].min() if not weekly_early_events.empty else pd.NaT
    monthly_valid = month_end_events["decision_date"].min() if not month_end_events.empty else pd.NaT
    candidates = [dt for dt in [weekly_valid, monthly_valid] if pd.notna(dt)]
    if not candidates:
        return {}
    common_start = min(candidates)

    month_metrics = _simulate_daily_from_events(daily_df, month_end_events, common_start=common_start)
    weekly_metrics = _simulate_daily_from_events(daily_df, weekly_early_events, common_start=common_start)
    if not month_metrics or not weekly_metrics:
        return {}

    out = {
        "common_start": pd.Timestamp(common_start).date().isoformat(),
        "monthly_window": int(monthly_window),
        "month_end_signal_count": int(len(month_end_events)),
        "weekly_early_signal_count": int(len(weekly_early_events)),
    }
    for prefix, metrics in [("month_end", month_metrics), ("weekly_early", weekly_metrics)]:
        for key, value in metrics.items():
            out[f"{prefix}_{key}"] = value

    out["delta_total_return"] = out["weekly_early_total_return"] - out["month_end_total_return"]
    out["delta_annualized_return"] = out["weekly_early_annualized_return"] - out["month_end_annualized_return"]
    out["delta_max_drawdown"] = out["weekly_early_max_drawdown"] - out["month_end_max_drawdown"]
    out["delta_trade_count"] = out["weekly_early_trade_count"] - out["month_end_trade_count"]
    out["delta_win_rate"] = (
        out["weekly_early_win_rate"] - out["month_end_win_rate"]
        if pd.notna(out["weekly_early_win_rate"]) and pd.notna(out["month_end_win_rate"])
        else np.nan
    )
    out["better_mode_total_return"] = (
        "weekly_early"
        if out["weekly_early_total_return"] > out["month_end_total_return"]
        else "month_end"
        if out["weekly_early_total_return"] < out["month_end_total_return"]
        else "tie"
    )
    out["better_mode_mdd"] = (
        "weekly_early"
        if out["weekly_early_max_drawdown"] > out["month_end_max_drawdown"]
        else "month_end"
        if out["weekly_early_max_drawdown"] < out["month_end_max_drawdown"]
        else "tie"
    )
    return out


def _mode_summary(comparison_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mode in ["month_end", "weekly_early"]:
        rows.append(
            {
                "mode": mode,
                "stock_count": int(len(comparison_df)),
                "avg_total_return": float(comparison_df[f"{mode}_total_return"].mean()),
                "median_total_return": float(comparison_df[f"{mode}_total_return"].median()),
                "avg_annualized_return": float(comparison_df[f"{mode}_annualized_return"].mean()),
                "median_annualized_return": float(comparison_df[f"{mode}_annualized_return"].median()),
                "avg_max_drawdown": float(comparison_df[f"{mode}_max_drawdown"].mean()),
                "median_max_drawdown": float(comparison_df[f"{mode}_max_drawdown"].median()),
                "avg_trade_count": float(comparison_df[f"{mode}_trade_count"].mean()),
                "avg_win_rate": float(comparison_df[f"{mode}_win_rate"].dropna().mean()),
                "avg_exposure_ratio": float(comparison_df[f"{mode}_exposure_ratio"].mean()),
            }
        )
    return pd.DataFrame(rows)


def _overall_summary(comparison_df: pd.DataFrame) -> pd.DataFrame:
    total = len(comparison_df)
    rows = [
        {
            "metric": "weekly_early_better_total_return_count",
            "value": int((comparison_df["better_mode_total_return"] == "weekly_early").sum()),
        },
        {
            "metric": "month_end_better_total_return_count",
            "value": int((comparison_df["better_mode_total_return"] == "month_end").sum()),
        },
        {
            "metric": "tie_total_return_count",
            "value": int((comparison_df["better_mode_total_return"] == "tie").sum()),
        },
        {
            "metric": "weekly_early_better_total_return_share",
            "value": float((comparison_df["better_mode_total_return"] == "weekly_early").mean()) if total else np.nan,
        },
        {
            "metric": "avg_delta_total_return",
            "value": float(comparison_df["delta_total_return"].mean()),
        },
        {
            "metric": "median_delta_total_return",
            "value": float(comparison_df["delta_total_return"].median()),
        },
        {
            "metric": "avg_delta_annualized_return",
            "value": float(comparison_df["delta_annualized_return"].mean()),
        },
        {
            "metric": "avg_delta_max_drawdown",
            "value": float(comparison_df["delta_max_drawdown"].mean()),
        },
        {
            "metric": "avg_delta_trade_count",
            "value": float(comparison_df["delta_trade_count"].mean()),
        },
    ]
    return pd.DataFrame(rows)


def _write_markdown(out_dir: Path, meta: dict[str, object], comparison_df: pd.DataFrame) -> None:
    lines: list[str] = []
    lines.append("# V2 Monthly MA Timing Comparison")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- price source: `{meta['price_source']}`")
    lines.append(f"- monthly selection source: `{meta['selection_source']}`")
    lines.append("- monthly window selection: best monthly MA per stock from native_timeframe_close")
    lines.append("- compare mode A: execute only at month-end close signal changes")
    lines.append("- compare mode B: observe the same monthly MA every week-end and execute early when the provisional monthly state changes")
    lines.append("- compare mode B constraint: once a buy or sell is executed in a month, no additional execution is allowed in that same month")
    lines.append("- execution assumption: signal is decided at close and applies from the next daily bar")
    lines.append("")
    lines.append("## Coverage")
    lines.append(f"- selected monthly-window stocks: `{meta['selected_stock_count']:,}`")
    lines.append(f"- simulated stocks: `{meta['simulated_stock_count']:,}`")
    lines.append("")

    if not comparison_df.empty:
        weekly_better = int((comparison_df["better_mode_total_return"] == "weekly_early").sum())
        month_better = int((comparison_df["better_mode_total_return"] == "month_end").sum())
        tie_count = int((comparison_df["better_mode_total_return"] == "tie").sum())
        lines.append("## Comparison Summary")
        lines.append(f"- weekly_early better by total_return: `{weekly_better}` stocks")
        lines.append(f"- month_end better by total_return: `{month_better}` stocks")
        lines.append(f"- ties: `{tie_count}` stocks")
        lines.append(f"- average delta total_return (weekly_early - month_end): `{comparison_df['delta_total_return'].mean():.4f}`")
        lines.append(f"- median delta total_return (weekly_early - month_end): `{comparison_df['delta_total_return'].median():.4f}`")
        lines.append(f"- average delta max_drawdown (weekly_early - month_end): `{comparison_df['delta_max_drawdown'].mean():.4f}`")
        lines.append("")

        lines.append("## Top Weekly-Early Improvements")
        top_gain = comparison_df.sort_values("delta_total_return", ascending=False).head(15)
        lines.append("| rank | code | name | window | month_end_total_return | weekly_early_total_return | delta_total_return | month_end_mdd | weekly_early_mdd |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for idx, (_, row) in enumerate(top_gain.iterrows(), start=1):
            lines.append(
                f"| {idx} | {row['code']} | {row['name']} | {int(row['monthly_window'])} | "
                f"{row['month_end_total_return']:.4f} | {row['weekly_early_total_return']:.4f} | "
                f"{row['delta_total_return']:.4f} | {row['month_end_max_drawdown']:.4f} | {row['weekly_early_max_drawdown']:.4f} |"
            )
        lines.append("")

        lines.append("## Top Month-End Advantages")
        top_loss = comparison_df.sort_values("delta_total_return", ascending=True).head(15)
        lines.append("| rank | code | name | window | month_end_total_return | weekly_early_total_return | delta_total_return | month_end_mdd | weekly_early_mdd |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for idx, (_, row) in enumerate(top_loss.iterrows(), start=1):
            lines.append(
                f"| {idx} | {row['code']} | {row['name']} | {int(row['monthly_window'])} | "
                f"{row['month_end_total_return']:.4f} | {row['weekly_early_total_return']:.4f} | "
                f"{row['delta_total_return']:.4f} | {row['month_end_max_drawdown']:.4f} | {row['weekly_early_max_drawdown']:.4f} |"
            )

    (out_dir / "summary_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare month-end execution vs weekly-early execution on the same optimal monthly MA.")
    parser.add_argument("--price-source", type=Path, default=data_path("feature_daily.pkl"))
    parser.add_argument(
        "--monthly-selection-source",
        type=Path,
        default=output_path("ma_breakout_research", "native_timeframe_close_returns_by_stock.csv"),
    )
    parser.add_argument("--out-dir", type=Path, default=output_path("v2_ma_timing_research"))
    parser.add_argument("--min-window", type=int, default=2)
    parser.add_argument("--limit-codes", type=int, default=0)
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = _select_best_monthly_windows(args.monthly_selection_source, min_window=args.min_window)
    if args.limit_codes > 0:
        selected = selected.head(args.limit_codes).copy()
    selected_codes = set(selected["code"])

    prices = _load_daily_prices(args.price_source)
    prices = prices[prices["code"].isin(selected_codes)].copy()

    result_rows: list[dict[str, object]] = []
    grouped = prices.groupby("code", sort=False)
    total_codes = grouped.ngroups
    for idx, (code, grp) in enumerate(grouped, start=1):
        sel = selected.loc[selected["code"] == code]
        if sel.empty:
            continue
        name = str(grp["name"].dropna().iloc[-1]) if grp["name"].notna().any() else str(sel["name"].iloc[0])
        monthly_window = int(sel["ma_window"].iloc[0])
        metrics = evaluate_stock(grp[["date", "close"]], monthly_window=monthly_window)
        if metrics:
            result_rows.append(
                {
                    "code": code,
                    "name": name,
                    **metrics,
                }
            )
        if idx % 100 == 0 or idx == total_codes:
            print(f"[progress] {idx}/{total_codes} codes processed")

    comparison_df = pd.DataFrame(result_rows).sort_values(["delta_total_return", "code"], ascending=[False, True]).reset_index(drop=True)
    mode_summary_df = _mode_summary(comparison_df) if not comparison_df.empty else pd.DataFrame()
    overall_summary_df = _overall_summary(comparison_df) if not comparison_df.empty else pd.DataFrame()

    comparison_df.to_csv(out_dir / "stock_monthly_execution_comparison.csv", index=False, encoding="utf-8-sig")
    mode_summary_df.to_csv(out_dir / "mode_summary.csv", index=False, encoding="utf-8-sig")
    overall_summary_df.to_csv(out_dir / "overall_summary.csv", index=False, encoding="utf-8-sig")
    if not comparison_df.empty:
        comparison_df.sort_values("delta_total_return", ascending=False).head(100).to_csv(
            out_dir / "top_weekly_early_improvements.csv", index=False, encoding="utf-8-sig"
        )
        comparison_df.sort_values("delta_total_return", ascending=True).head(100).to_csv(
            out_dir / "top_month_end_advantages.csv", index=False, encoding="utf-8-sig"
        )

    meta = {
        "price_source": str(args.price_source),
        "selection_source": str(args.monthly_selection_source),
        "selected_stock_count": int(selected["code"].nunique()),
        "simulated_stock_count": int(comparison_df["code"].nunique()) if not comparison_df.empty else 0,
        "min_window": int(args.min_window),
        "limit_codes": int(args.limit_codes),
        "weekly_early_monthly_cap": True,
    }
    (out_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(out_dir, meta=meta, comparison_df=comparison_df)
    print(f"[done] outputs written to {out_dir}")


if __name__ == "__main__":
    main()
