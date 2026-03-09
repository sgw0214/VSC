from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StrategyConfig:
    liquidity_min_value: float = 1_000_000_000.0
    liquidity_top_quantile: float = 0.30
    liquidity_trend_ratio: float = 1.0
    # 5-week ~= 25 trading days
    ma_short: int = 25
    # Weekly trend approximation on daily data:
    # 10-week ~= 50 trading days, 20-week ~= 100 trading days.
    ma_mid: int = 50
    ma_long: int = 100
    ma_slope_lookback: int = 20
    momentum_windows: tuple = (20, 60, 120)
    momentum_weights: tuple = (0.5, 0.3, 0.2)
    # Entry-risk control to reduce chasing sharp short-term spikes.
    max_ret_5d: float = 0.12
    max_dist_ma60: float = 0.18
    max_atr_ratio: float = 0.08
    # Quality score weights (cross-sectional z-score mix).
    quality_w_momo: float = 0.40
    quality_w_trend: float = 0.30
    quality_w_vol: float = 0.20
    quality_w_liq: float = 0.10
    top_n: int = 15
    max_weight: float = 0.10
    stop_mode: str = "fixed"  # fixed | atr
    fixed_stop_loss: float = -0.08
    atr_mult: float = 2.5
    # Exit trend confirmation to reduce whipsaw.
    trend_exit_buffer: float = 0.01
    trend_exit_confirm_days: int = 3
    rank_exit_confirm_days: int = 5
    min_hold_days: int = 5


