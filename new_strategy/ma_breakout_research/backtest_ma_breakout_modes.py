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


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=float)
    if len(values) < window:
        return out
    csum = np.concatenate(([0.0], np.cumsum(values, dtype=float)))
    out[window - 1 :] = (csum[window:] - csum[:-window]) / float(window)
    return out


def _period_end_dates_from_periods(periods: pd.Series) -> pd.Series:
    return periods.dt.to_timestamp(how="end").dt.normalize()


def build_completed_period_frame(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    today: pd.Timestamp,
) -> pd.DataFrame:
    if timeframe == "daily":
        out = frame[["date", "close"]].copy()
        out["decision_date"] = out["date"]
        return out[["decision_date", "close"]].reset_index(drop=True)

    period_alias = {"weekly": "W-FRI", "monthly": "M"}[timeframe]
    temp = frame[["date", "close"]].copy()
    temp["period"] = temp["date"].dt.to_period(period_alias)
    agg = (
        temp.groupby("period", as_index=False)
        .agg(decision_date=("date", "max"), close=("close", "last"))
        .sort_values("decision_date")
        .reset_index(drop=True)
    )

    if not agg.empty:
      latest_period = agg["period"].iloc[-1]
      current_period = today.to_period(period_alias)
      if latest_period == current_period:
          agg = agg.iloc[:-1].copy()

    return agg[["decision_date", "close"]].reset_index(drop=True)


def _compute_trade_returns(prices: np.ndarray, entries: np.ndarray, exits: np.ndarray) -> tuple[int, int, float]:
    completed = 0
    wins = 0
    for entry in entries:
        later_exits = exits[exits > entry]
        if later_exits.size == 0:
            continue
        exit_idx = int(later_exits[0])
        trade_ret = prices[exit_idx] / prices[entry] - 1.0
        completed += 1
        if trade_ret > 0:
            wins += 1
    win_rate = wins / completed if completed else np.nan
    return int(len(entries)), int(completed), float(win_rate) if not np.isnan(win_rate) else np.nan


def _decision_state_from_crosses(length: int, cross_up: np.ndarray, cross_down: np.ndarray) -> np.ndarray:
    state_after_close = np.zeros(length, dtype=float)
    event_idx = np.flatnonzero(cross_up | cross_down)
    if event_idx.size == 0:
        return state_after_close
    event_values = np.where(cross_up[event_idx], 1.0, 0.0)
    starts = np.r_[0, event_idx]
    values = np.r_[0.0, event_values]
    lengths = np.diff(np.r_[starts, length])
    return np.repeat(values, lengths).astype(float, copy=False)


def backtest_from_signal(
    dates: np.ndarray,
    prices: np.ndarray,
    ma: np.ndarray,
    *,
    periods_per_year: int,
) -> dict[str, object]:
    valid = np.isfinite(prices) & np.isfinite(ma)
    if not np.any(valid):
        return {}

    above_full = np.zeros(len(prices), dtype=bool)
    above_full[valid] = prices[valid] > ma[valid]
    prev_valid = np.roll(valid, 1)
    prev_valid[0] = False
    prev_above = np.roll(above_full, 1)
    prev_above[0] = False
    cross_up_full = valid & prev_valid & above_full & (~prev_above)
    cross_down_full = valid & prev_valid & (~above_full) & prev_above

    start_idx = int(np.flatnonzero(valid)[0])
    px = prices[start_idx:].astype(float, copy=False)
    dt = dates[start_idx:]
    if len(px) < 2:
        return {}

    cross_up = cross_up_full[start_idx:]
    cross_down = cross_down_full[start_idx:]
    state_after_close = _decision_state_from_crosses(len(px), cross_up, cross_down)
    position = np.zeros(len(px), dtype=float)
    position[1:] = state_after_close[:-1]

    bar_ret = np.zeros(len(px), dtype=float)
    bar_ret[1:] = position[1:] * (px[1:] / px[:-1] - 1.0)
    equity = np.cumprod(1.0 + bar_ret)
    running_peak = np.maximum.accumulate(equity)
    drawdown = equity / running_peak - 1.0

    total_return = float(equity[-1] - 1.0)
    buy_hold_return = float(px[-1] / px[0] - 1.0)
    excess_return = total_return - buy_hold_return
    intervals = max(len(px) - 1, 1)
    annualized_return = float(equity[-1] ** (periods_per_year / intervals) - 1.0) if equity[-1] > 0 else -1.0
    entry_idx = np.flatnonzero(cross_up)
    exit_idx = np.flatnonzero(cross_down)
    trade_count, completed_trade_count, win_rate = _compute_trade_returns(px, entry_idx, exit_idx)

    return {
        "test_start": pd.Timestamp(dt[0]).date().isoformat(),
        "test_end": pd.Timestamp(dt[-1]).date().isoformat(),
        "bars": int(len(px)),
        "total_return": total_return,
        "buy_hold_return": buy_hold_return,
        "excess_return": excess_return,
        "annualized_return": annualized_return,
        "max_drawdown": float(np.min(drawdown)),
        "trade_count": trade_count,
        "completed_trade_count": completed_trade_count,
        "win_rate": win_rate,
        "exposure_ratio": float(np.mean(position[1:])) if len(position) > 1 else 0.0,
    }


