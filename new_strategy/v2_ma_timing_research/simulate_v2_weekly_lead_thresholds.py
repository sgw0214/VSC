from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from new_strategy.paths import data_path, output_path


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


def _load_optimal_windows(source: Path) -> pd.DataFrame:
    df = pd.read_csv(source, dtype={"code": str}, low_memory=False)
    work = df[
        (df["action_mode"] == "native_timeframe_close")
        & (df["ma_timeframe"].isin(["monthly", "weekly"]))
    ].copy()
    work["ma_window"] = pd.to_numeric(work["ma_window"], errors="coerce")
    work = work.loc[work["ma_window"] >= 2].copy()
    if work.empty:
        return pd.DataFrame()

    monthly = work.loc[work["ma_timeframe"] == "monthly", ["code", "name", "ma_window"]].rename(
        columns={"ma_window": "monthly_window"}
    )
    weekly = work.loc[work["ma_timeframe"] == "weekly", ["code", "ma_window"]].rename(
        columns={"ma_window": "weekly_window"}
    )
    merged = monthly.merge(weekly, on="code", how="inner")
    merged["monthly_window"] = merged["monthly_window"].astype(int)
    merged["weekly_window"] = merged["weekly_window"].astype(int)
    return merged.drop_duplicates(subset=["code"]).reset_index(drop=True)


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
    out["month_ord"] = out["month_period"].map(lambda p: int(p.ordinal))
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
    out["week_ord"] = out["week_period"].map(lambda p: int(p.ordinal))
    out["month_period"] = out["decision_date"].dt.to_period("M")
    out["month_ord"] = out["month_period"].map(lambda p: int(p.ordinal))
    return out


def _build_daily_observation_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame[["date", "close"]].copy().rename(columns={"date": "decision_date"})
    out["week_period"] = out["decision_date"].dt.to_period("W-FRI")
    out["week_ord"] = out["week_period"].map(lambda p: int(p.ordinal))
    out["month_period"] = out["decision_date"].dt.to_period("M")
    out["month_ord"] = out["month_period"].map(lambda p: int(p.ordinal))
    return out.reset_index(drop=True)


def _completed_month_state_map(monthly_df: pd.DataFrame, window: int, buy_threshold: float) -> tuple[np.ndarray, np.ndarray, dict[int, bool]]:
    closes = monthly_df["close"].to_numpy(dtype=float)
    ords = monthly_df["month_ord"].to_numpy(dtype=int)
    ma = _rolling_mean(closes, window)
    state = np.where(np.isfinite(ma), closes >= ma * (1.0 + buy_threshold), np.nan)
    state_map = {
        int(ord_): bool(st)
        for ord_, st in zip(ords, state)
        if pd.notna(st)
    }
    return ords, closes, state_map


def _completed_week_state_map(weekly_df: pd.DataFrame, window: int, sell_threshold: float) -> tuple[np.ndarray, np.ndarray, dict[int, bool]]:
    closes = weekly_df["close"].to_numpy(dtype=float)
    ords = weekly_df["week_ord"].to_numpy(dtype=int)
    ma = _rolling_mean(closes, window)
    state = np.where(np.isfinite(ma), closes <= ma * (1.0 + sell_threshold), np.nan)
    state_map = {
        int(ord_): bool(st)
        for ord_, st in zip(ords, state)
        if pd.notna(st)
    }
    return ords, closes, state_map


