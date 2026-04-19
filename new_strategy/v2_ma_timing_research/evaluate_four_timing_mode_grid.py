from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from new_strategy.paths import data_path, output_path


DEFAULT_WINDOWS = [1, 2, 3, 4, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]
MODES = {
    "monthly_buy_weekly_sell": ("monthly", "weekly"),
    "weekly_buy_monthly_sell": ("weekly", "monthly"),
    "monthly_buy_monthly_sell": ("monthly", "monthly"),
    "weekly_buy_weekly_sell": ("weekly", "weekly"),
}


def _load_daily_prices(source: Path) -> pd.DataFrame:
    df = pd.read_pickle(source)[["date", "code", "name", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return (
        df.dropna(subset=["date", "code", "close"])
        .sort_values(["code", "date"])
        .reset_index(drop=True)
    )


def _build_timeframe_frame(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    temp = frame[["date", "close"]].copy()
    if timeframe == "monthly":
        temp["bucket"] = temp["date"].dt.to_period("M")
    elif timeframe == "weekly":
        temp["bucket"] = temp["date"].dt.to_period("W-FRI")
    else:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    out = (
        temp.groupby("bucket", as_index=False)
        .agg(decision_date=("date", "max"), close=("close", "last"))
        .sort_values("decision_date")
        .reset_index(drop=True)
    )
    return out


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=float)
    if len(values) < window:
        return out
    csum = np.concatenate(([0.0], np.cumsum(values, dtype=float)))
    out[window - 1 :] = (csum[window:] - csum[:-window]) / float(window)
    return out


def _build_event_map(tf_df: pd.DataFrame, window: int, event_type: str) -> tuple[set[pd.Timestamp], pd.Timestamp | None]:
    prices = tf_df["close"].to_numpy(dtype=float)
    ma = _rolling_mean(prices, window)
    valid_mask = np.isfinite(ma)
    if not valid_mask.any():
        return set(), None
    if event_type == "buy":
        state = prices >= ma
    elif event_type == "sell":
        state = prices <= ma
    else:
        raise ValueError(f"Unsupported event_type: {event_type}")

    valid_idx = np.flatnonzero(valid_mask)
    start_date = pd.Timestamp(tf_df.iloc[int(valid_idx[0])]["decision_date"])

    events: set[pd.Timestamp] = set()
    prev_state: bool | None = None
    for idx in valid_idx:
        current_state = bool(state[idx])
        if prev_state is not None and (not prev_state) and current_state:
            events.add(pd.Timestamp(tf_df.iloc[int(idx)]["decision_date"]).normalize())
        prev_state = current_state
    return events, start_date


def _precompute_timeframe_events(
    tf_df: pd.DataFrame,
    windows: list[int],
) -> tuple[dict[int, set[pd.Timestamp]], dict[int, set[pd.Timestamp]], dict[int, pd.Timestamp | None]]:
    buy_events: dict[int, set[pd.Timestamp]] = {}
    sell_events: dict[int, set[pd.Timestamp]] = {}
    valid_starts: dict[int, pd.Timestamp | None] = {}
    for window in windows:
        b_events, start_date = _build_event_map(tf_df, window, "buy")
        s_events, _ = _build_event_map(tf_df, window, "sell")
        buy_events[window] = b_events
        sell_events[window] = s_events
        valid_starts[window] = start_date
    return buy_events, sell_events, valid_starts


def _simulate_daily_from_events(
    daily_df: pd.DataFrame,
    buy_dates: set[pd.Timestamp],
    sell_dates: set[pd.Timestamp],
    *,
    start_date: pd.Timestamp,
) -> dict[str, object]:
    work = daily_df.loc[daily_df["date"] >= start_date, ["date", "close"]].copy().reset_index(drop=True)
    if len(work) < 2:
        return {}

    dates = work["date"].to_numpy()
    prices = work["close"].to_numpy(dtype=float)
    position = np.zeros(len(work), dtype=float)
    current_state = 0.0
    action_count = 0

    for idx in range(1, len(work)):
        prev_date = pd.Timestamp(dates[idx - 1]).normalize()
        if current_state == 1.0 and prev_date in sell_dates:
            current_state = 0.0
            action_count += 1
        elif current_state == 0.0 and prev_date in buy_dates:
            current_state = 1.0
            action_count += 1
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
        "test_start": pd.Timestamp(work["date"].iloc[0]).date().isoformat(),
        "test_end": pd.Timestamp(work["date"].iloc[-1]).date().isoformat(),
        "bars": int(len(work)),
        "total_return": total_return,
        "buy_hold_return": buy_hold_return,
        "excess_return": total_return - buy_hold_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
        "trade_count": int(action_count),
        "completed_trade_count": int(completed),
        "win_rate": float(wins / completed) if completed else np.nan,
        "exposure_ratio": exposure_ratio,
    }


def _evaluate_stock_grid(stock_df: pd.DataFrame, code: str, name: str, windows: list[int]) -> list[dict[str, object]]:
    monthly_df = _build_timeframe_frame(stock_df, "monthly")
    weekly_df = _build_timeframe_frame(stock_df, "weekly")
    tf_cache = {}
    for timeframe, tf_df in [("monthly", monthly_df), ("weekly", weekly_df)]:
        buy_events, sell_events, starts = _precompute_timeframe_events(tf_df, windows)
        tf_cache[timeframe] = {
            "buy": buy_events,
            "sell": sell_events,
            "starts": starts,
        }

    rows: list[dict[str, object]] = []
    for mode_label, (buy_tf, sell_tf) in MODES.items():
        for buy_window in windows:
            buy_dates = tf_cache[buy_tf]["buy"][buy_window]
            buy_start = tf_cache[buy_tf]["starts"][buy_window]
            if buy_start is None:
                continue
            for sell_window in windows:
                sell_dates = tf_cache[sell_tf]["sell"][sell_window]
                sell_start = tf_cache[sell_tf]["starts"][sell_window]
                if sell_start is None:
                    continue
                start_date = max(buy_start, sell_start)
                metrics = _simulate_daily_from_events(
                    stock_df,
                    buy_dates,
                    sell_dates,
                    start_date=start_date,
                )
                if not metrics:
                    continue
                rows.append(
                    {
                        "code": code,
                        "name": name,
                        "mode": mode_label,
                        "buy_timeframe": buy_tf,
                        "sell_timeframe": sell_tf,
                        "buy_window": buy_window,
                        "sell_window": sell_window,
                        **metrics,
                    }
                )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate 4 buy/sell timeframe combinations across 1..120 windows.")
    parser.add_argument("--limit-codes", type=int, default=1, help="How many codes to process for validation.")
    parser.add_argument("--code", type=str, default="", help="Optional single code to evaluate.")
    parser.add_argument(
        "--windows",
        type=str,
        default="5,10,20,30,40,50,60,70,80,90,100",
        help="Comma-separated window candidates.",
    )
    args = parser.parse_args()

    windows = sorted({int(part.strip()) for part in str(args.windows).split(",") if part.strip()})
    if not windows:
        raise RuntimeError("No windows provided.")

    price_source = data_path("feature_daily.pkl")
    out_dir = output_path("v2_four_timing_mode_grid")
    out_dir.mkdir(parents=True, exist_ok=True)

    prices = _load_daily_prices(price_source)
    codes = prices[["code", "name"]].drop_duplicates().sort_values("code").reset_index(drop=True)

    if args.code:
        target = str(args.code).zfill(6)
        codes = codes.loc[codes["code"] == target].copy()
    elif args.limit_codes > 0:
        codes = codes.head(args.limit_codes).copy()

    if codes.empty:
        raise RuntimeError("No codes selected for evaluation.")

    run_scope = "full" if (not args.code and args.limit_codes == 0) else "sample"

    rows: list[dict[str, object]] = []
    benchmarks: list[dict[str, object]] = []
    total_codes = len(codes)

    for idx, row in enumerate(codes.itertuples(index=False), start=1):
        code = str(row.code).zfill(6)
        name = str(row.name)
        stock_df = prices.loc[prices["code"] == code, ["date", "close"]].copy().sort_values("date")
        started = time.perf_counter()
        stock_rows = _evaluate_stock_grid(stock_df, code, name, windows)
        elapsed = time.perf_counter() - started
        rows.extend(stock_rows)
        benchmarks.append(
            {
                "code": code,
                "name": name,
                "elapsed_seconds": elapsed,
                "combo_count": len(stock_rows),
            }
        )
        print(f"[progress] {idx}/{total_codes} {code} {name} -> {len(stock_rows)} rows in {elapsed:.2f}s")

    results = pd.DataFrame(rows)
    bench_df = pd.DataFrame(benchmarks)
    if results.empty:
        raise RuntimeError("No results produced.")

    results.to_csv(out_dir / f"stock_mode_window_results_{run_scope}.csv", index=False, encoding="utf-8-sig")
    bench_df.to_csv(out_dir / f"benchmark_{run_scope}.csv", index=False, encoding="utf-8-sig")

    summary = (
        results.groupby("mode", as_index=False)
        .agg(
            stock_count=("code", "nunique"),
            combo_count=("code", "size"),
            avg_total_return=("total_return", "mean"),
            median_total_return=("total_return", "median"),
            avg_excess_return=("excess_return", "mean"),
            avg_max_drawdown=("max_drawdown", "mean"),
            avg_trade_count=("trade_count", "mean"),
        )
        .sort_values("avg_total_return", ascending=False)
        .reset_index(drop=True)
    )
    summary.to_csv(out_dir / f"mode_summary_{run_scope}.csv", index=False, encoding="utf-8-sig")

    run_meta = {
        "price_source": str(price_source),
        "modes": MODES,
        "windows": windows,
        "selected_codes": codes.to_dict(orient="records"),
        "benchmark_seconds_total": float(bench_df["elapsed_seconds"].sum()),
        "benchmark_seconds_avg_per_code": float(bench_df["elapsed_seconds"].mean()),
        "rows": int(len(results)),
    }
    (out_dir / f"run_meta_{run_scope}.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] sample outputs written to {out_dir}")


if __name__ == "__main__":
    main()