def evaluate_native_action(
    code: str,
    name: str,
    frame: pd.DataFrame,
    *,
    today: pd.Timestamp,
    daily_windows: Iterable[int],
    weekly_windows: Iterable[int],
    monthly_windows: Iterable[int],
    min_bars: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    config = [
        ("daily", daily_windows, 252),
        ("weekly", weekly_windows, 52),
        ("monthly", monthly_windows, 12),
    ]
    for timeframe, windows, periods_per_year in config:
        period_df = build_completed_period_frame(frame, timeframe, today=today)
        if len(period_df) < min_bars:
            continue
        dates = period_df["decision_date"].to_numpy()
        prices = period_df["close"].to_numpy(dtype=float)
        for window in windows:
            ma = _rolling_mean(prices, int(window))
            metrics = backtest_from_signal(dates, prices, ma, periods_per_year=periods_per_year)
            if not metrics:
                continue
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "ma_timeframe": timeframe,
                    "action_mode": "native_timeframe_close",
                    "ma_window": int(window),
                    **metrics,
                }
            )
    return rows


def _map_period_ma_to_daily(
    daily_dates: np.ndarray,
    period_dates: np.ndarray,
    period_ma: np.ndarray,
) -> np.ndarray:
    out = np.full(len(daily_dates), np.nan, dtype=float)
    if len(period_dates) == 0:
        return out
    idx = np.searchsorted(period_dates, daily_dates, side="right") - 1
    valid = idx >= 0
    out[valid] = period_ma[idx[valid]]
    return out


def evaluate_daily_action(
    code: str,
    name: str,
    frame: pd.DataFrame,
    *,
    today: pd.Timestamp,
    daily_windows: Iterable[int],
    weekly_windows: Iterable[int],
    monthly_windows: Iterable[int],
    min_bars: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    daily = frame[["date", "close"]].copy().sort_values("date").reset_index(drop=True)
    if len(daily) < min_bars:
        return rows

    daily_dates = daily["date"].to_numpy()
    daily_prices = daily["close"].to_numpy(dtype=float)

    for window in daily_windows:
        ma = _rolling_mean(daily_prices, int(window))
        metrics = backtest_from_signal(daily_dates, daily_prices, ma, periods_per_year=252)
        if not metrics:
            continue
        rows.append(
            {
                "code": code,
                "name": name,
                "ma_timeframe": "daily",
                "action_mode": "daily_close_action",
                "ma_window": int(window),
                **metrics,
            }
        )

    for timeframe, windows in (("weekly", weekly_windows), ("monthly", monthly_windows)):
        period_df = build_completed_period_frame(frame, timeframe, today=today)
        if len(period_df) < min_bars:
            continue
        period_dates = period_df["decision_date"].to_numpy()
        period_prices = period_df["close"].to_numpy(dtype=float)
        for window in windows:
            period_ma = _rolling_mean(period_prices, int(window))
            daily_ma = _map_period_ma_to_daily(daily_dates, period_dates, period_ma)
            metrics = backtest_from_signal(daily_dates, daily_prices, daily_ma, periods_per_year=252)
            if not metrics:
                continue
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "ma_timeframe": timeframe,
                    "action_mode": "daily_close_action",
                    "ma_window": int(window),
                    **metrics,
                }
            )

    return rows