def _build_monthly_lead_buy_events(
    monthly_df: pd.DataFrame,
    obs_df: pd.DataFrame,
    window: int,
    buy_threshold: float,
) -> pd.DataFrame:
    completed_ord, completed_close, prev_state_map = _completed_month_state_map(monthly_df, window, buy_threshold)
    rows: list[dict[str, object]] = []
    for row in obs_df.itertuples(index=False):
        month_ord = int(row.month_ord)
        prior_count = int(np.searchsorted(completed_ord, month_ord, side="left"))
        if prior_count < window - 1:
            continue
        prior_slice = completed_close[prior_count - (window - 1) : prior_count]
        if len(prior_slice) != window - 1 or not np.all(np.isfinite(prior_slice)):
            continue
        provisional_ma = (float(np.sum(prior_slice)) + float(row.close)) / float(window)
        state = bool(float(row.close) >= provisional_ma * (1.0 + buy_threshold))
        rows.append(
            {
                "decision_date": pd.Timestamp(row.decision_date),
                "bucket_ord": month_ord,
                "prev_completed_ord": month_ord - 1,
                "state": state,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["decision_date", "event_type"])

    state_df = pd.DataFrame(rows).sort_values("decision_date").reset_index(drop=True)
    events: list[dict[str, object]] = []
    prev_bucket: int | None = None
    prev_state: bool | None = None

    for row in state_df.itertuples(index=False):
        if prev_bucket != int(row.bucket_ord):
            prev_bucket = int(row.bucket_ord)
            prev_state = prev_state_map.get(int(row.prev_completed_ord))
            if prev_state is None:
                continue
        current_state = bool(row.state)
        if (not prev_state) and current_state:
            events.append({"decision_date": pd.Timestamp(row.decision_date), "event_type": "buy"})
        prev_state = current_state

    if not events:
        return pd.DataFrame(columns=["decision_date", "event_type"])
    return pd.DataFrame(events)


def _build_weekly_lead_sell_events(
    weekly_df: pd.DataFrame,
    obs_df: pd.DataFrame,
    window: int,
    sell_threshold: float,
) -> pd.DataFrame:
    completed_ord, completed_close, prev_state_map = _completed_week_state_map(weekly_df, window, sell_threshold)
    rows: list[dict[str, object]] = []
    for row in obs_df.itertuples(index=False):
        week_ord = int(row.week_ord)
        prior_count = int(np.searchsorted(completed_ord, week_ord, side="left"))
        if prior_count < window - 1:
            continue
        prior_slice = completed_close[prior_count - (window - 1) : prior_count]
        if len(prior_slice) != window - 1 or not np.all(np.isfinite(prior_slice)):
            continue
        provisional_ma = (float(np.sum(prior_slice)) + float(row.close)) / float(window)
        state = bool(float(row.close) <= provisional_ma * (1.0 + sell_threshold))
        rows.append(
            {
                "decision_date": pd.Timestamp(row.decision_date),
                "bucket_ord": week_ord,
                "prev_completed_ord": week_ord - 1,
                "state": state,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["decision_date", "event_type"])

    state_df = pd.DataFrame(rows).sort_values("decision_date").reset_index(drop=True)
    events: list[dict[str, object]] = []
    prev_bucket: int | None = None
    prev_state: bool | None = None

    for row in state_df.itertuples(index=False):
        if prev_bucket != int(row.bucket_ord):
            prev_bucket = int(row.bucket_ord)
            prev_state = prev_state_map.get(int(row.prev_completed_ord))
            if prev_state is None:
                continue
        current_state = bool(row.state)
        if (not prev_state) and current_state:
            events.append({"decision_date": pd.Timestamp(row.decision_date), "event_type": "sell"})
        prev_state = current_state

    if not events:
        return pd.DataFrame(columns=["decision_date", "event_type"])
    return pd.DataFrame(events)


def _simulate_daily_from_events(
    daily_df: pd.DataFrame,
    buy_events: pd.DataFrame,
    sell_events: pd.DataFrame,
    *,
    start_date: pd.Timestamp,
) -> dict[str, object]:
    work = daily_df.loc[daily_df["date"] >= start_date, ["date", "close"]].copy().reset_index(drop=True)
    if len(work) < 2:
        return {}

    buy_dates = {pd.Timestamp(ts).normalize() for ts in buy_events["decision_date"].tolist()}
    sell_dates = {pd.Timestamp(ts).normalize() for ts in sell_events["decision_date"].tolist()}

    dates = work["date"].to_numpy()
    prices = work["close"].to_numpy(dtype=float)
    position = np.zeros(len(work), dtype=float)
    current_state = 0.0
    action_count = 0
    action_months: set[pd.Period] = set()

    for idx in range(1, len(work)):
        prev_date = pd.Timestamp(dates[idx - 1]).normalize()
        prev_month = prev_date.to_period("M")
        can_act = prev_month not in action_months
        if can_act and current_state == 1.0 and prev_date in sell_dates:
            current_state = 0.0
            action_count += 1
            action_months.add(prev_month)
        elif can_act and current_state == 0.0 and prev_date in buy_dates:
            current_state = 1.0
            action_count += 1
            action_months.add(prev_month)
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
        "win_rate": float(wins / completed) if completed > 0 else np.nan,
        "exposure_ratio": exposure_ratio,
    }


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _combo_label(mode_label: str, buy_threshold: float, sell_threshold: float) -> str:
    return f"{mode_label}__buy_{_fmt_pct(buy_threshold)}__sell_{_fmt_pct(sell_threshold)}"


def _write_markdown(summary_df: pd.DataFrame, out_path: Path, stock_count: int) -> None:
    lines: list[str] = []
    lines.append("# V2 Weekly Lead Simulation")
    lines.append("")
    lines.append("## Assumption")
    lines.append("- `week_daily_lead`: observe provisional current month/week state on every trading-day close")
    lines.append("- `week_close_lead`: observe provisional current month/week state only on weekly close")
    lines.append("- buy trigger: previous completed month was below the monthly threshold, current provisional month is above it")
    lines.append("- sell trigger: previous completed week was above the weekly threshold, current provisional week is below it")
    lines.append("")
    lines.append("## Coverage")
    lines.append(f"- simulated stocks: `{stock_count}`")
    lines.append("")
    lines.append("## Combo Summary")
    lines.append("| mode | combo | avg_total_return | median_total_return | avg_annualized_return | avg_max_drawdown | avg_trade_count |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for row in summary_df.itertuples(index=False):
        lines.append(
            f"| {row.mode} | {row.combo_label} | {row.avg_total_return:.4f} | {row.median_total_return:.4f} | "
            f"{row.avg_annualized_return:.4f} | {row.avg_max_drawdown:.4f} | {row.avg_trade_count:.2f} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate V2 weekly lead modes with monthly buy / weekly sell thresholds.")
    parser.add_argument("--limit-codes", type=int, default=0, help="Optional limit for sample validation.")
    args = parser.parse_args()

    price_source = data_path("feature_daily.pkl")
    selection_source = output_path("ma_breakout_research", "published", "optimal_ma_selection_all_timeframes.csv")
    out_dir = output_path("v2_weekly_lead_threshold_research")
    out_dir.mkdir(parents=True, exist_ok=True)

    prices = _load_daily_prices(price_source)
    selections = _load_optimal_windows(selection_source)
    if args.limit_codes > 0:
        keep_codes = selections["code"].head(args.limit_codes).tolist()
        selections = selections.loc[selections["code"].isin(keep_codes)].copy()

    modes = {
        "week_daily_lead": "daily",
        "week_close_lead": "weekly_close",
    }
    buy_thresholds = [0.00, 0.02, 0.05]
    sell_thresholds = [0.00, -0.02, -0.05]
    combos = list(product(buy_thresholds, sell_thresholds))

    rows: list[dict[str, object]] = []
    total = len(selections)

    for idx, sel in enumerate(selections.itertuples(index=False), start=1):
        code = str(sel.code).zfill(6)
        stock_df = prices.loc[prices["code"] == code, ["date", "close"]].copy().sort_values("date")
        if stock_df.empty:
            continue

        monthly_df = _build_monthly_frame(stock_df)
        weekly_df = _build_weekly_frame(stock_df)
        daily_obs_df = _build_daily_observation_frame(stock_df)
        weekly_obs_df = weekly_df[["decision_date", "close", "week_ord", "month_ord"]].copy()

        monthly_window = int(sel.monthly_window)
        weekly_window = int(sel.weekly_window)

        month_ma = _rolling_mean(monthly_df["close"].to_numpy(dtype=float), monthly_window)
        valid_start_dates = monthly_df.loc[np.isfinite(month_ma), "decision_date"]
        if valid_start_dates.empty:
            continue
        start_date = pd.Timestamp(valid_start_dates.iloc[0])

        for mode_label, mode_kind in modes.items():
            obs_df = daily_obs_df if mode_kind == "daily" else weekly_obs_df
            for buy_threshold, sell_threshold in combos:
                buy_events = _build_monthly_lead_buy_events(monthly_df, obs_df, monthly_window, buy_threshold)
                sell_events = _build_weekly_lead_sell_events(weekly_df, obs_df, weekly_window, sell_threshold)
                metrics = _simulate_daily_from_events(
                    stock_df,
                    buy_events,
                    sell_events,
                    start_date=start_date,
                )
                if not metrics:
                    continue
                rows.append(
                    {
                        "mode": mode_label,
                        "code": code,
                        "name": sel.name,
                        "monthly_window": monthly_window,
                        "weekly_window": weekly_window,
                        "buy_threshold": buy_threshold,
                        "sell_threshold": sell_threshold,
                        "combo_label": _combo_label(mode_label, buy_threshold, sell_threshold),
                        **metrics,
                    }
                )

        if idx % 100 == 0 or idx == total:
            print(f"[progress] {idx}/{total} codes processed")

    results = pd.DataFrame(rows)
    if results.empty:
        raise RuntimeError("No simulation results were produced.")

    results.to_csv(out_dir / "stock_combo_results.csv", index=False, encoding="utf-8-sig")

    summary = (
        results.groupby(["mode", "combo_label", "buy_threshold", "sell_threshold"], as_index=False)
        .agg(
            stock_count=("code", "nunique"),
            avg_total_return=("total_return", "mean"),
            median_total_return=("total_return", "median"),
            avg_annualized_return=("annualized_return", "mean"),
            avg_max_drawdown=("max_drawdown", "mean"),
            avg_trade_count=("trade_count", "mean"),
            avg_win_rate=("win_rate", "mean"),
            avg_exposure_ratio=("exposure_ratio", "mean"),
        )
        .sort_values(["mode", "avg_total_return", "avg_annualized_return"], ascending=[True, False, False])
        .reset_index(drop=True)
    )
    summary.to_csv(out_dir / "combo_summary.csv", index=False, encoding="utf-8-sig")

    ranked = results.sort_values(
        [
            "mode",
            "code",
            "total_return",
            "max_drawdown",
            "completed_trade_count",
            "annualized_return",
            "win_rate",
            "trade_count",
        ],
        ascending=[True, True, False, False, False, False, False, True],
    )
    best = ranked.groupby(["mode", "code"], as_index=False).head(1).reset_index(drop=True)
    best.to_csv(out_dir / "best_combo_by_stock.csv", index=False, encoding="utf-8-sig")

    _write_markdown(summary, out_dir / "summary_report.md", int(results["code"].nunique()))
    run_meta = {
        "price_source": str(price_source),
        "selection_source": str(selection_source),
        "modes": list(modes),
        "buy_thresholds": buy_thresholds,
        "sell_thresholds": sell_thresholds,
        "limit_codes": int(args.limit_codes),
        "stock_count": int(results["code"].nunique()),
        "row_count": int(len(results)),
        "assumption": {
            "week_daily_lead": "observe provisional current month/week state on every trading-day close",
            "week_close_lead": "observe provisional current month/week state only on weekly close",
        },
    }
    (out_dir / "run_meta.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] outputs written to {out_dir}")


if __name__ == "__main__":
    main()
