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
MONTHLY_CAP = 36


def _load_price_frame(source: Path) -> pd.DataFrame:
    df = pd.read_pickle(source)[["date", "code", "name", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return (
        df.dropna(subset=["date", "code", "close"])
        .sort_values(["code", "date"])
        .reset_index(drop=True)
    )


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


def _simulate_mixed(frame: pd.DataFrame, monthly_window: int, weekly_window: int) -> dict[str, object]:
    monthly_df = _build_monthly_frame(frame)
    weekly_df = _build_weekly_frame(frame)
    monthly_ma = _rolling_mean(monthly_df["close"].to_numpy(dtype=float), monthly_window)
    valid_monthly_dates = monthly_df.loc[np.isfinite(monthly_ma), "decision_date"]
    if valid_monthly_dates.empty:
        return {}
    start_date = pd.Timestamp(valid_monthly_dates.iloc[0])
    buy_events = _build_buy_events(monthly_df, monthly_window, BUY_THRESHOLD)
    sell_events = _build_sell_events(weekly_df, weekly_window, SELL_THRESHOLD)
    return _simulate_daily_from_events(frame, buy_events, sell_events, start_date=start_date)


def _simulate_monthly_only(frame: pd.DataFrame, monthly_window: int) -> dict[str, object]:
    monthly_df = _build_monthly_frame(frame)
    monthly_ma = _rolling_mean(monthly_df["close"].to_numpy(dtype=float), monthly_window)
    valid_monthly_dates = monthly_df.loc[np.isfinite(monthly_ma), "decision_date"]
    if valid_monthly_dates.empty:
        return {}
    start_date = pd.Timestamp(valid_monthly_dates.iloc[0])
    buy_events = _build_buy_events(monthly_df, monthly_window, BUY_THRESHOLD)
    # Rebuild sell events on monthly frame using the same crossing logic as sell-state.
    out = monthly_df.copy()
    prices = out["close"].to_numpy(dtype=float)
    ma = _rolling_mean(prices, monthly_window)
    out["monthly_ma"] = ma
    out["sell_level"] = ma * (1.0 + SELL_THRESHOLD)
    out["sell_state"] = np.where(np.isfinite(ma), prices <= out["sell_level"].to_numpy(dtype=float), np.nan)
    valid = out.dropna(subset=["sell_state"]).copy()
    if valid.empty:
        sell_events = pd.DataFrame(columns=["decision_date", "event_type"])
    else:
        valid["prev_state"] = valid["sell_state"].shift(1)
        valid = valid.dropna(subset=["prev_state"]).copy()
        valid["sell_state"] = valid["sell_state"].astype(bool)
        valid["prev_state"] = valid["prev_state"].astype(bool)
        sell_events = valid.loc[(~valid["prev_state"]) & (valid["sell_state"]), ["decision_date"]].copy()
        sell_events["event_type"] = "sell"
        sell_events = sell_events.reset_index(drop=True)
    return _simulate_daily_from_events(frame, buy_events, sell_events, start_date=start_date)


def _write_report(out_path: Path, details: pd.DataFrame, summary: pd.DataFrame) -> None:
    lines: list[str] = []
    lines.append("# <=0.5 Worst-30 Long Monthly Window Analysis")
    lines.append("")
    lines.append(f"- target subset: worst 30 stocks in `<=0.5` bucket with `monthly_window >= {MONTHLY_CAP + 14}`")
    lines.append(f"- tested monthly cap: `{MONTHLY_CAP}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("| mode | stock_count | avg_total_return | median_total_return | avg_excess_return | avg_max_drawdown | avg_trade_count | avg_win_rate |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in summary.itertuples(index=False):
        lines.append(
            f"| {row.mode} | {int(row.stock_count)} | {row.avg_total_return:.4f} | {row.median_total_return:.4f} | "
            f"{row.avg_excess_return:.4f} | {row.avg_max_drawdown:.4f} | {row.avg_trade_count:.2f} | {row.avg_win_rate:.4f} |"
        )
    lines.append("")
    lines.append("## Sample")
    sample = details.head(10)
    lines.append("| code | name | original_monthly | original_weekly | capped_monthly | reselected_weekly | original_total_return | capped_mixed_total_return | capped_monthly_only_total_return |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in sample.itertuples(index=False):
        lines.append(
            f"| {row.code} | {row.name} | {int(row.original_monthly_window)} | {int(row.original_weekly_window)} | "
            f"{int(row.capped_monthly_window)} | {int(row.reselected_weekly_window)} | {row.original_total_return:.4f} | "
            f"{row.capped_mixed_total_return:.4f} | {row.capped_monthly_only_total_return:.4f} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    output_base = output_path()
    price_source = data_path("feature_daily.pkl")
    mixed_source = output_base / "v2_monthly_only_vs_optimal_vs_conditional" / "stock_results.csv"
    out_dir = output_base / "v2_leq05_long_monthly_window_analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    mixed = pd.read_csv(mixed_source, dtype={"code": str}, low_memory=False)
    mixed = mixed[(mixed["mode"] == "monthly_plus_weekly_optimal") & (mixed["ratio_bucket"] == "<=0.5")].copy()
    worst30 = mixed.sort_values(["excess_return", "total_return", "max_drawdown"], ascending=[True, True, True]).head(30).copy()
    target = worst30[worst30["monthly_window"] >= 50].copy()

    prices = _load_price_frame(price_source)
    today = pd.Timestamp.today().normalize()

    rows: list[dict[str, object]] = []
    for idx, row in enumerate(target.itertuples(index=False), start=1):
        code = str(row.code).zfill(6)
        stock_df = prices.loc[prices["code"] == code, ["date", "close"]].copy().sort_values("date").reset_index(drop=True)
        capped_monthly_window = min(int(row.monthly_window), MONTHLY_CAP)
        allowed_weekly = [
            w for w in WEEKLY_WINDOWS
            if 0.5 <= (w / (capped_monthly_window * 4.345)) <= 1.5
        ]
        if not allowed_weekly:
            allowed_weekly = WEEKLY_WINDOWS
        reselected_weekly_window, _ = _select_best_window(stock_df, timeframe="weekly", windows=allowed_weekly, today=today)
        if reselected_weekly_window is None:
            reselected_weekly_window = int(row.optimal_weekly_window)

        capped_mixed = _simulate_mixed(stock_df, capped_monthly_window, int(reselected_weekly_window))
        capped_monthly_only = _simulate_monthly_only(stock_df, capped_monthly_window)

        rows.append(
            {
                "code": code,
                "name": row.name,
                "original_monthly_window": int(row.monthly_window),
                "original_weekly_window": int(row.optimal_weekly_window),
                "original_ratio": float(row.ratio_optimal_weekly_to_month_equiv),
                "original_total_return": float(row.total_return),
                "original_excess_return": float(row.excess_return),
                "original_max_drawdown": float(row.max_drawdown),
                "capped_monthly_window": int(capped_monthly_window),
                "reselected_weekly_window": int(reselected_weekly_window),
                "reselected_ratio": float(int(reselected_weekly_window) / (int(capped_monthly_window) * 4.345)),
                "capped_mixed_total_return": float(capped_mixed.get("total_return", np.nan)),
                "capped_mixed_excess_return": float(capped_mixed.get("excess_return", np.nan)),
                "capped_mixed_max_drawdown": float(capped_mixed.get("max_drawdown", np.nan)),
                "capped_mixed_trade_count": float(capped_mixed.get("trade_count", np.nan)),
                "capped_mixed_win_rate": float(capped_mixed.get("win_rate", np.nan)),
                "capped_monthly_only_total_return": float(capped_monthly_only.get("total_return", np.nan)),
                "capped_monthly_only_excess_return": float(capped_monthly_only.get("excess_return", np.nan)),
                "capped_monthly_only_max_drawdown": float(capped_monthly_only.get("max_drawdown", np.nan)),
                "capped_monthly_only_trade_count": float(capped_monthly_only.get("trade_count", np.nan)),
                "capped_monthly_only_win_rate": float(capped_monthly_only.get("win_rate", np.nan)),
            }
        )
        print(f"[progress] {idx}/{len(target)}")
    details = pd.DataFrame(rows)
    details.to_csv(out_dir / "long_monthly_window_stock_results.csv", index=False, encoding="utf-8-sig")

    summary_rows = [
        {
            "mode": "original_mixed",
            "stock_count": int(len(details)),
            "avg_total_return": float(details["original_total_return"].mean()),
            "median_total_return": float(details["original_total_return"].median()),
            "avg_excess_return": float(details["original_excess_return"].mean()),
            "avg_max_drawdown": float(details["original_max_drawdown"].mean()),
            "avg_trade_count": float(target["trade_count"].mean()),
            "avg_win_rate": float(target["win_rate"].mean()),
        },
        {
            "mode": "monthly_cap_plus_weekly_reselected",
            "stock_count": int(len(details)),
            "avg_total_return": float(details["capped_mixed_total_return"].mean()),
            "median_total_return": float(details["capped_mixed_total_return"].median()),
            "avg_excess_return": float(details["capped_mixed_excess_return"].mean()),
            "avg_max_drawdown": float(details["capped_mixed_max_drawdown"].mean()),
            "avg_trade_count": float(details["capped_mixed_trade_count"].mean()),
            "avg_win_rate": float(details["capped_mixed_win_rate"].mean()),
        },
        {
            "mode": "monthly_cap_only",
            "stock_count": int(len(details)),
            "avg_total_return": float(details["capped_monthly_only_total_return"].mean()),
            "median_total_return": float(details["capped_monthly_only_total_return"].median()),
            "avg_excess_return": float(details["capped_monthly_only_excess_return"].mean()),
            "avg_max_drawdown": float(details["capped_monthly_only_max_drawdown"].mean()),
            "avg_trade_count": float(details["capped_monthly_only_trade_count"].mean()),
            "avg_win_rate": float(details["capped_monthly_only_win_rate"].mean()),
        },
    ]
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(out_dir / "summary.csv", index=False, encoding="utf-8-sig")
    _write_report(out_dir / "summary_report.md", details, summary)

    run_meta = {
        "monthly_cap": MONTHLY_CAP,
        "target_stock_count": int(len(details)),
        "selection_rule": "worst 30 of <=0.5 by excess_return asc, filtered to original monthly_window >= 50",
        "weekly_reselection_rule": "choose best weekly window within ratio band 0.5~1.5 using capped monthly window",
    }
    (out_dir / "run_meta.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] outputs written to {out_dir}")


if __name__ == "__main__":
    main()
