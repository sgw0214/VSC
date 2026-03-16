import argparse
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from new_strategy.paths import cache_path, data_path, output_path

from new_strategy.strategy_rules import StrategyConfig, add_features, build_ranked_signals


def load_price_panel(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix.lower() == ".pkl":
        df = pd.read_pickle(path)
    else:
        df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "code"]).reset_index(drop=True)


def is_feature_dataset(df: pd.DataFrame) -> bool:
    required = {"quality_score", "momentum_score", "ma_short", "ma_mid", "ma_long", "atr20"}
    return required.issubset(set(df.columns))


def load_macro_exposure(path: Optional[Path]) -> Optional[pd.Series]:
    if path is None or not path.exists():
        return None
    macro = pd.read_csv(path)
    macro["date"] = pd.to_datetime(macro["date"])
    if "exposure" not in macro.columns:
        raise ValueError("macro file must contain `exposure` column.")
    return macro.drop_duplicates("date").set_index("date")["exposure"]


def _target_positions(exposure: float, max_positions: int) -> int:
    exposure = float(np.clip(exposure, 0.0, 1.0))
    target = int(np.floor(exposure * max_positions))
    return int(min(max_positions, target))


def signal_rebalance_backtest(
    signal_df: pd.DataFrame,
    cfg: StrategyConfig,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    max_positions: int = 5,
    entry_top_n: int = 10,
    macro_exposure: Optional[pd.Series] = None,
    initial_positions: Optional[Dict[str, Dict[str, float]]] = None,
) -> tuple:
    use_cols = [
        "date",
        "code",
        "name",
        "close",
        "low",
        "ma_short",
        "ma_mid",
        "ma_long",
        "ma_short_slope",
        "ma_mid_slope",
        "entry_ok",
        "rank",
        "atr20",
    ]
    data = signal_df[(signal_df["date"] >= start_date) & (signal_df["date"] <= end_date)][use_cols].copy()
    if data.empty:
        return (
            pd.DataFrame(columns=["date", "daily_return", "equity", "n_positions"]),
            pd.DataFrame(columns=["date", "signal", "code", "name", "reason", "detail"]),
        )

    by_date: Dict[pd.Timestamp, pd.DataFrame] = {d: g.set_index("code") for d, g in data.groupby("date", sort=True)}
    dates = sorted(by_date.keys())

    positions: Dict[str, Dict[str, float]] = dict(initial_positions) if initial_positions else {}
    history = []
    trade_logs: List[Dict[str, object]] = []
    prev_date = None

    for dt in dates:
        today = by_date[dt]
        sold_today = set()
        exposure = 1.0 if macro_exposure is None else float(macro_exposure.get(dt, 1.0))
        target_n = _target_positions(exposure, max_positions)

        # Increase holding day counter for existing positions at each new trading day.
        for code in list(positions.keys()):
            positions[code]["hold_days"] = int(positions[code].get("hold_days", 0)) + 1

        daily_ret = 0.0
        if prev_date is not None and positions:
            prev = by_date.get(prev_date)
            rlist = []
            if prev is not None:
                for code in list(positions.keys()):
                    if code in prev.index and code in today.index:
                        prev_close = float(prev.at[code, "close"])
                        cur_close = float(today.at[code, "close"])
                        if prev_close > 0 and np.isfinite(cur_close):
                            rlist.append(cur_close / prev_close - 1.0)
            if rlist:
                daily_ret = float(np.mean(rlist))

        if positions:
            to_exit = []
            for code, pos in positions.items():
                if code not in today.index:
                    to_exit.append(code)
                    continue
                row = today.loc[code]
                close = float(row["close"])
                low = float(row["low"])
                ma_short = float(row["ma_short"]) if pd.notna(row["ma_short"]) else np.nan
                ma_mid = float(row["ma_mid"]) if pd.notna(row["ma_mid"]) else np.nan
                ma_long = float(row["ma_long"]) if pd.notna(row["ma_long"]) else np.nan
                ma_short_slope = float(row["ma_short_slope"]) if pd.notna(row["ma_short_slope"]) else np.nan
                ma_mid_slope = float(row["ma_mid_slope"]) if pd.notna(row["ma_mid_slope"]) else np.nan
                rank = float(row["rank"]) if pd.notna(row["rank"]) else np.inf
                hold_days = int(pos.get("hold_days", 0))

                stop_breach = (low / pos["entry_price"] - 1.0) <= pos["stop_pct"]
                # Exit trend: 5w and 10w both turned down (AND), with optional buffer filter.
                trend_breach_today = (
                    pd.notna(ma_short_slope)
                    and pd.notna(ma_mid_slope)
                    and (ma_short_slope < 0)
                    and (ma_mid_slope < 0)
                    and (pd.notna(ma_short) and pd.notna(ma_mid) and ma_short < ma_mid * (1.0 + cfg.trend_exit_buffer))
                )
                if trend_breach_today:
                    pos["trend_breach_days"] = int(pos.get("trend_breach_days", 0)) + 1
                else:
                    pos["trend_breach_days"] = 0
                trend_break = (hold_days >= int(cfg.min_hold_days)) and (
                    int(pos.get("trend_breach_days", 0)) >= int(cfg.trend_exit_confirm_days)
                )
                rank_break = False

                if stop_breach or trend_break or rank_break:
                    to_exit.append(code)
                    reasons = []
                    if stop_breach:
                        reasons.append("stop_loss")
                    if trend_break:
                        reasons.append("trend_break")
                    if rank_break:
                        reasons.append("rank_break")
                    if stop_breach:
                        realized_ret = float(pos["stop_pct"])
                    else:
                        realized_ret = float(close / pos["entry_price"] - 1.0)
                    ma_mid_txt = f"{ma_mid:.2f}" if np.isfinite(ma_mid) else "nan"
                    ma_short_txt = f"{ma_short:.2f}" if np.isfinite(ma_short) else "nan"
                    trade_logs.append(
                        {
                            "date": dt,
                            "signal": "SELL",
                            "code": code,
                            "name": str(row["name"]) if "name" in row.index else "",
                            "reason": "|".join(reasons),
                            "detail": f"hold_days={hold_days},rank={rank:.0f},close={close:.2f},ma_short={ma_short_txt},ma_mid={ma_mid_txt},trend_days={int(pos.get('trend_breach_days',0))},stop_pct={pos['stop_pct']:.4f},realized_ret={realized_ret:.4f}",
                        }
                    )
                    sold_today.add(code)

            for code in to_exit:
                positions.pop(code, None)

        effective_target_n = max(target_n, len(positions))
        if len(positions) < effective_target_n:
            cands = today[(today["entry_ok"] == True) & (today["rank"] <= entry_top_n)].copy()
            cands = cands.sort_values("rank")
            for code, row in cands.iterrows():
                if len(positions) >= effective_target_n:
                    break
                if code in positions:
                    continue
                if code in sold_today:
                    # Prevent same-day churn: do not re-enter a symbol sold on the same date.
                    continue
                close = float(row["close"])
                if not np.isfinite(close) or close <= 0:
                    continue
                if cfg.stop_mode == "atr" and pd.notna(row["atr20"]):
                    stop_pct = -float(cfg.atr_mult * row["atr20"] / close)
                else:
                    stop_pct = float(cfg.fixed_stop_loss)
                positions[code] = {
                    "entry_price": close,
                    "entry_date": dt,
                    "stop_pct": stop_pct,
                    "trend_breach_days": 0,
                    "hold_days": 0,
                }
                rank = float(row["rank"]) if pd.notna(row["rank"]) else np.nan
                trade_logs.append(
                    {
                        "date": dt,
                        "signal": "BUY",
                        "code": code,
                        "name": str(row["name"]) if "name" in row.index else "",
                        "reason": "entry_signal",
                        "detail": f"hold_days=0,rank={rank:.0f},exposure={exposure:.2f},target_n={target_n},stop_pct={stop_pct:.4f}",
                    }
                )
        elif len(positions) >= max_positions:
            cands = today[(today["entry_ok"] == True) & (today["rank"] <= entry_top_n)].copy()
            cands = cands.sort_values("rank")
            for code, row in cands.iterrows():
                if code in positions:
                    continue
                trade_logs.append(
                    {
                        "date": dt,
                        "signal": "CANDIDATE",
                        "code": code,
                        "name": str(row["name"]) if "name" in row.index else "",
                        "reason": "candidate_only_full_positions",
                        "detail": f"rank={float(row['rank']):.0f},positions={len(positions)},max_positions={max_positions},exposure={exposure:.2f}",
                    }
                )

        history.append({"date": dt, "daily_return": daily_ret, "n_positions": len(positions)})
        prev_date = dt

    curve = pd.DataFrame(history).sort_values("date")
    curve["equity"] = (1.0 + curve["daily_return"]).cumprod()
    log_df = pd.DataFrame(trade_logs).sort_values(["date", "signal", "code"]) if trade_logs else pd.DataFrame(
        columns=["date", "signal", "code", "name", "reason", "detail"]
    )
    return curve, log_df, positions