def summarize_best(full_df: pd.DataFrame) -> pd.DataFrame:
    if full_df.empty:
        return pd.DataFrame()
    ranked = full_df.sort_values(
        ["action_mode", "ma_timeframe", "code", "total_return", "max_drawdown", "ma_window"],
        ascending=[True, True, True, False, False, True],
    )
    return ranked.groupby(["action_mode", "ma_timeframe", "code"], as_index=False).head(1).reset_index(drop=True)


def summarize_distribution(best_df: pd.DataFrame) -> pd.DataFrame:
    if best_df.empty:
        return pd.DataFrame()
    dist = (
        best_df.groupby(["action_mode", "ma_timeframe", "ma_window"], as_index=False)
        .agg(
            stock_count=("code", "nunique"),
            avg_total_return=("total_return", "mean"),
            median_total_return=("total_return", "median"),
            avg_max_drawdown=("max_drawdown", "mean"),
        )
        .sort_values(["action_mode", "ma_timeframe", "stock_count", "ma_window"], ascending=[True, True, False, True])
        .reset_index(drop=True)
    )
    totals = dist.groupby(["action_mode", "ma_timeframe"])["stock_count"].transform("sum")
    dist["stock_share"] = dist["stock_count"] / totals
    return dist


def build_markdown_report(
    out_dir: Path,
    *,
    meta: dict[str, object],
    best_df: pd.DataFrame,
    dist_df: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# MA Breakout Backtest Research")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- source dataset: `{meta['source']}`")
    lines.append(f"- daily candidate windows: `{meta['daily_range']}`")
    lines.append(f"- weekly candidate windows: `{meta['weekly_range']}`")
    lines.append(f"- monthly candidate windows: `{meta['monthly_range']}`")
    lines.append("- action rule: buy on upward crossover of close vs moving average, sell on downward crossover")
    lines.append("- crossover requires both current and previous completed periods to have a valid moving average")
    lines.append("- execution assumption: decision is made at close, position applies from the next bar")
    lines.append("- action mode A: monthly at month-end, weekly at week-end, daily at daily close")
    lines.append("- action mode B: evaluate monthly/weekly/daily moving averages at each daily close")
    lines.append("- daily action mode uses latest completed weekly/monthly MA and forward-fills it to daily dates")
    lines.append("- no transaction cost, tax, dividend, or split adjustment is applied")
    lines.append("")
    lines.append("## Coverage")
    lines.append(f"- analyzed rows: `{meta['result_rows']:,}`")
    lines.append(f"- analyzed stocks: `{meta['stock_count']:,}`")
    lines.append("")
    lines.append("## Most Common Best Windows")
    for action_mode in ["native_timeframe_close", "daily_close_action"]:
        lines.append(f"### {action_mode}")
        subset_action = dist_df[dist_df["action_mode"] == action_mode]
        if subset_action.empty:
            lines.append("- no rows")
            continue
        for timeframe in ["daily", "weekly", "monthly"]:
            subset = subset_action[subset_action["ma_timeframe"] == timeframe].head(10)
            lines.append(f"#### {timeframe}")
            if subset.empty:
                lines.append("- no rows")
                continue
            lines.append("| rank | window | stocks | share | avg_total_return | median_total_return | avg_max_drawdown |")
            lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
            for idx, (_, row) in enumerate(subset.iterrows(), start=1):
                lines.append(
                    f"| {idx} | {int(row['ma_window'])} | {int(row['stock_count'])} | "
                    f"{row['stock_share']:.4f} | {row['avg_total_return']:.4f} | "
                    f"{row['median_total_return']:.4f} | {row['avg_max_drawdown']:.4f} |"
                )
            lines.append("")

    if not best_df.empty:
        lines.append("## Best-Window Sample")
        sample = best_df.sort_values(["action_mode", "ma_timeframe", "code"]).head(12)
        lines.append("| action_mode | ma_timeframe | code | name | best_window | total_return | buy_hold_return | max_drawdown | trades |")
        lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |")
        for _, row in sample.iterrows():
            lines.append(
                f"| {row['action_mode']} | {row['ma_timeframe']} | {row['code']} | {row['name']} | "
                f"{int(row['ma_window'])} | {row['total_return']:.4f} | {row['buy_hold_return']:.4f} | "
                f"{row['max_drawdown']:.4f} | {int(row['trade_count'])} |"
            )

    (out_dir / "summary_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest MA breakout returns by stock for native vs daily action modes.")
    parser.add_argument("--source", type=Path, default=data_path("feature_daily.pkl"))
    parser.add_argument("--out-dir", type=Path, default=output_path("ma_breakout_research"))
    parser.add_argument("--daily-range", default="3-240")
    parser.add_argument("--weekly-range", default="3-60")
    parser.add_argument("--monthly-range", default="3-36")
    parser.add_argument("--min-bars", type=int, default=24)
    parser.add_argument("--limit-codes", type=int, default=0, help="debug/test limit on stock count")
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    today = pd.Timestamp.today().normalize()
    daily_windows = _parse_window_range(args.daily_range)
    weekly_windows = _parse_window_range(args.weekly_range)
    monthly_windows = _parse_window_range(args.monthly_range)

    df = pd.read_pickle(args.source)[["date", "code", "name", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["code"] = df["code"].astype(str).str.zfill(6)
    df = df.dropna(subset=["date", "code", "close"]).sort_values(["code", "date"]).reset_index(drop=True)

    if args.limit_codes > 0:
        keep_codes = df["code"].drop_duplicates().head(args.limit_codes)
        df = df[df["code"].isin(set(keep_codes))].copy()

    native_rows: list[dict[str, object]] = []
    daily_rows: list[dict[str, object]] = []

    grouped = df.groupby("code", sort=False)
    total_codes = grouped.ngroups
    for idx, (code, grp) in enumerate(grouped, start=1):
        name = str(grp["name"].dropna().iloc[-1]) if grp["name"].notna().any() else code
        stock_frame = grp[["date", "close"]].copy()
        native_rows.extend(
            evaluate_native_action(
                code,
                name,
                stock_frame,
                today=today,
                daily_windows=daily_windows,
                weekly_windows=weekly_windows,
                monthly_windows=monthly_windows,
                min_bars=args.min_bars,
            )
        )
        daily_rows.extend(
            evaluate_daily_action(
                code,
                name,
                stock_frame,
                today=today,
                daily_windows=daily_windows,
                weekly_windows=weekly_windows,
                monthly_windows=monthly_windows,
                min_bars=args.min_bars,
            )
        )
        if idx % 100 == 0 or idx == total_codes:
            print(f"[progress] {idx}/{total_codes} codes processed")

    native_df = pd.DataFrame(native_rows).sort_values(["ma_timeframe", "code", "ma_window"]).reset_index(drop=True)
    daily_df = pd.DataFrame(daily_rows).sort_values(["ma_timeframe", "code", "ma_window"]).reset_index(drop=True)
    combined_df = pd.concat([native_df, daily_df], ignore_index=True)
    best_df = summarize_best(combined_df)
    dist_df = summarize_distribution(best_df)

    native_df.to_csv(out_dir / "native_timeframe_close_returns_by_stock.csv", index=False, encoding="utf-8-sig")
    daily_df.to_csv(out_dir / "daily_close_action_returns_by_stock.csv", index=False, encoding="utf-8-sig")
    combined_df.to_csv(out_dir / "all_action_modes_returns_by_stock.csv", index=False, encoding="utf-8-sig")
    best_df.to_csv(out_dir / "best_window_by_stock.csv", index=False, encoding="utf-8-sig")
    dist_df.to_csv(out_dir / "best_window_distribution.csv", index=False, encoding="utf-8-sig")

    meta = {
        "source": str(args.source),
        "out_dir": str(out_dir),
        "daily_range": args.daily_range,
        "weekly_range": args.weekly_range,
        "monthly_range": args.monthly_range,
        "min_bars": args.min_bars,
        "limit_codes": args.limit_codes,
        "stock_count": int(combined_df["code"].nunique()) if not combined_df.empty else 0,
        "result_rows": int(len(combined_df)),
        "today": today.date().isoformat(),
    }
    (out_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    build_markdown_report(out_dir, meta=meta, best_df=best_df, dist_df=dist_df)
    print(f"[done] outputs written to {out_dir}")


if __name__ == "__main__":
    main()