def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def add_features(price_df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    df = price_df.sort_values(["code", "date"]).copy()
    g = df.groupby("code", group_keys=False)

    df["adv20"] = g["trading_value"].transform(lambda s: s.rolling(20, min_periods=15).mean())
    df["adv60"] = g["trading_value"].transform(lambda s: s.rolling(60, min_periods=40).mean())

    min_short = max(10, int(cfg.ma_short * 0.67))
    min_mid = max(20, int(cfg.ma_mid * 0.67))
    min_long = max(40, int(cfg.ma_long * 0.67))
    df["ma_short"] = g["close"].transform(lambda s: s.rolling(cfg.ma_short, min_periods=min_short).mean())
    df["ma_mid"] = g["close"].transform(lambda s: s.rolling(cfg.ma_mid, min_periods=min_mid).mean())
    df["ma_long"] = g["close"].transform(lambda s: s.rolling(cfg.ma_long, min_periods=min_long).mean())
    df["ma_short_slope"] = g["ma_short"].transform(lambda s: s - s.shift(cfg.ma_slope_lookback))
    df["ma_mid_slope"] = g["ma_mid"].transform(lambda s: s - s.shift(cfg.ma_slope_lookback))
    df["ma_long_slope"] = g["ma_long"].transform(lambda s: s - s.shift(cfg.ma_slope_lookback))

    for window in cfg.momentum_windows:
        df[f"ret_{window}"] = g["close"].transform(lambda s: s / s.shift(window) - 1.0)
    df["ret_5"] = g["close"].transform(lambda s: s / s.shift(5) - 1.0)

    tr = g.apply(_true_range).reset_index(level=0, drop=True)
    df["atr20"] = tr.groupby(df["code"]).transform(lambda s: s.rolling(20, min_periods=14).mean())
    df["atr_ratio"] = df["atr20"] / df["close"]
    df["dist_ma_mid"] = df["close"] / df["ma_mid"] - 1.0

    df["next_close"] = g["close"].shift(-1)
    df["next_low"] = g["low"].shift(-1)
    df["ret_1d_fwd"] = df["next_close"] / df["close"] - 1.0

    w20, w60, w120 = cfg.momentum_weights
    df["momentum_score"] = (
        w20 * df["ret_20"].fillna(0.0)
        + w60 * df["ret_60"].fillna(0.0)
        + w120 * df["ret_120"].fillna(0.0)
    )
    df["trend_strength"] = (df["ma_short"] / df["ma_mid"] - 1.0) + (df["ma_mid"] / df["ma_long"] - 1.0)
    df["liq_strength"] = df["adv20"] / df["adv60"]

    df["adv20_pct_rank"] = df.groupby("date")["adv20"].rank(pct=True, method="average")
    # Cross-sectional z-score helper to rank better quality setups each day.
    for src, zc in [
        ("momentum_score", "z_momo"),
        ("trend_strength", "z_trend"),
        ("atr_ratio", "z_vol"),
        ("liq_strength", "z_liq"),
    ]:
        g = df.groupby("date")[src]
        mu = g.transform("mean")
        sd = g.transform("std").replace(0, np.nan)
        df[zc] = (df[src] - mu) / sd
        df[zc] = df[zc].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    df["quality_score"] = (
        cfg.quality_w_momo * df["z_momo"]
        + cfg.quality_w_trend * df["z_trend"]
        - cfg.quality_w_vol * df["z_vol"]  # lower vol is better
        + cfg.quality_w_liq * df["z_liq"]
    )
    return df


def _entry_condition(feature_df: pd.DataFrame, cfg: StrategyConfig, forward_col: str = "ret_1d_fwd") -> pd.Series:
    df = feature_df
    cond_liq = (
        (df["adv20"] >= cfg.liquidity_min_value)
        & (df["adv20_pct_rank"] >= (1.0 - cfg.liquidity_top_quantile))
        & (df["adv20"] / df["adv60"] >= cfg.liquidity_trend_ratio)
    )
    # Bullish 3-line weekly pattern: 5w > 10w > 20w and each trend slope positive.
    cond_trend = (
        (df["close"] > df["ma_short"])
        & (df["ma_short"] > df["ma_mid"])
        & (df["ma_mid"] > df["ma_long"])
        & (df["ma_short_slope"] > 0)
        & (df["ma_mid_slope"] > 0)
        & (df["ma_long_slope"] > 0)
    )
    cond_entry_risk = (
        (df["ret_5"] <= cfg.max_ret_5d)
        & (df["dist_ma_mid"] <= cfg.max_dist_ma60)
        & (df["atr_ratio"] <= cfg.max_atr_ratio)
    )
    return df["is_trading_day"] & cond_liq & cond_trend & cond_entry_risk & df[forward_col].notna()


def build_ranked_signals(feature_df: pd.DataFrame, cfg: StrategyConfig, forward_col: str = "ret_1d_fwd") -> pd.DataFrame:
    df = feature_df.copy()
    cond_base = _entry_condition(df, cfg, forward_col=forward_col)
    df["entry_ok"] = cond_base
    df["rank"] = np.nan
    ranked = df[cond_base].groupby("date")["quality_score"].rank(ascending=False, method="first")
    df.loc[cond_base, "rank"] = ranked
    return df


def pick_candidates(feature_df: pd.DataFrame, cfg: StrategyConfig, forward_col: str = "ret_1d_fwd") -> pd.DataFrame:
    df = feature_df.copy()
    selected = df[_entry_condition(df, cfg, forward_col=forward_col)].copy()
    selected["rank"] = selected.groupby("date")["momentum_score"].rank(ascending=False, method="first")
    selected = selected[selected["rank"] <= cfg.top_n].copy()
    return selected


def apply_stop_loss(
    selected_df: pd.DataFrame,
    cfg: StrategyConfig,
    ret_col: str = "ret_1d_fwd",
    low_col: str = "next_low",
) -> pd.Series:
    if cfg.stop_mode == "fixed":
        stop_pct = pd.Series(cfg.fixed_stop_loss, index=selected_df.index, dtype=float)
    elif cfg.stop_mode == "atr":
        stop_pct = -(cfg.atr_mult * selected_df["atr20"] / selected_df["close"])
        stop_pct = stop_pct.fillna(cfg.fixed_stop_loss)
    else:
        raise ValueError(f"Unsupported stop mode: {cfg.stop_mode}")

    breached = (selected_df[low_col] / selected_df["close"] - 1.0) <= stop_pct
    realized = selected_df[ret_col].copy()
    realized[breached] = stop_pct[breached]
    return realized