def performance_stats(curve: pd.DataFrame) -> dict:
    if curve.empty:
        return {"cagr": np.nan, "mdd": np.nan, "sharpe": np.nan, "win_rate": np.nan, "days": 0}
    ret = curve["daily_return"].fillna(0.0)
    n = len(ret)
    years = n / 252.0
    final_equity = curve["equity"].iloc[-1]
    cagr = final_equity ** (1.0 / years) - 1.0 if years > 0 else np.nan
    running_max = curve["equity"].cummax()
    drawdown = curve["equity"] / running_max - 1.0
    mdd = float(drawdown.min())
    vol = ret.std(ddof=0) * np.sqrt(252)
    sharpe = float((ret.mean() * 252) / vol) if vol > 0 else np.nan
    win_rate = float((ret > 0).mean())
    return {"cagr": cagr, "mdd": mdd, "sharpe": sharpe, "win_rate": win_rate, "days": int(n)}


def run_walkforward(
    signal_df: pd.DataFrame,
    cfg: StrategyConfig,
    train_years: int,
    test_years: int,
    max_positions: int,
    entry_top_n: int,
    macro_exposure: Optional[pd.Series] = None,
) -> tuple:
    years = sorted(signal_df["date"].dt.year.unique())
    first_year, last_year = years[0], years[-1]
    rows = []
    logs = []
    carry_positions: Dict[str, Dict[str, float]] = {}
    test_start = first_year + train_years

    while test_start <= last_year:
        test_end = min(test_start + test_years - 1, last_year)
        carry_in = len(carry_positions)
        curve, trade_log, carry_positions = signal_rebalance_backtest(
            signal_df=signal_df,
            cfg=cfg,
            start_date=pd.Timestamp(f"{test_start}-01-01"),
            end_date=pd.Timestamp(f"{test_end}-12-31"),
            max_positions=max_positions,
            entry_top_n=entry_top_n,
            macro_exposure=macro_exposure,
            initial_positions=carry_positions,
        )
        stats = performance_stats(curve)
        rows.append(
            {
                "test_start_year": test_start,
                "test_end_year": test_end,
                "carry_in_positions": carry_in,
                "carry_out_positions": len(carry_positions),
                "max_positions": max_positions,
                "entry_top_n": entry_top_n,
                "stop_mode": cfg.stop_mode,
                "fixed_stop": cfg.fixed_stop_loss,
                "atr_mult": cfg.atr_mult,
                **stats,
            }
        )
        if not trade_log.empty:
            trade_log = trade_log.copy()
            trade_log["test_start_year"] = test_start
            trade_log["test_end_year"] = test_end
            logs.append(trade_log)
        test_start += test_years

    all_logs = pd.concat(logs, ignore_index=True) if logs else pd.DataFrame(
        columns=["date", "signal", "code", "name", "reason", "detail", "test_start_year", "test_end_year"]
    )
    return pd.DataFrame(rows), all_logs


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Signal-based walk-forward backtest with dynamic rebalancing.")
    p.add_argument("--price-panel", default=str(data_path("feature_daily.pkl")))
    p.add_argument("--macro", default="", help="Optional macro regime csv with date,exposure")
    p.add_argument("--train-years", type=int, default=6)
    p.add_argument("--test-years", type=int, default=1)
    p.add_argument("--max-positions", type=int, default=5, help="Backtest portfolio cap (<=5)")
    p.add_argument("--entry-top-n", type=int, default=10, help="Entry candidate pool ranked by signal")
    p.add_argument("--stop-mode", default="atr", choices=["fixed", "atr"])
    p.add_argument("--fixed-stop", type=float, default=-0.08)
    p.add_argument("--atr-mult", type=float, default=2.5)
    p.add_argument("--feature-cache", default=str(cache_path("features", "features.pkl")))
    p.add_argument("--no-feature-cache", action="store_true")
    p.add_argument("--output", default=str(output_path("walkforward_result_signal.csv")))
    p.add_argument("--signal-log-output", default="", help="Optional output path for buy/sell signal logs csv")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    price_df = load_price_panel(Path(args.price_panel))
    cfg = StrategyConfig(
        top_n=args.entry_top_n,
        stop_mode=args.stop_mode,
        atr_mult=args.atr_mult,
        fixed_stop_loss=args.fixed_stop,
    )

    feature_cache = Path(args.feature_cache)
    if is_feature_dataset(price_df):
        feature_df = price_df.copy()
        print("[feature] using prebuilt feature dataset")
    elif (not args.no_feature_cache) and feature_cache.exists():
        print(f"[feature-cache] {feature_cache}")
        feature_df = pd.read_pickle(feature_cache)
    else:
        feature_df = add_features(price_df, cfg)
        if not args.no_feature_cache:
            feature_cache.parent.mkdir(parents=True, exist_ok=True)
            feature_df.to_pickle(feature_cache)
            print(f"[feature-cache-write] {feature_cache}")

    signal_df = build_ranked_signals(feature_df, cfg, forward_col="ret_1d_fwd")
    macro_series = load_macro_exposure(Path(args.macro)) if args.macro else None

    result, signal_logs = run_walkforward(
        signal_df=signal_df,
        cfg=cfg,
        train_years=args.train_years,
        test_years=args.test_years,
        max_positions=args.max_positions,
        entry_top_n=args.entry_top_n,
        macro_exposure=macro_series,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[saved] {out}")
    print(result.to_string(index=False))

    sig_out = Path(args.signal_log_output) if args.signal_log_output else out.with_name(f"{out.stem}_signals.csv")
    signal_logs.to_csv(sig_out, index=False, encoding="utf-8-sig")
    print(f"[saved] {sig_out}")


if __name__ == "__main__":
    main()
