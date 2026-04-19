from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from new_strategy.paths import data_path, output_path, strategy_output_path
from new_strategy.strategy_rules import StrategyConfig, add_features
from new_strategy.v2_ma_contract import normalize_v2_mode_contract_frame


EXCLUDED_SECURITY_CODES = {"005390"}
V2_OPTIMAL_MA_RAW_PATH = output_path("ma_breakout_research", "native_timeframe_close_returns_by_stock.csv")
V2_BEST_MODE_BY_STOCK_PATH = output_path("v2_four_timing_mode_grid", "best_mode_by_stock_full.csv")
SIGNAL_RESOLUTION_ORDER = {
    "SELL": 0,
    "BUY": 1,
    "SELL_WATCH": 2,
    "BUY_WATCH": 3,
    "WATCH": 4,
    "HOLD": 5,
}


FEATURE_COLUMNS = [
    "date",
    "code",
    "name",
    "market",
    "industry",
    "close",
    "open",
    "high",
    "low",
    "volume",
    "trading_value",
    "market_cap",
    "shares_outstanding",
    "is_trading_day",
    "adv20",
    "adv60",
    "adv20_pct_rank",
    "ma_short",
    "ma_mid",
    "ma_long",
    "ret_5",
    "ret_20",
    "ret_60",
    "ret_120",
    "atr20",
    "atr_ratio",
    "dist_ma_mid",
    "quality_score",
    "momentum_score",
    "trend_strength",
    "kospi",
    "vix",
    "usdkrw",
    "us10y",
    "kr10y",
    "gold_kr_close",
    "risk_count",
    "regime",
    "exposure",
    "filing_date_pti",
    "fiscal_year_pti",
    "reprt_code_pti",
    "revenue_pti",
    "op_income_pti",
    "net_income_pti",
    "op_margin_pti",
    "roe_simple_pti",
    "revenue_qoq_pti",
    "op_income_qoq_pti",
    "net_income_qoq_pti",
    "days_since_filing",
]


def dedupe_signal_rows(signal_df: pd.DataFrame) -> pd.DataFrame:
    if signal_df.empty or "code" not in signal_df.columns or "signal" not in signal_df.columns:
        return signal_df
    work = signal_df.copy()
    work["code"] = work["code"].astype(str).str.upper()
    work["code"] = work["code"].where(~work["code"].str.fullmatch(r"\d+"), work["code"].str.zfill(6))
    work["_signal_priority"] = work["signal"].astype(str).str.upper().map(SIGNAL_RESOLUTION_ORDER).fillna(99).astype(int)
    dedupe_cols = ["code"]
    sort_cols = ["_signal_priority", "code"]
    ascending = [True, True]
    if "date" in work.columns:
        work["_date_sort"] = pd.to_datetime(work["date"], errors="coerce")
        dedupe_cols = ["date", "code"]
        sort_cols = ["_date_sort", "_signal_priority", "code"]
        ascending = [False, True, True]
    work = work.sort_values(sort_cols, ascending=ascending, kind="stable")
    work = work.drop_duplicates(subset=dedupe_cols, keep="first")
    if "date" in work.columns:
        work = work.sort_values(["date", "code"], ascending=[True, True], kind="stable")
    return work.drop(columns=["_signal_priority", "_date_sort"], errors="ignore").reset_index(drop=True)


def sync_decision_summary(decision_df: pd.DataFrame, signal_df: pd.DataFrame) -> pd.DataFrame:
    if decision_df.empty or "date" not in decision_df.columns:
        return decision_df
    work = decision_df.copy()
    if signal_df.empty or "date" not in signal_df.columns or "signal" not in signal_df.columns or "code" not in signal_df.columns:
        return work

    signals = signal_df.copy()
    signals["date"] = pd.to_datetime(signals["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    signals["code"] = signals["code"].astype(str).str.upper()
    signals["code"] = signals["code"].where(~signals["code"].str.fullmatch(r"\d+"), signals["code"].str.zfill(6))
    signals["signal"] = signals["signal"].astype(str).str.upper()
    signals = signals.dropna(subset=["date"])
    if signals.empty:
        return work

    grouped: dict[str, dict[str, list[str]]] = {}
    for dt, group in signals.groupby("date"):
        grouped[str(dt)] = {
            "BUY": group.loc[group["signal"] == "BUY", "code"].astype(str).drop_duplicates().tolist(),
            "SELL": group.loc[group["signal"] == "SELL", "code"].astype(str).drop_duplicates().tolist(),
            "HOLD": group.loc[group["signal"] == "HOLD", "code"].astype(str).drop_duplicates().tolist(),
            "WATCH": group.loc[group["signal"] == "WATCH", "code"].astype(str).drop_duplicates().tolist(),
        }

    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["_date_key"] = work["date"].dt.strftime("%Y-%m-%d")

    for idx, row in work.iterrows():
        bucket = grouped.get(str(row["_date_key"]))
        if not bucket:
            continue
        buy_codes = bucket["BUY"]
        sell_codes = bucket["SELL"]
        hold_codes = bucket["HOLD"]
        watch_codes = bucket["WATCH"]
        work.at[idx, "buy_count"] = len(buy_codes)
        work.at[idx, "sell_count"] = len(sell_codes)
        work.at[idx, "hold_count"] = len(hold_codes)
        work.at[idx, "watch_count"] = len(watch_codes)
        work.at[idx, "buy_codes"] = ",".join(buy_codes)
        work.at[idx, "sell_codes"] = ",".join(sell_codes)
        work.at[idx, "watch_codes"] = ",".join(watch_codes)
        regime = row.get("market_regime", "unknown")
        exposure = float(row.get("exposure", 1.0) or 1.0)
        work.at[idx, "summary_text"] = (
            f"regime={regime}, exposure={exposure:.2f}, "
            f"buy={len(buy_codes)}, sell={len(sell_codes)}, hold={len(hold_codes)}, watch={len(watch_codes)}"
        )

    return work.drop(columns=["_date_key"], errors="ignore")

FUND_RENAME = {
    "종목코드": "code",
    "법인코드": "corp_code",
    "법인명": "corp_name",
    "사업연도": "bsns_year",
    "보고서코드": "reprt_code",
    "접수번호": "rcept_no",
    "공시일": "filing_date",
    "매출액": "revenue_cum",
    "영업이익": "op_income_cum",
    "당기순이익": "net_income_cum",
    "자산총계": "total_assets",
    "자본총계": "total_equity",
    "부채총계": "total_liab",
    "기간": "period",
    "영업이익률": "op_margin_cum",
    "ROE(단순)": "roe_simple_cum",
    "분기매출액": "revenue_q",
    "분기영업이익": "op_income_q",
    "분기당기순이익": "net_income_q",
    "분기영업이익률": "op_margin_q",
    "분기ROE(단순)": "roe_simple_q",
}

QUARTER_ORDER = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}


@dataclass
class EarningsStrategyConfig:
    strategy_id: str = "earnings_pti_v2"
    trend_mode: str = "optimal_ma_v2"
    min_adv20: float = 1_000_000_000.0
    recent_filing_days: int = 90
    watchlist_size: int = 12
    max_positions: int = 8
    min_hold_days: int = 10
    max_holding_days: int = 90
    fixed_stop_loss: float = -0.10
    max_ret_5: float = 0.12
    max_atr_ratio: float = 0.10
    max_dist_ma_mid: float = 0.18
    neutral_target_ratio: float = 0.50
    riskoff_target_ratio: float = 0.00
    buy_threshold: float = 0.72
    watch_threshold: float = 0.58
    sell_threshold: float = 0.35
    min_timing_score: float = 0.45
    pre_signal_threshold: float = 0.66
    research_min_obs: int = 80
    ml_backend: str = "auto"
    ml_train_window_days: int = 756
    ml_horizon_days: int = 60
    riskoff_exposure_cutoff: float = 0.20
    daily_ma_window: int = 20
    weekly_ma_window: int = 10
    monthly_ma_window: int = 10
    monthly_buy_threshold: float = 0.00
    weekly_sell_threshold: float = -0.05


def _clip_z(series: pd.Series, lower: float = -5.0, upper: float = 5.0) -> pd.Series:
    return series.replace([np.inf, -np.inf], np.nan).clip(lower=lower, upper=upper)


def _zscore_by_date(df: pd.DataFrame, column: str, new_col: str) -> pd.DataFrame:
    grp = df.groupby("date")[column]
    mu = grp.transform("mean")
    sd = grp.transform("std").replace(0, np.nan)
    df[new_col] = ((df[column] - mu) / sd).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df[new_col] = _clip_z(df[new_col])
    return df


def _bool_score(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(float)


def _ma_min_periods(window: int, *, floor: int = 5) -> int:
    return min(window, max(1, max(floor, int(np.ceil(window * 0.6)))))


def _optimal_ma_sort_values(df: pd.DataFrame) -> pd.DataFrame:
    ranked = df.copy()
    ranked["ma_window"] = pd.to_numeric(ranked["ma_window"], errors="coerce")
    ranked["total_return"] = pd.to_numeric(ranked["total_return"], errors="coerce")
    ranked["max_drawdown"] = pd.to_numeric(ranked["max_drawdown"], errors="coerce")
    ranked["completed_trade_count"] = pd.to_numeric(ranked["completed_trade_count"], errors="coerce")
    ranked["annualized_return"] = pd.to_numeric(ranked["annualized_return"], errors="coerce")
    ranked["win_rate"] = pd.to_numeric(ranked["win_rate"], errors="coerce")
    return ranked


def load_v2_optimal_ma_pairs(path: Path = V2_OPTIMAL_MA_RAW_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["code", "v2_month_window", "v2_week_window"])
    df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    if df.empty:
        return pd.DataFrame(columns=["code", "v2_month_window", "v2_week_window"])
    df["code"] = df["code"].astype(str).str.zfill(6)
    df = df.loc[df["action_mode"].astype(str).str.lower() == "native_timeframe_close"].copy()
    df = df.loc[df["ma_timeframe"].astype(str).str.lower().isin(["monthly", "weekly"])].copy()
    df = df.loc[pd.to_numeric(df["ma_window"], errors="coerce").ge(2)].copy()
    if df.empty:
        return pd.DataFrame(columns=["code", "v2_month_window", "v2_week_window"])

    ranked = _optimal_ma_sort_values(df).sort_values(
        [
            "code",
            "ma_timeframe",
            "total_return",
            "max_drawdown",
            "completed_trade_count",
            "annualized_return",
            "win_rate",
            "ma_window",
        ],
        ascending=[True, True, False, False, False, False, False, True],
    )
    selected = ranked.groupby(["code", "ma_timeframe"], as_index=False).head(1).reset_index(drop=True)
    pivot = (
        selected.pivot(index="code", columns="ma_timeframe", values="ma_window")
        .rename(columns={"monthly": "v2_month_window", "weekly": "v2_week_window"})
        .reset_index()
    )
    for col in ["v2_month_window", "v2_week_window"]:
        if col in pivot.columns:
            pivot[col] = pd.to_numeric(pivot[col], errors="coerce")
    return pivot


def load_v2_mode_contract_pairs(
    best_mode_path: Path = V2_BEST_MODE_BY_STOCK_PATH,
    base_path: Path = V2_OPTIMAL_MA_RAW_PATH,
) -> pd.DataFrame:
    base = load_v2_optimal_ma_pairs(base_path)
    columns = [
        "code",
        "v2_month_window",
        "v2_week_window",
        "v2_contract_mode",
        "v2_buy_timeframe",
        "v2_sell_timeframe",
        "v2_buy_window",
        "v2_sell_window",
    ]
    if best_mode_path.exists():
        contract = pd.read_csv(best_mode_path, dtype={"code": str}, low_memory=False)
        if not contract.empty:
            contract["code"] = contract["code"].astype(str).str.zfill(6)
            contract = normalize_v2_mode_contract_frame(contract)
            contract = contract[
                [
                    "code",
                    "v2_contract_mode",
                    "v2_buy_timeframe",
                    "v2_sell_timeframe",
                    "v2_buy_window",
                    "v2_sell_window",
                ]
            ].drop_duplicates(subset=["code"], keep="last")
        else:
            contract = pd.DataFrame(columns=[c for c in columns if c not in {"v2_month_window", "v2_week_window"}])
    else:
        contract = pd.DataFrame(columns=[c for c in columns if c not in {"v2_month_window", "v2_week_window"}])

    if base.empty and contract.empty:
        return pd.DataFrame(columns=columns)
    if base.empty:
        out = contract.copy()
        out["v2_month_window"] = np.nan
        out["v2_week_window"] = np.nan
    elif contract.empty:
        out = base.copy()
    else:
        out = base.merge(contract, on="code", how="outer")

    out["code"] = out["code"].astype(str).str.zfill(6)
    out["v2_buy_timeframe"] = (
        out["v2_buy_timeframe"].astype("string").str.strip().str.lower().replace({"": pd.NA, "nan": pd.NA, "none": pd.NA})
    )
    out["v2_sell_timeframe"] = (
        out["v2_sell_timeframe"].astype("string").str.strip().str.lower().replace({"": pd.NA, "nan": pd.NA, "none": pd.NA})
    )
    out["v2_buy_timeframe"] = out["v2_buy_timeframe"].fillna("monthly")
    out["v2_sell_timeframe"] = out["v2_sell_timeframe"].fillna("weekly")
    out["v2_buy_window"] = pd.to_numeric(out.get("v2_buy_window"), errors="coerce")
    out["v2_sell_window"] = pd.to_numeric(out.get("v2_sell_window"), errors="coerce")
    out["v2_month_window"] = pd.to_numeric(out.get("v2_month_window"), errors="coerce")
    out["v2_week_window"] = pd.to_numeric(out.get("v2_week_window"), errors="coerce")
    buy_month_mask = out["v2_buy_timeframe"].eq("monthly")
    sell_month_mask = out["v2_sell_timeframe"].eq("monthly")
    buy_month_fill_mask = buy_month_mask & out["v2_buy_window"].isna()
    buy_week_fill_mask = (~buy_month_mask) & out["v2_buy_window"].isna()
    sell_month_fill_mask = sell_month_mask & out["v2_sell_window"].isna()
    sell_week_fill_mask = (~sell_month_mask) & out["v2_sell_window"].isna()
    out.loc[buy_month_fill_mask, "v2_buy_window"] = out.loc[buy_month_fill_mask, "v2_month_window"]
    out.loc[buy_week_fill_mask, "v2_buy_window"] = out.loc[buy_week_fill_mask, "v2_week_window"]
    out.loc[sell_month_fill_mask, "v2_sell_window"] = out.loc[sell_month_fill_mask, "v2_month_window"]
    out.loc[sell_week_fill_mask, "v2_sell_window"] = out.loc[sell_week_fill_mask, "v2_week_window"]
    out["v2_contract_mode"] = out["v2_contract_mode"].astype("string").str.strip().str.lower()
    out["v2_contract_mode"] = out["v2_contract_mode"].replace({"": pd.NA, "nan": pd.NA, "none": pd.NA})
    out["v2_contract_mode"] = out["v2_contract_mode"].fillna(
        out["v2_buy_timeframe"].astype(str) + "_buy_" + out["v2_sell_timeframe"].astype(str) + "_sell"
    )
    return out[columns].drop_duplicates(subset=["code"], keep="last").reset_index(drop=True)


def _merge_variable_period_state(
    frame: pd.DataFrame,
    *,
    period_alias: str,
    window_map: dict[str, int],
    prefix: str,
) -> pd.DataFrame:
    merged_parts: List[pd.DataFrame] = []
    base_df = frame.sort_values(["code", "date"]).reset_index(drop=True)

    for code, grp in base_df.groupby("code", sort=False):
        window = int(window_map.get(str(code).zfill(6), 0) or 0)
        block = grp.copy()
        block[f"{prefix}_window"] = np.nan if window < 2 else float(window)
        block[f"{prefix}_close"] = np.nan
        block[f"{prefix}_ma"] = np.nan
        block[f"{prefix}_period_dist"] = np.nan
        block[f"{prefix}_period_above"] = False
        block[f"{prefix}_prev_period_dist"] = np.nan
        block[f"{prefix}_prev_period_above"] = False
        block[f"{prefix}_live_dist"] = np.nan
        if window < 2:
            merged_parts.append(block)
            continue

        period_key = grp["date"].dt.to_period(period_alias)
        period_state = (
            grp.assign(_period_key=period_key)
            .groupby("_period_key", as_index=False)
            .agg(state_date=("date", "max"), state_close=("close", "last"))
        )
        period_state[f"{prefix}_close"] = period_state["state_close"]
        period_state[f"{prefix}_ma"] = period_state["state_close"].rolling(
            window,
            min_periods=_ma_min_periods(window),
        ).mean()
        period_state[f"{prefix}_period_dist"] = period_state["state_close"] / period_state[f"{prefix}_ma"] - 1.0
        period_state[f"{prefix}_period_above"] = period_state[f"{prefix}_period_dist"] >= 0.0
        period_state[f"{prefix}_prev_period_dist"] = period_state[f"{prefix}_period_dist"].shift(1)
        period_state[f"{prefix}_prev_period_above"] = period_state[f"{prefix}_period_above"].shift(1).fillna(False)

        block = pd.merge_asof(
            grp.sort_values("date").reset_index(drop=True),
            period_state[
                [
                    "state_date",
                    f"{prefix}_close",
                    f"{prefix}_ma",
                    f"{prefix}_period_dist",
                    f"{prefix}_period_above",
                    f"{prefix}_prev_period_dist",
                    f"{prefix}_prev_period_above",
                ]
            ],
            left_on="date",
            right_on="state_date",
            direction="backward",
            allow_exact_matches=True,
        ).drop(columns=["state_date"], errors="ignore")
        block[f"{prefix}_window"] = float(window)
        block[f"{prefix}_live_dist"] = block["close"] / block[f"{prefix}_ma"] - 1.0
        merged_parts.append(block)

    return pd.concat(merged_parts, ignore_index=True)


def _build_period_state(grp: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    tf = str(timeframe or "").strip().lower()
    if tf == "daily":
        return grp[["date", "close"]].rename(columns={"date": "state_date", "close": "state_close"}).copy()
    if tf == "weekly":
        return (
            grp.assign(_period_key=grp["date"].dt.to_period("W-FRI"))
            .groupby("_period_key", as_index=False)
            .agg(state_date=("date", "max"), state_close=("close", "last"))
        )
    return (
        grp.assign(_period_key=grp["date"].dt.to_period("M"))
        .groupby("_period_key", as_index=False)
        .agg(state_date=("date", "max"), state_close=("close", "last"))
    )


def _merge_contract_period_state(
    frame: pd.DataFrame,
    *,
    timeframe_map: dict[str, str],
    window_map: dict[str, int],
    prefix: str,
) -> pd.DataFrame:
    merged_parts: List[pd.DataFrame] = []
    base_df = frame.sort_values(["code", "date"]).reset_index(drop=True)

    for code, grp in base_df.groupby("code", sort=False):
        code_key = str(code).zfill(6)
        timeframe = str(timeframe_map.get(code_key, "") or "").strip().lower()
        window = int(window_map.get(code_key, 0) or 0)
        block = grp.copy()
        block[f"{prefix}_window"] = np.nan if window < 2 else float(window)
        block[f"{prefix}_timeframe"] = timeframe or pd.NA
        block[f"{prefix}_close"] = np.nan
        block[f"{prefix}_ma"] = np.nan
        block[f"{prefix}_period_dist"] = np.nan
        block[f"{prefix}_period_above"] = False
        block[f"{prefix}_prev_period_dist"] = np.nan
        block[f"{prefix}_prev_period_above"] = False
        block[f"{prefix}_live_dist"] = np.nan
        if window < 2 or timeframe not in {"daily", "weekly", "monthly"}:
            merged_parts.append(block)
            continue

        period_state = _build_period_state(grp, timeframe)
        period_state[f"{prefix}_close"] = period_state["state_close"]
        period_state[f"{prefix}_ma"] = period_state["state_close"].rolling(
            window,
            min_periods=_ma_min_periods(window),
        ).mean()
        period_state[f"{prefix}_period_dist"] = period_state["state_close"] / period_state[f"{prefix}_ma"] - 1.0
        period_state[f"{prefix}_period_above"] = period_state[f"{prefix}_period_dist"] >= 0.0
        period_state[f"{prefix}_prev_period_dist"] = period_state[f"{prefix}_period_dist"].shift(1)
        period_state[f"{prefix}_prev_period_above"] = period_state[f"{prefix}_period_above"].shift(1).fillna(False)

        block = pd.merge_asof(
            grp.sort_values("date").reset_index(drop=True),
            period_state[
                [
                    "state_date",
                    f"{prefix}_close",
                    f"{prefix}_ma",
                    f"{prefix}_period_dist",
                    f"{prefix}_period_above",
                    f"{prefix}_prev_period_dist",
                    f"{prefix}_prev_period_above",
                ]
            ],
            left_on="date",
            right_on="state_date",
            direction="backward",
            allow_exact_matches=True,
        ).drop(columns=["state_date"], errors="ignore")
        block[f"{prefix}_window"] = float(window)
        block[f"{prefix}_timeframe"] = timeframe
        block[f"{prefix}_live_dist"] = block["close"] / block[f"{prefix}_ma"] - 1.0
        merged_parts.append(block)

    return pd.concat(merged_parts, ignore_index=True)


def add_v2_optimal_ma_features(frame: pd.DataFrame, cfg: EarningsStrategyConfig) -> pd.DataFrame:
    # `sort_values(...).reset_index(...)` already returns a new frame. Copying a
    # 2M+ row panel again can trigger avoidable memory spikes during daily EOD runs.
    df = frame.sort_values(["code", "date"]).reset_index(drop=True)
    selection = load_v2_mode_contract_pairs()
    if selection.empty:
        df["v2_contract_mode"] = pd.NA
        df["v2_buy_timeframe"] = pd.NA
        df["v2_sell_timeframe"] = pd.NA
        df["v2_buy_window"] = np.nan
        df["v2_sell_window"] = np.nan
        df["v2_month_window"] = np.nan
        df["v2_week_window"] = np.nan
        df["v2_month_close"] = np.nan
        df["v2_month_ma"] = np.nan
        df["v2_month_period_dist"] = np.nan
        df["v2_month_period_above"] = False
        df["v2_month_prev_period_dist"] = np.nan
        df["v2_month_prev_period_above"] = False
        df["v2_month_live_dist"] = np.nan
        df["v2_week_close"] = np.nan
        df["v2_week_ma"] = np.nan
        df["v2_week_period_dist"] = np.nan
        df["v2_week_period_above"] = False
        df["v2_week_prev_period_dist"] = np.nan
        df["v2_week_prev_period_above"] = False
        df["v2_week_live_dist"] = np.nan
        df["v2_month_buy_ready"] = False
        df["v2_month_prev_ready"] = False
        df["v2_month_buy_cross"] = False
        df["v2_month_above_maintain"] = False
        df["v2_month_sell_cross"] = False
        df["v2_week_sell_trigger"] = False
        df["v2_week_sell_watch"] = False
        df["v2_buy_close"] = np.nan
        df["v2_buy_ma"] = np.nan
        df["v2_buy_period_dist"] = np.nan
        df["v2_buy_period_above"] = False
        df["v2_buy_prev_period_dist"] = np.nan
        df["v2_buy_prev_period_above"] = False
        df["v2_buy_live_dist"] = np.nan
        df["v2_buy_ready"] = False
        df["v2_buy_prev_ready"] = False
        df["v2_buy_cross"] = False
        df["v2_buy_above_maintain"] = False
        df["v2_buy_sell_cross"] = False
        df["v2_sell_close"] = np.nan
        df["v2_sell_ma"] = np.nan
        df["v2_sell_period_dist"] = np.nan
        df["v2_sell_period_above"] = False
        df["v2_sell_prev_period_dist"] = np.nan
        df["v2_sell_prev_period_above"] = False
        df["v2_sell_live_dist"] = np.nan
        df["v2_sell_trigger"] = False
        df["v2_sell_watch"] = False
        return df

    selection["code"] = selection["code"].astype(str).str.zfill(6)
    df = df.merge(
        selection[
            [
                "code",
                "v2_contract_mode",
                "v2_buy_timeframe",
                "v2_sell_timeframe",
                "v2_buy_window",
                "v2_sell_window",
                "v2_month_window",
                "v2_week_window",
            ]
        ],
        on="code",
        how="left",
    )
    window_map_month = selection.set_index("code")["v2_month_window"].dropna().astype(int).to_dict()
    window_map_week = selection.set_index("code")["v2_week_window"].dropna().astype(int).to_dict()

    df = _merge_variable_period_state(df, period_alias="M", window_map=window_map_month, prefix="v2_month")
    df = _merge_variable_period_state(df, period_alias="W-FRI", window_map=window_map_week, prefix="v2_week")
    buy_timeframe_map = (
        selection.dropna(subset=["v2_buy_timeframe"])
        .set_index("code")["v2_buy_timeframe"]
        .astype(str)
        .str.lower()
        .to_dict()
    )
    sell_timeframe_map = (
        selection.dropna(subset=["v2_sell_timeframe"])
        .set_index("code")["v2_sell_timeframe"]
        .astype(str)
        .str.lower()
        .to_dict()
    )
    buy_window_map = selection.set_index("code")["v2_buy_window"].dropna().astype(int).to_dict()
    sell_window_map = selection.set_index("code")["v2_sell_window"].dropna().astype(int).to_dict()
    df = _merge_contract_period_state(df, timeframe_map=buy_timeframe_map, window_map=buy_window_map, prefix="v2_buy")
    df = _merge_contract_period_state(df, timeframe_map=sell_timeframe_map, window_map=sell_window_map, prefix="v2_sell")
    df["v2_month_buy_ready"] = df["v2_month_period_dist"] >= cfg.monthly_buy_threshold
    df["v2_month_prev_ready"] = df["v2_month_prev_period_dist"] >= cfg.monthly_buy_threshold
    df["v2_month_buy_cross"] = df["v2_month_buy_ready"] & (~df["v2_month_prev_ready"].fillna(False))
    df["v2_month_above_maintain"] = df["v2_month_buy_ready"] & df["v2_month_prev_ready"].fillna(False)
    df["v2_month_sell_cross"] = (~df["v2_month_buy_ready"]) & df["v2_month_prev_ready"].fillna(False)
    df["v2_week_sell_trigger"] = df["v2_week_period_dist"] <= cfg.weekly_sell_threshold
    df["v2_week_sell_watch"] = (
        df["v2_week_period_dist"].gt(cfg.weekly_sell_threshold)
        & df["v2_week_period_dist"].lt(0.0)
    )
    df["v2_buy_ready"] = df["v2_buy_period_dist"] >= cfg.monthly_buy_threshold
    df["v2_buy_prev_ready"] = df["v2_buy_prev_period_dist"] >= cfg.monthly_buy_threshold
    df["v2_buy_cross"] = df["v2_buy_ready"] & (~df["v2_buy_prev_ready"].fillna(False))
    df["v2_buy_above_maintain"] = df["v2_buy_ready"] & df["v2_buy_prev_ready"].fillna(False)
    df["v2_buy_sell_cross"] = (~df["v2_buy_ready"]) & df["v2_buy_prev_ready"].fillna(False)
    df["v2_sell_trigger"] = df["v2_sell_period_dist"] <= cfg.weekly_sell_threshold
    df["v2_sell_watch"] = (
        df["v2_sell_period_dist"].gt(cfg.weekly_sell_threshold)
        & df["v2_sell_period_dist"].lt(0.0)
    )
    return df


def _merge_period_state(
    frame: pd.DataFrame,
    *,
    period_alias: str,
    window: int,
    prefix: str,
) -> pd.DataFrame:
    state_parts: List[pd.DataFrame] = []
    for code, grp in frame[["code", "date", "close"]].dropna().sort_values(["code", "date"]).groupby("code", sort=False):
        period_key = grp["date"].dt.to_period(period_alias)
        period_state = (
            grp.assign(_period_key=period_key)
            .groupby("_period_key", as_index=False)
            .agg(state_date=("date", "max"), state_close=("close", "last"))
        )
        period_state[f"{prefix}_close"] = period_state["state_close"]
        period_state[f"{prefix}_ma"] = period_state["state_close"].rolling(
            window,
            min_periods=_ma_min_periods(window),
        ).mean()
        period_state[f"{prefix}_above"] = period_state["state_close"] >= period_state[f"{prefix}_ma"]
        period_state["code"] = code
        state_parts.append(
            period_state[
                ["code", "state_date", f"{prefix}_close", f"{prefix}_ma", f"{prefix}_above"]
            ]
        )

    if not state_parts:
        frame[f"{prefix}_close"] = np.nan
        frame[f"{prefix}_ma"] = np.nan
        frame[f"{prefix}_above"] = False
        return frame

    state_df = pd.concat(state_parts, ignore_index=True)
    merged_parts: List[pd.DataFrame] = []
    base_df = frame.sort_values(["code", "date"]).reset_index(drop=True)
    for code, grp in base_df.groupby("code", sort=False):
        right = state_df.loc[state_df["code"] == code].sort_values("state_date").reset_index(drop=True)
        if right.empty:
            block = grp.copy()
            block[f"{prefix}_close"] = np.nan
            block[f"{prefix}_ma"] = np.nan
            block[f"{prefix}_above"] = False
        else:
            block = pd.merge_asof(
                grp.sort_values("date").reset_index(drop=True),
                right,
                left_on="date",
                right_on="state_date",
                direction="backward",
                allow_exact_matches=True,
            ).drop(columns=["state_date", "code_y"], errors="ignore")
            if "code_x" in block.columns:
                block = block.rename(columns={"code_x": "code"})
        merged_parts.append(block)
    return pd.concat(merged_parts, ignore_index=True)


def add_multi_timeframe_ma_features(frame: pd.DataFrame, cfg: EarningsStrategyConfig) -> pd.DataFrame:
    df = frame.sort_values(["code", "date"]).reset_index(drop=True).copy()
    daily_min_periods = _ma_min_periods(cfg.daily_ma_window, floor=10)
    df["ma_day_20"] = df.groupby("code", sort=False)["close"].transform(
        lambda s: s.rolling(cfg.daily_ma_window, min_periods=daily_min_periods).mean()
    )
    df["dist_ma_day_20"] = df["close"] / df["ma_day_20"] - 1.0

    trend_mode = str(cfg.trend_mode or "optimal_ma_v2").strip().lower()
    if trend_mode == "optimal_ma_v2":
        df = add_v2_optimal_ma_features(df, cfg)
        df["week_10_ma"] = df["v2_week_ma"]
        df["week_10_above"] = df["v2_week_period_above"].fillna(False)
        df["month_10_ma"] = df["v2_month_ma"]
        df["month_10_above"] = df["v2_month_period_above"].fillna(False)
        df["weekly_aux_ok"] = (~df["v2_sell_trigger"]).fillna(False)
        df["monthly_main_ok"] = df["v2_buy_ready"].fillna(False)
        df["dist_month_10"] = df["v2_buy_live_dist"]
    else:
        df = _merge_period_state(
            df,
            period_alias="W-FRI",
            window=cfg.weekly_ma_window,
            prefix="week_10",
        )
        df = _merge_period_state(
            df,
            period_alias="M",
            window=cfg.monthly_ma_window,
            prefix="month_10",
        )
        df["weekly_aux_ok"] = df["week_10_above"].fillna(False)
        df["monthly_main_ok"] = df["month_10_above"].fillna(False)
        df["dist_month_10"] = df["close"] / df["month_10_ma"] - 1.0
    return df


def _apply_trend_logic(df: pd.DataFrame, cfg: EarningsStrategyConfig, *, include_ml: bool) -> pd.DataFrame:
    buy_ready = df.get("v2_buy_ready", df.get("v2_month_buy_ready", pd.Series(False, index=df.index))).fillna(False)
    buy_new_cross = df.get("v2_buy_cross", df.get("v2_month_buy_cross", pd.Series(False, index=df.index))).fillna(False)
    sell_exit = df.get("v2_sell_trigger", df.get("v2_week_sell_trigger", pd.Series(False, index=df.index))).fillna(False)
    sell_watch = df.get("v2_sell_watch", df.get("v2_week_sell_watch", pd.Series(False, index=df.index))).fillna(False)
    df["timing_ok"] = buy_ready & (~sell_exit)
    df["timing_score"] = (
        0.70 * _bool_score(buy_ready)
        + 0.30 * _bool_score(~sell_exit)
    )
    df["watch_candidate"] = df["core_candidate"] & buy_ready & (~sell_exit)
    # V2 MA-only contract: entries/exits are driven by optimal MA state only.
    df["buy_candidate"] = df["watch_candidate"] & buy_new_cross & (~sell_watch)
    df["sell_candidate"] = sell_exit
    # Keep schema-compatible columns, but do not use score for any decision path.
    df["conviction_score"] = np.nan
    df["conviction_raw"] = df["conviction_score"]
    return df


def _format_amount(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    abs_value = abs(float(value))
    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}조"
    if abs_value >= 100_000_000:
        return f"{value / 100_000_000:.1f}억"
    if abs_value >= 10_000:
        return f"{value / 10_000:.0f}만"
    return f"{value:,.0f}"


def _supported_ml_backend(config_backend: str) -> str:
    if config_backend and config_backend not in {"auto", "none"}:
        return config_backend
    if importlib.util.find_spec("lightgbm"):
        return "lightgbm"
    if importlib.util.find_spec("xgboost"):
        return "xgboost"
    if importlib.util.find_spec("sklearn"):
        return "sklearn_rf"
    return "none"


def load_feature_dataset(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype={"code": str}, usecols=lambda c: c in FEATURE_COLUMNS, low_memory=False)
    else:
        df = pd.read_pickle(path)
        cols = [c for c in FEATURE_COLUMNS if c in df.columns]
        df = df[cols]
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "filing_date_pti" in df.columns:
        df["filing_date_pti"] = pd.to_datetime(df["filing_date_pti"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values(["code", "date"]).reset_index(drop=True)


def _sanitize_price_ohlc_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for col in ["close", "open", "high", "low"]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["close"] = out["close"].where(np.isfinite(out["close"]) & (out["close"] > 0))
    out["open"] = out["open"].where(np.isfinite(out["open"]) & (out["open"] > 0)).combine_first(out["close"])
    valid_high = out["high"].where(np.isfinite(out["high"]) & (out["high"] > 0))
    valid_low = out["low"].where(np.isfinite(out["low"]) & (out["low"] > 0))
    out["high"] = pd.concat([valid_high, out["open"], out["close"]], axis=1).max(axis=1, skipna=True)
    out["low"] = pd.concat([valid_low, out["open"], out["close"]], axis=1).min(axis=1, skipna=True)
    out["close"] = out["close"].combine_first(out["open"])
    out["open"] = out["open"].combine_first(out["close"])
    return out.dropna(subset=["close", "open", "high", "low"])


def load_live_quotes(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["date", "code", "close", "open", "high", "low", "volume", "trading_value", "quote_time"])

    if path.suffix.lower() == ".xlsx":
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, low_memory=False)

    rename_map = {
        "종목코드": "code",
        "code": "code",
        "date": "date",
        "일자": "date",
        "현재가": "close",
        "close": "close",
        "시가": "open",
        "open": "open",
        "고가": "high",
        "high": "high",
        "저가": "low",
        "low": "low",
        "거래량": "volume",
        "volume": "volume",
        "거래대금": "trading_value",
        "trading_value": "trading_value",
        "quote_time": "quote_time",
        "체결시각": "quote_time",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    required = {"code", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"live quote file missing columns: {sorted(required - set(df.columns))}")

    if "date" not in df.columns:
        df["date"] = pd.Timestamp.today().normalize()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df["code"] = df["code"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
    for col in ["close", "open", "high", "low", "volume", "trading_value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = np.nan
    df = _sanitize_price_ohlc_frame(df)
    if "quote_time" not in df.columns:
        df["quote_time"] = pd.NaT
    else:
        df["quote_time"] = pd.to_datetime(df["quote_time"], errors="coerce")
    df = df.dropna(subset=["date", "code", "close"]).sort_values(["code", "date", "quote_time"])
    return df.drop_duplicates(["code", "date"], keep="last").reset_index(drop=True)


def _macro_snapshot_by_date(feature_df: pd.DataFrame) -> pd.DataFrame:
    macro_cols = [
        "date",
        "kospi",
        "vix",
        "usdkrw",
        "us10y",
        "kr10y",
        "gold_kr_close",
        "risk_count",
        "regime",
        "exposure",
    ]
    keep = [c for c in macro_cols if c in feature_df.columns]
    return feature_df[keep].drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def build_live_feature_history(feature_df: pd.DataFrame, live_quotes_path: Path) -> Tuple[pd.DataFrame, bool]:
    quotes = load_live_quotes(live_quotes_path)
    if quotes.empty:
        return feature_df.sort_values(["code", "date"]).reset_index(drop=True), False

    raw_cols = [
        "date",
        "code",
        "name",
        "market",
        "industry",
        "close",
        "open",
        "high",
        "low",
        "volume",
        "trading_value",
        "market_cap",
        "shares_outstanding",
        "is_trading_day",
    ]
    raw = feature_df[[c for c in raw_cols if c in feature_df.columns]].copy()
    latest_date = raw["date"].max()
    quote_date = quotes["date"].max()

    if quote_date == latest_date:
        base_history = raw.loc[raw["date"] < latest_date].copy()
        seed = raw.loc[raw["date"] == latest_date].sort_values(["code", "date"]).drop_duplicates("code", keep="last").copy()
    else:
        base_history = raw.copy()
        seed = raw.sort_values(["code", "date"]).groupby("code", as_index=False).tail(1).copy()

    seed["date"] = quote_date
    seed["is_trading_day"] = True

    merged = seed.merge(
        quotes[["code", "close", "open", "high", "low", "volume", "trading_value"]],
        on="code",
        how="left",
        suffixes=("", "_live"),
    )
    prev_close = merged["close"]
    base_close = pd.to_numeric(merged["close"], errors="coerce")
    base_open = pd.to_numeric(merged["open"], errors="coerce")
    base_high = pd.to_numeric(merged["high"], errors="coerce")
    base_low = pd.to_numeric(merged["low"], errors="coerce")
    live_close = pd.to_numeric(merged["close_live"], errors="coerce")
    live_open = pd.to_numeric(merged["open_live"], errors="coerce")
    live_high = pd.to_numeric(merged["high_live"], errors="coerce")
    live_low = pd.to_numeric(merged["low_live"], errors="coerce")

    base_close = base_close.where(np.isfinite(base_close) & (base_close > 0))
    base_open = base_open.where(np.isfinite(base_open) & (base_open > 0))
    base_high = base_high.where(np.isfinite(base_high) & (base_high > 0))
    base_low = base_low.where(np.isfinite(base_low) & (base_low > 0))
    live_close = live_close.where(np.isfinite(live_close) & (live_close > 0))
    live_open = live_open.where(np.isfinite(live_open) & (live_open > 0))
    live_high = live_high.where(np.isfinite(live_high) & (live_high > 0))
    live_low = live_low.where(np.isfinite(live_low) & (live_low > 0))

    merged["close"] = live_close.combine_first(base_close)
    merged["open"] = live_open.combine_first(base_open).combine_first(prev_close).combine_first(merged["close"])
    merged["high"] = pd.concat(
        [live_high.combine_first(base_high), merged["open"], merged["close"], prev_close],
        axis=1,
    ).max(axis=1, skipna=True)
    merged["low"] = pd.concat(
        [live_low.combine_first(base_low), merged["open"], merged["close"], prev_close],
        axis=1,
    ).min(axis=1, skipna=True)
    merged["volume"] = merged["volume_live"].combine_first(merged["volume"])
    merged["trading_value"] = merged["trading_value_live"].combine_first(merged["trading_value"])
    drop_live = [c for c in merged.columns if c.endswith("_live")]
    merged = merged.drop(columns=drop_live)

    enriched = add_features(
        pd.concat([base_history, merged], ignore_index=True).sort_values(["code", "date"]).reset_index(drop=True),
        StrategyConfig(),
    )
    current = enriched.loc[enriched["date"] == quote_date].copy()
    macro_snapshot = _macro_snapshot_by_date(feature_df)
    enriched = pd.merge_asof(
        enriched.sort_values("date"),
        macro_snapshot.sort_values("date"),
        on="date",
        direction="backward",
        allow_exact_matches=True,
    )
    return enriched.sort_values(["code", "date"]).reset_index(drop=True), True


def build_live_feature_overlay(feature_df: pd.DataFrame, live_quotes_path: Path) -> pd.DataFrame:
    history_df, live_applied = build_live_feature_history(feature_df, live_quotes_path)
    if not live_applied or history_df.empty:
        return pd.DataFrame()
    latest_date = history_df["date"].max()
    return history_df.loc[history_df["date"] == latest_date].sort_values(["code"]).reset_index(drop=True)


def load_fundamental_dataset(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = df.rename(columns={k: v for k, v in FUND_RENAME.items() if k in df.columns})
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    df["bsns_year"] = pd.to_numeric(df["bsns_year"], errors="coerce").astype("Int64")
    df["reprt_code"] = df["reprt_code"].astype(str)
    for col in ["revenue_q", "op_income_q", "net_income_q", "op_margin_q", "roe_simple_q"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["quarter_num"] = df["reprt_code"].map(QUARTER_ORDER)
    df = df.dropna(subset=["filing_date", "quarter_num"]).sort_values(
        ["code", "bsns_year", "quarter_num", "filing_date"]
    )
    return df.reset_index(drop=True)


def build_filing_features(fund_df: pd.DataFrame) -> pd.DataFrame:
    df = fund_df.copy()
    grp = df.groupby("code", sort=False)

    df["net_margin_q"] = df["net_income_q"] / df["revenue_q"].replace(0, np.nan)
    df["net_op_gap_ratio"] = (df["net_income_q"] - df["op_income_q"]).abs() / df["revenue_q"].abs().replace(0, np.nan)
    df["non_operating_profit_flag"] = (df["op_income_q"] <= 0) & (df["net_income_q"] > 0)
    df["extreme_net_margin_flag"] = df["net_margin_q"].abs() > 0.50
    df["earnings_exception_flag"] = df["non_operating_profit_flag"] | (
        df["extreme_net_margin_flag"] & (df["net_op_gap_ratio"] > 0.20)
    )

    for base in ["revenue_q", "op_income_q", "net_income_q", "op_margin_q", "net_margin_q"]:
        prev_q = grp[base].shift(1)
        df[f"{base}_qoq"] = df[base] - prev_q
    for base in ["revenue_q", "op_income_q", "net_income_q", "op_margin_q", "net_margin_q"]:
        df[f"{base}_qoq_accel"] = df[f"{base}_qoq"] - grp[f"{base}_qoq"].shift(1)

    for base in ["revenue_q", "op_income_q", "net_income_q"]:
        df[f"{base}_ttm"] = grp[base].transform(lambda s: s.rolling(4, min_periods=2).sum())
        df[f"{base}_vol_4q"] = grp[base].transform(lambda s: s.rolling(4, min_periods=3).std())

    keep_cols = [
        "code",
        "filing_date",
        "corp_code",
        "corp_name",
        "bsns_year",
        "reprt_code",
        "revenue_q",
        "op_income_q",
        "net_income_q",
        "op_margin_q",
        "roe_simple_q",
        "net_margin_q",
        "net_op_gap_ratio",
        "non_operating_profit_flag",
        "extreme_net_margin_flag",
        "earnings_exception_flag",
        "revenue_q_qoq",
        "op_income_q_qoq",
        "net_income_q_qoq",
        "op_margin_q_qoq",
        "net_margin_q_qoq",
        "revenue_q_qoq_accel",
        "op_income_q_qoq_accel",
        "net_income_q_qoq_accel",
        "op_margin_q_qoq_accel",
        "net_margin_q_qoq_accel",
        "revenue_q_ttm",
        "op_income_q_ttm",
        "net_income_q_ttm",
        "revenue_q_vol_4q",
        "op_income_q_vol_4q",
        "net_income_q_vol_4q",
    ]
    return df[keep_cols].drop_duplicates(["code", "filing_date"], keep="last").reset_index(drop=True)


def merge_filing_features(feature_df: pd.DataFrame, filing_df: pd.DataFrame) -> pd.DataFrame:
    parts: List[pd.DataFrame] = []
    for code, left in feature_df.sort_values(["code", "date"]).groupby("code", sort=False):
        right = filing_df.loc[filing_df["code"] == code].sort_values("filing_date")
        left = left.sort_values("date").copy()
        if right.empty:
            parts.append(left)
            continue
        merged = pd.merge_asof(
            left,
            right,
            left_on="date",
            right_on="filing_date",
            direction="backward",
            allow_exact_matches=True,
        )
        if "code_x" in merged.columns:
            merged["code"] = merged["code_x"]
            merged = merged.drop(columns=[c for c in ["code_x", "code_y"] if c in merged.columns])
        parts.append(merged)
    return pd.concat(parts, ignore_index=True)


def _fit_latest_ml_assist(df: pd.DataFrame, cfg: EarningsStrategyConfig) -> Tuple[pd.Series, str]:
    backend = _supported_ml_backend(cfg.ml_backend)
    score = pd.Series(0.0, index=df.index)
    if backend == "none":
        return score, "none"

    latest_date = df["date"].max()
    latest_mask = df["date"] == latest_date
    train_start = latest_date - pd.Timedelta(days=cfg.ml_train_window_days)
    train_mask = (df["date"] >= train_start) & (df["date"] < latest_date - pd.Timedelta(days=cfg.ml_horizon_days))

    feat_cols = [
        "op_margin_pti",
        "net_margin_pti",
        "op_income_qoq_pti",
        "net_income_qoq_pti",
        "op_income_qoq_accel",
        "net_income_qoq_accel",
        "op_income_q_ttm",
        "net_income_q_ttm",
        "op_income_q_vol_4q",
        "net_income_q_vol_4q",
        "net_op_gap_ratio",
        "timing_score",
        "adv20_pct_rank",
        "atr_ratio",
        "ret_20",
        "ret_60",
        "exposure",
    ]

    train = df.loc[train_mask & df["fwd_ret_60d"].notna() & df["core_candidate"]].copy()
    latest = df.loc[latest_mask & df["core_candidate"]].copy()
    if len(train) < 500 or latest.empty:
        return score, backend

    X_train = train[feat_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y_train = (train["fwd_ret_60d"] > 0).astype(int)
    X_pred = latest[feat_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if backend == "lightgbm":
        import lightgbm as lgb

        model = lgb.LGBMClassifier(
            n_estimators=250,
            max_depth=4,
            learning_rate=0.04,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
        )
        model.fit(X_train, y_train)
        prob = model.predict_proba(X_pred)[:, 1]
    elif backend == "xgboost":
        from xgboost import XGBClassifier

        model = XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
        )
        model.fit(X_train, y_train)
        prob = model.predict_proba(X_pred)[:, 1]
    else:
        from sklearn.ensemble import RandomForestClassifier

        model = RandomForestClassifier(
            n_estimators=300,
            max_depth=6,
            min_samples_leaf=20,
            n_jobs=-1,
            random_state=42,
        )
        model.fit(X_train, y_train)
        prob = model.predict_proba(X_pred)[:, 1]

    score.loc[latest.index] = prob
    return score, backend


def prepare_strategy_frame(
    feature_path: Path,
    fundamental_path: Path,
    cfg: EarningsStrategyConfig,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    feature_df = load_feature_dataset(feature_path)
    filing_features = build_filing_features(load_fundamental_dataset(fundamental_path))
    df = merge_filing_features(feature_df, filing_features)
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    df = add_multi_timeframe_ma_features(df, cfg)

    numeric_cols = [
        "close",
        "low",
        "adv20",
        "adv20_pct_rank",
        "ret_5",
        "ret_20",
        "ret_60",
        "atr_ratio",
        "dist_month_10",
        "exposure",
        "revenue_pti",
        "op_income_pti",
        "net_income_pti",
        "op_margin_pti",
        "days_since_filing",
        "revenue_q_qoq",
        "op_income_q_qoq",
        "net_income_q_qoq",
        "op_income_q_ttm",
        "net_income_q_ttm",
        "op_income_q_vol_4q",
        "net_income_q_vol_4q",
        "net_op_gap_ratio",
        "op_income_qoq_pti",
        "net_income_qoq_pti",
        "op_income_qoq_accel",
        "net_income_qoq_accel",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    grp = df.groupby("code", sort=False)
    for horizon in [20, 60, 90]:
        df[f"fwd_ret_{horizon}d"] = grp["close"].shift(-horizon) / df["close"] - 1.0

    df["net_margin_pti"] = df["net_income_pti"] / df["revenue_pti"].replace(0, np.nan)
    df["fresh_filing"] = df["days_since_filing"].between(0, cfg.recent_filing_days)
    df["macro_gate_ok"] = df["exposure"].fillna(1.0) > cfg.riskoff_target_ratio
    df["quality_gate_ok"] = (~df["earnings_exception_flag"].fillna(False)) & (df["net_op_gap_ratio"] <= 0.35)
    df["core_candidate"] = (
        df["is_trading_day"].fillna(False)
        & (df["adv20"] >= cfg.min_adv20)
    )

    score_map = {
        "op_margin_pti": "z_op_margin",
        "net_margin_pti": "z_net_margin",
        "op_income_qoq_pti": "z_op_qoq",
        "net_income_qoq_pti": "z_net_qoq",
        "op_income_qoq_accel": "z_op_accel",
        "net_income_qoq_accel": "z_net_accel",
        "op_income_q_ttm": "z_op_ttm",
        "net_income_q_ttm": "z_net_ttm",
        "op_income_q_vol_4q": "z_op_vol",
        "net_income_q_vol_4q": "z_net_vol",
        "net_op_gap_ratio": "z_gap",
        "days_since_filing": "z_freshness",
    }
    for src, zc in score_map.items():
        if src not in df.columns:
            df[src] = np.nan
        _zscore_by_date(df, src, zc)

    df["profitability_score"] = 0.55 * df["z_op_margin"] + 0.45 * df["z_net_margin"]
    df["growth_score"] = 0.30 * df["z_op_qoq"] + 0.30 * df["z_net_qoq"] + 0.20 * df["z_op_accel"] + 0.20 * df["z_net_accel"]
    df["durability_score"] = 0.50 * df["z_op_ttm"] + 0.50 * df["z_net_ttm"]
    df["stability_score"] = -0.45 * df["z_op_vol"] - 0.35 * df["z_net_vol"] - 0.20 * df["z_gap"]
    df["freshness_score"] = -df["z_freshness"]

    df["timing_score"] = (
        0.45 * _bool_score(df["monthly_main_ok"])
        + 0.20 * _bool_score(df["weekly_aux_ok"])
        + 0.15 * _bool_score(df["ret_5"] <= cfg.max_ret_5)
        + 0.10 * _bool_score(df["atr_ratio"] <= cfg.max_atr_ratio)
        + 0.10 * _bool_score(df["dist_month_10"] <= cfg.max_dist_ma_mid)
    )

    df["fundamental_score"] = (
        0.32 * df["profitability_score"]
        + 0.28 * df["growth_score"]
        + 0.20 * df["durability_score"]
        + 0.12 * df["stability_score"]
        + 0.08 * df["freshness_score"]
    )
    df["ml_assist_score"] = 0.0
    latest_ml, ml_backend_used = _fit_latest_ml_assist(df, cfg)
    df["ml_assist_score"] = latest_ml
    df = _apply_trend_logic(df, cfg, include_ml=True)

    metadata = {
        "strategy_id": cfg.strategy_id,
        "trend_mode": cfg.trend_mode,
        "rows": int(len(df)),
        "codes": int(df["code"].nunique()),
        "date_min": str(df["date"].min().date()),
        "date_max": str(df["date"].max().date()),
        "ml_backend_used": ml_backend_used,
    }
    return df, metadata


def _row_reasons(row: pd.Series, signal: str) -> Tuple[str, str, str]:
    reasons: List[str] = []
    month_window = _coerce_float(row.get("v2_month_window"))
    week_window = _coerce_float(row.get("v2_week_window"))
    month_dist = _coerce_float(row.get("v2_month_period_dist"))
    week_dist = _coerce_float(row.get("v2_week_period_dist"))
    buy_timeframe = str(row.get("v2_buy_timeframe") or "monthly").strip().lower()
    sell_timeframe = str(row.get("v2_sell_timeframe") or "weekly").strip().lower()
    buy_window = _coerce_float(row.get("v2_buy_window"))
    sell_window = _coerce_float(row.get("v2_sell_window"))
    buy_dist = _coerce_float(row.get("v2_buy_period_dist"))
    sell_dist = _coerce_float(row.get("v2_sell_period_dist"))
    timeframe_labels = {"monthly": "월봉", "weekly": "주봉", "daily": "일봉"}
    timeframe_short = {"monthly": "월", "weekly": "주", "daily": "일"}
    buy_label = timeframe_labels.get(buy_timeframe, "매수")
    sell_label = timeframe_labels.get(sell_timeframe, "매도")
    if signal in {"BUY", "WATCH", "HOLD"}:
        if bool(row.get("v2_buy_cross", row.get("v2_month_buy_cross", False))):
            reasons.append(f"{buy_label} 신규 상향돌파")
        elif bool(row.get("v2_buy_above_maintain", row.get("v2_month_above_maintain", False))):
            reasons.append(f"{buy_label} 유지상방")
        if np.isfinite(buy_window) and pd.notna(buy_dist):
            reasons.append(f"매수 {timeframe_short.get(buy_timeframe, '')}{int(buy_window)} / 이격 {buy_dist:.1%}")
        if np.isfinite(sell_window) and pd.notna(sell_dist):
            reasons.append(f"매도 {timeframe_short.get(sell_timeframe, '')}{int(sell_window)} / 이격 {sell_dist:.1%}")
        elif np.isfinite(month_window) and pd.notna(month_dist):
            reasons.append(f"최적 월이평 {int(month_window)} / 이격 {month_dist:.1%}")
        elif np.isfinite(week_window) and pd.notna(week_dist):
            reasons.append(f"최적 주이평 {int(week_window)} / 이격 {week_dist:.1%}")
        if pd.notna(row.get("op_margin_pti")):
            reasons.append(f"영업이익률 {row['op_margin_pti']:.1%}")
        if pd.notna(row.get("net_margin_pti")):
            reasons.append(f"순이익률 {row['net_margin_pti']:.1%}")
        if pd.notna(row.get("op_income_qoq_pti")) and row["op_income_qoq_pti"] > 0:
            reasons.append(f"영업이익 QoQ {_format_amount(row['op_income_qoq_pti'])}")
        if pd.notna(row.get("net_income_qoq_pti")) and row["net_income_qoq_pti"] > 0:
            reasons.append(f"순이익 QoQ {_format_amount(row['net_income_qoq_pti'])}")
        if pd.notna(row.get("op_income_q_ttm")):
            reasons.append(f"최근4Q 영업이익 {_format_amount(row['op_income_q_ttm'])}")
        if row.get("timing_score", 0) >= 0.75:
            reasons.append("중기 타이밍 양호")
        if row.get("ml_assist_score", 0) > 0:
            reasons.append(f"ML 보조점수 {row['ml_assist_score']:.2f}")
    else:
        if bool(row.get("v2_sell_trigger", row.get("v2_week_sell_trigger", False))) and np.isfinite(sell_window):
            reasons.append(f"매도 {timeframe_short.get(sell_timeframe, '')}{int(sell_window)} 하향트리거")
        if np.isfinite(sell_window) and pd.notna(sell_dist):
            reasons.append(f"매도 {timeframe_short.get(sell_timeframe, '')}{int(sell_window)} / 이격 {sell_dist:.1%}")
        if row.get("_exit_reason"):
            reasons.append(str(row["_exit_reason"]))
        if row.get("_realized_return") is not None and not pd.isna(row.get("_realized_return")):
            reasons.append(f"실현수익률 {row['_realized_return']:.2%}")

    reasons = reasons[:3] + [""] * max(0, 3 - len(reasons))
    return reasons[0], reasons[1], reasons[2]


def _risk_flag(row: pd.Series) -> str:
    flags = []
    if str(row.get("regime", "")) == "risk_off":
        flags.append("macro_risk_off")
    if bool(row.get("earnings_exception_flag", False)):
        flags.append("earnings_exception")
    if pd.notna(row.get("atr_ratio")) and row.get("atr_ratio", 0) > 0.10:
        flags.append("high_volatility")
    if bool(row.get("v2_sell_watch", row.get("v2_week_sell_watch", False))):
        flags.append("sell_watch")
    if pd.notna(row.get("v2_buy_live_dist")) and row.get("v2_buy_live_dist", 0) > 0.18:
        flags.append("monthly_overheat")
    return "|".join(flags)


def _coerce_float(value: object) -> float:
    try:
        if value is None or pd.isna(value):
            return float("nan")
        return float(value)
    except Exception:
        return float("nan")


def _execution_plan_fields(row: pd.Series, signal: str) -> Dict[str, str]:
    signal = str(signal).upper()
    ret_5 = _coerce_float(row.get("ret_5"))
    atr_ratio = _coerce_float(row.get("atr_ratio"))
    overheat = (not np.isnan(ret_5) and ret_5 >= 0.08) or (not np.isnan(atr_ratio) and atr_ratio >= 0.08)

    intraday_plan = ""
    next_day_plan = ""
    execution_priority = "monitor"

    if signal == "BUY":
        execution_priority = "enter"
        intraday_plan = "추격보다 가격 안정 구간에서 분할 진입합니다."
        next_day_plan = "시초 5~15분 대기 후 가격 안정 또는 첫 눌림 확인 뒤 분할 진입합니다."
        if overheat:
            intraday_plan = "추격 금지. 첫 눌림 또는 변동성 완화 전까지 진입을 보류합니다."
            next_day_plan = "시초 추격 금지. 5~15분 대기 후 첫 눌림과 거래대금 유지 확인 시에만 소액 진입합니다."
    elif signal == "WATCH":
        execution_priority = "watch"
        intraday_plan = "장중 강도와 거래대금 확인 후 매수 승격 여부를 점검합니다."
        next_day_plan = "익일 시초 강도와 거래대금 확인 후 매수 후보 유지 여부를 재평가합니다."
    elif signal == "HOLD":
        execution_priority = "hold"
        intraday_plan = "보유 유지. 손절선 또는 중기 추세 훼손 시 매도 전환을 우선 검토합니다."
        next_day_plan = "익일 시초 약세가 크지 않으면 보유 유지, 손절선 하향 이탈 시 매도를 우선합니다."
    elif signal == "SELL":
        execution_priority = "exit"
        intraday_plan = "실행 가능한 매도 신호입니다. 반등 대기보다 즉시 청산을 우선합니다."
        next_day_plan = "익일 장 초반 유동성 구간에서 우선 정리하고 손절 훼손이 크면 지체 없이 청산합니다."
    else:
        intraday_plan = "신호를 다시 확인합니다."
        next_day_plan = "익일 장 시작 후 신호를 다시 확인합니다."

    return {
        "intraday_action_guide": intraday_plan,
        "next_day_action_guide": next_day_plan,
        "execution_priority": execution_priority,
    }


def _signal_context_fields(row: pd.Series) -> Dict[str, object]:
    fields = {
        "ma_day_20": _coerce_float(row.get("ma_day_20")),
        "week_10_ma": _coerce_float(row.get("week_10_ma")),
        "month_10_ma": _coerce_float(row.get("month_10_ma")),
        "weekly_aux_ok": bool(row.get("weekly_aux_ok", False)),
        "monthly_main_ok": bool(row.get("monthly_main_ok", False)),
        "v2_month_window": _coerce_float(row.get("v2_month_window")),
        "v2_week_window": _coerce_float(row.get("v2_week_window")),
        "v2_month_ma": _coerce_float(row.get("v2_month_ma")),
        "v2_week_ma": _coerce_float(row.get("v2_week_ma")),
        "v2_month_period_dist": _coerce_float(row.get("v2_month_period_dist")),
        "v2_month_prev_period_dist": _coerce_float(row.get("v2_month_prev_period_dist")),
        "v2_week_period_dist": _coerce_float(row.get("v2_week_period_dist")),
        "v2_month_live_dist": _coerce_float(row.get("v2_month_live_dist")),
        "v2_week_live_dist": _coerce_float(row.get("v2_week_live_dist")),
        "v2_month_buy_cross": bool(row.get("v2_month_buy_cross", False)),
        "v2_month_above_maintain": bool(row.get("v2_month_above_maintain", False)),
        "v2_month_sell_cross": bool(row.get("v2_month_sell_cross", False)),
        "v2_week_sell_trigger": bool(row.get("v2_week_sell_trigger", False)),
        "v2_week_sell_watch": bool(row.get("v2_week_sell_watch", False)),
        "v2_contract_mode": str(row.get("v2_contract_mode") or ""),
        "v2_buy_timeframe": str(row.get("v2_buy_timeframe") or ""),
        "v2_sell_timeframe": str(row.get("v2_sell_timeframe") or ""),
        "v2_buy_window": _coerce_float(row.get("v2_buy_window")),
        "v2_sell_window": _coerce_float(row.get("v2_sell_window")),
        "v2_buy_ma": _coerce_float(row.get("v2_buy_ma")),
        "v2_sell_ma": _coerce_float(row.get("v2_sell_ma")),
        "v2_buy_period_dist": _coerce_float(row.get("v2_buy_period_dist")),
        "v2_buy_prev_period_dist": _coerce_float(row.get("v2_buy_prev_period_dist")),
        "v2_sell_period_dist": _coerce_float(row.get("v2_sell_period_dist")),
        "v2_buy_live_dist": _coerce_float(row.get("v2_buy_live_dist")),
        "v2_sell_live_dist": _coerce_float(row.get("v2_sell_live_dist")),
        "v2_buy_cross": bool(row.get("v2_buy_cross", False)),
        "v2_buy_above_maintain": bool(row.get("v2_buy_above_maintain", False)),
        "v2_buy_sell_cross": bool(row.get("v2_buy_sell_cross", False)),
        "v2_sell_trigger": bool(row.get("v2_sell_trigger", False)),
        "v2_sell_watch": bool(row.get("v2_sell_watch", False)),
    }
    return fields


def _effective_stop_price(row: pd.Series, position: Dict[str, object]) -> float:
    entry_price = float(position["entry_price"])
    stop_pct = float(position["stop_pct"])
    initial_stop = entry_price * (1.0 + stop_pct)
    try:
        close = _coerce_float(row.get("close"))
    except Exception:
        close = np.nan
    if np.isfinite(close) and close >= entry_price * 1.08:
        return max(initial_stop, entry_price)
    return initial_stop


def _safe_low_for_stop(row: pd.Series, close_price: float) -> float:
    low = _coerce_float(row.get("low"))
    if np.isfinite(low) and low > 0:
        return float(low)
    fallback_candidates = [
        _coerce_float(row.get("open")),
        _coerce_float(row.get("high")),
        close_price,
    ]
    valid = [value for value in fallback_candidates if np.isfinite(value) and value > 0]
    if not valid:
        return float("nan")
    return float(min(valid))


def _trend_break(row: pd.Series, cfg: EarningsStrategyConfig) -> bool:
    dist = _coerce_float(row.get("v2_sell_period_dist"))
    if not np.isfinite(dist):
        dist = _coerce_float(row.get("v2_week_period_dist"))
    if np.isfinite(dist):
        return bool(dist <= cfg.weekly_sell_threshold)
    return not bool(row.get("monthly_main_ok", True))


def _sort_candidates_by_ma_state(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    ranked = frame.copy()
    ranked["_buy_cross_priority"] = (
        ranked.get("v2_buy_cross", pd.Series(False, index=ranked.index))
        .fillna(False)
        .astype(int)
    )
    ranked["_buy_live_dist_priority"] = pd.to_numeric(
        ranked.get("v2_buy_live_dist", ranked.get("v2_buy_period_dist", pd.Series(np.nan, index=ranked.index))),
        errors="coerce",
    ).fillna(float("-inf"))
    ranked["_sell_live_dist_priority"] = pd.to_numeric(
        ranked.get("v2_sell_live_dist", ranked.get("v2_sell_period_dist", pd.Series(np.nan, index=ranked.index))),
        errors="coerce",
    ).fillna(float("-inf"))
    ranked["_code_priority"] = ranked.index.astype(str)
    ranked = ranked.sort_values(
        ["_buy_cross_priority", "_buy_live_dist_priority", "_sell_live_dist_priority", "_code_priority"],
        ascending=[False, False, False, True],
        kind="stable",
    )
    return ranked.drop(
        columns=["_buy_cross_priority", "_buy_live_dist_priority", "_sell_live_dist_priority", "_code_priority"],
        errors="ignore",
    )


def _target_positions(exposure: float, cfg: EarningsStrategyConfig) -> int:
    exposure = float(np.clip(exposure, 0.0, 1.0))
    if exposure <= 0.0:
        return 0
    if exposure >= 0.99:
        return cfg.max_positions
    return max(1, int(np.floor(cfg.max_positions * exposure)))


def _resolve_macro_context(frame: pd.DataFrame, dt: pd.Timestamp) -> tuple[float, str]:
    exposure_series = pd.to_numeric(frame.get("exposure"), errors="coerce").dropna()
    regime_series = frame.get("regime", pd.Series(dtype=object))
    if isinstance(regime_series, pd.Series):
        regime_series = regime_series.dropna().astype(str).str.strip()
        regime_series = regime_series[regime_series != ""]
    else:
        regime_series = pd.Series(dtype=object)

    if not exposure_series.empty and not regime_series.empty:
        return float(exposure_series.iloc[0]), str(regime_series.iloc[0])

    macro_path = data_path("macro_regime_v3_rec.csv")
    if macro_path.exists():
        try:
            macro = pd.read_csv(macro_path, usecols=["date", "regime", "exposure"])
            macro["date"] = pd.to_datetime(macro["date"], errors="coerce")
            macro["exposure"] = pd.to_numeric(macro["exposure"], errors="coerce")
            macro["regime"] = macro["regime"].astype(str).str.strip()
            macro = macro.dropna(subset=["date"]).sort_values("date")
            macro = macro[(macro["date"] <= pd.Timestamp(dt)) & macro["exposure"].notna() & (macro["regime"] != "")]
            if not macro.empty:
                row = macro.iloc[-1]
                return float(row["exposure"]), str(row["regime"])
        except Exception:
            pass

    exposure = float(exposure_series.iloc[0]) if not exposure_series.empty else 1.0
    regime = str(regime_series.iloc[0]) if not regime_series.empty else "unknown"
    return exposure, regime


def simulate_signals(strategy_df: pd.DataFrame, cfg: EarningsStrategyConfig) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = strategy_df.sort_values(["date", "code"]).reset_index(drop=True)
    by_date = {d: g.set_index("code") for d, g in data.groupby("date", sort=True)}
    dates = sorted(by_date.keys())

    positions: Dict[str, Dict[str, object]] = {}
    signal_rows: List[Dict[str, object]] = []
    trade_rows: List[Dict[str, object]] = []
    decision_rows: List[Dict[str, object]] = []
    curve_rows: List[Dict[str, object]] = []
    trade_id = 1
    prev_date = None

    for dt in dates:
        today = by_date[dt]
        exposure, regime = _resolve_macro_context(today, pd.Timestamp(dt))
        target_positions = _target_positions(exposure, cfg)
        trend_mode = str(cfg.trend_mode or "optimal_ma_v2").strip().lower()

        if prev_date is not None and positions:
            prev = by_date.get(prev_date)
            rets = []
            if prev is not None:
                for code in list(positions.keys()):
                    if code in prev.index and code in today.index:
                        prev_close = float(prev.at[code, "close"])
                        cur_close = float(today.at[code, "close"])
                        if prev_close > 0 and np.isfinite(cur_close):
                            rets.append(cur_close / prev_close - 1.0)
                        positions[code]["hold_bars"] = int(positions[code]["hold_bars"]) + 1
            daily_return = float(np.mean(rets)) if rets else 0.0
        else:
            daily_return = 0.0

        buy_count = sell_count = hold_count = watch_count = 0
        buy_codes: List[str] = []
        sell_codes: List[str] = []
        watch_codes: List[str] = []

        to_remove: List[str] = []
        for code, pos in list(positions.items()):
            if code not in today.index:
                exit_price = float(pos["last_close"])
                realized_return = exit_price / float(pos["entry_price"]) - 1.0
                trade_rows.append(
                    {
                        "trade_id": pos["trade_id"],
                        "strategy_id": cfg.strategy_id,
                        "code": code,
                        "name": pos["name"],
                        "entry_date": pos["entry_date"],
                        "exit_date": dt,
                        "entry_price": pos["entry_price"],
                        "exit_price": exit_price,
                        "holding_days": pos["hold_bars"],
                        "realized_return": realized_return,
                        "exit_reason": "missing_price_row",
                        "status": "CLOSED",
                    }
                )
                to_remove.append(code)
                continue

            row = today.loc[code]
            close = float(row["close"])
            low = _safe_low_for_stop(row, close)
            pos["last_close"] = close
            hold_bars = int(pos["hold_bars"])
            effective_stop_price = _effective_stop_price(row, pos)
            stop_hit = bool(np.isfinite(low) and low <= effective_stop_price)
            timing_break = bool(_trend_break(row, cfg))
            sell_signal = stop_hit or timing_break
            if sell_signal:
                exit_price = effective_stop_price if stop_hit else close
                realized_return = exit_price / float(pos["entry_price"]) - 1.0
                if stop_hit:
                    exit_reason = "stop_loss"
                else:
                    exit_reason = "timing_break"
                row = row.copy()
                row["_exit_reason"] = exit_reason
                row["_realized_return"] = realized_return
                reason_1, reason_2, reason_3 = _row_reasons(row, "SELL")
                signal_rows.append(
                    {
                        "date": dt,
                        "code": code,
                        "name": row["name"],
                        "industry": row["industry"],
                        "signal": "SELL",
                        "strategy_id": cfg.strategy_id,
                        "conviction_score": float(row["conviction_score"]),
                        "holding_horizon": "중기(2~6개월)",
                        "reason_1": reason_1,
                        "reason_2": reason_2,
                        "reason_3": reason_3,
                        "risk_flag": _risk_flag(row),
                        "stop_rule": f"{cfg.fixed_stop_loss:.0%}",
                        "target_exit_rule": "초기손절/원금보호/품질/타이밍",
                        **_execution_plan_fields(row, "SELL"),
                        **_signal_context_fields(row),
                    }
                )
                trade_rows.append(
                    {
                        "trade_id": pos["trade_id"],
                        "strategy_id": cfg.strategy_id,
                        "code": code,
                        "name": pos["name"],
                        "entry_date": pos["entry_date"],
                        "exit_date": dt,
                        "entry_price": pos["entry_price"],
                        "exit_price": exit_price,
                        "holding_days": hold_bars,
                        "realized_return": realized_return,
                        "exit_reason": exit_reason,
                        "status": "CLOSED",
                    }
                )
                sell_count += 1
                sell_codes.append(code)
                to_remove.append(code)

        for code in to_remove:
            positions.pop(code, None)

        candidates = _sort_candidates_by_ma_state(today[today["buy_candidate"]])
        slots = max(0, target_positions - len(positions))
        if slots > 0:
            for code, row in candidates.iterrows():
                if slots <= 0:
                    break
                if code in positions:
                    continue
                positions[code] = {
                    "trade_id": trade_id,
                    "name": row["name"],
                    "entry_date": dt,
                    "entry_price": float(row["close"]),
                    "last_close": float(row["close"]),
                    "stop_pct": cfg.fixed_stop_loss,
                    "hold_bars": 0,
                }
                trade_id += 1
                reason_1, reason_2, reason_3 = _row_reasons(row, "BUY")
                signal_rows.append(
                    {
                        "date": dt,
                        "code": code,
                        "name": row["name"],
                        "industry": row["industry"],
                        "signal": "BUY",
                        "strategy_id": cfg.strategy_id,
                        "conviction_score": float(row["conviction_score"]),
                        "holding_horizon": "중기(2~6개월)",
                        "reason_1": reason_1,
                        "reason_2": reason_2,
                        "reason_3": reason_3,
                        "risk_flag": _risk_flag(row),
                        "stop_rule": f"{cfg.fixed_stop_loss:.0%}",
                        "target_exit_rule": "초기손절/원금보호/품질/타이밍",
                        **_execution_plan_fields(row, "BUY"),
                        **_signal_context_fields(row),
                    }
                )
                buy_count += 1
                buy_codes.append(code)
                slots -= 1

        for code in list(positions.keys()):
            if code not in today.index:
                continue
            if code in buy_codes or code in sell_codes:
                continue
            row = today.loc[code]
            reason_1, reason_2, reason_3 = _row_reasons(row, "HOLD")
            signal_rows.append(
                {
                    "date": dt,
                    "code": code,
                    "name": row["name"],
                    "industry": row["industry"],
                    "signal": "HOLD",
                    "strategy_id": cfg.strategy_id,
                    "conviction_score": float(row["conviction_score"]),
                    "holding_horizon": "중기(2~6개월)",
                    "reason_1": reason_1,
                    "reason_2": reason_2,
                    "reason_3": reason_3,
                    "risk_flag": _risk_flag(row),
                    "stop_rule": f"{cfg.fixed_stop_loss:.0%}",
                    "target_exit_rule": "품질 유지 + 타이밍 양호 시 보유",
                    **_execution_plan_fields(row, "HOLD"),
                        **_signal_context_fields(row),
                }
            )
            hold_count += 1

        watch_candidates = _sort_candidates_by_ma_state(today[today["watch_candidate"]])
        watch_candidates = watch_candidates[~watch_candidates.index.isin(positions.keys())].head(cfg.watchlist_size)
        for code, row in watch_candidates.iterrows():
            reason_1, reason_2, reason_3 = _row_reasons(row, "WATCH")
            signal_rows.append(
                {
                    "date": dt,
                    "code": code,
                    "name": row["name"],
                    "industry": row["industry"],
                    "signal": "WATCH",
                    "strategy_id": cfg.strategy_id,
                    "conviction_score": float(row["conviction_score"]),
                    "holding_horizon": "관찰",
                    "reason_1": reason_1,
                    "reason_2": reason_2,
                    "reason_3": reason_3,
                    "risk_flag": _risk_flag(row),
                    "stop_rule": "",
                    "target_exit_rule": "기존 코어점수 + 타이밍 확인 후 편입",
                    **_execution_plan_fields(row, "WATCH"),
                        **_signal_context_fields(row),
                }
            )
            watch_count += 1
            watch_codes.append(code)

        decision_rows.append(
            {
                "date": dt,
                "strategy_id": cfg.strategy_id,
                "market_regime": regime,
                "exposure": exposure,
                "target_positions": target_positions,
                "positions_after": len(positions),
                "buy_count": buy_count,
                "sell_count": sell_count,
                "hold_count": hold_count,
                "watch_count": watch_count,
                "buy_codes": ",".join(buy_codes),
                "sell_codes": ",".join(sell_codes),
                "watch_codes": ",".join(watch_codes),
                "summary_text": f"regime={regime}, exposure={exposure:.2f}, buy={buy_count}, sell={sell_count}, hold={hold_count}, watch={watch_count}",
            }
        )
        curve_rows.append({"date": dt, "daily_return": daily_return, "n_positions": len(positions), "exposure": exposure})
        prev_date = dt

    for code, pos in positions.items():
        trade_rows.append(
            {
                "trade_id": pos["trade_id"],
                "strategy_id": cfg.strategy_id,
                "code": code,
                "name": pos["name"],
                "entry_date": pos["entry_date"],
                "exit_date": pd.NaT,
                "entry_price": pos["entry_price"],
                "exit_price": pos["last_close"],
                "holding_days": pos["hold_bars"],
                "realized_return": pos["last_close"] / pos["entry_price"] - 1.0,
                "exit_reason": "",
                "status": "OPEN",
            }
        )

    signal_df = pd.DataFrame(signal_rows).sort_values(["date", "signal", "code"]).reset_index(drop=True)
    trade_df = pd.DataFrame(trade_rows).sort_values(["entry_date", "trade_id"]).reset_index(drop=True)
    decision_df = pd.DataFrame(decision_rows).sort_values("date").reset_index(drop=True)
    curve_df = pd.DataFrame(curve_rows).sort_values("date").reset_index(drop=True)
    if not curve_df.empty:
        curve_df["equity"] = (1.0 + curve_df["daily_return"].fillna(0.0)).cumprod()
    return signal_df, trade_df, decision_df, curve_df


def evaluate_backtest(curve_df: pd.DataFrame, trade_df: pd.DataFrame) -> pd.DataFrame:
    if curve_df.empty:
        return pd.DataFrame([{"metric": "status", "value": "empty_curve"}])
    ret = curve_df["daily_return"].fillna(0.0)
    years = max(len(ret) / 252.0, 1 / 252.0)
    final_equity = float(curve_df["equity"].iloc[-1])
    running_max = curve_df["equity"].cummax()
    drawdown = curve_df["equity"] / running_max - 1.0
    vol = ret.std(ddof=0) * np.sqrt(252)
    sharpe = float((ret.mean() * 252) / vol) if vol > 0 else np.nan

    closed = trade_df[trade_df["status"] == "CLOSED"].copy()
    avg_hold = float(closed["holding_days"].mean()) if not closed.empty else np.nan
    win_rate = float((closed["realized_return"] > 0).mean()) if not closed.empty else np.nan

    rows = [
        {"metric": "date_min", "value": str(curve_df["date"].min().date())},
        {"metric": "date_max", "value": str(curve_df["date"].max().date())},
        {"metric": "cagr", "value": final_equity ** (1.0 / years) - 1.0},
        {"metric": "mdd", "value": float(drawdown.min())},
        {"metric": "sharpe", "value": sharpe},
        {"metric": "win_rate", "value": win_rate},
        {"metric": "num_closed_trades", "value": int(len(closed))},
        {"metric": "num_open_trades", "value": int((trade_df["status"] == "OPEN").sum())},
        {"metric": "avg_holding_days", "value": avg_hold},
        {"metric": "final_equity", "value": final_equity},
    ]
    return pd.DataFrame(rows)


def build_condition_performance(
    strategy_df: pd.DataFrame,
    cfg: EarningsStrategyConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    base = strategy_df[strategy_df["is_trading_day"].fillna(False)].copy()
    conditions = {
        "core_candidate": base["core_candidate"],
        "fresh_filing_30d": base["days_since_filing"].between(0, 30),
        "fresh_filing_60d": base["days_since_filing"].between(0, 60),
        "op_income_positive": base["op_income_pti"] > 0,
        "net_income_positive": base["net_income_pti"] > 0,
        "op_margin_positive": base["op_margin_pti"] > 0,
        "quality_gate_ok": base["quality_gate_ok"],
        "timing_ok": base["timing_ok"],
        "qoq_positive_combo": (base["op_income_qoq_pti"] > 0) & (base["net_income_qoq_pti"] > 0),
        "ttm_positive_combo": (base["op_income_q_ttm"] > 0) & (base["net_income_q_ttm"] > 0),
    }

    def _summarize(df: pd.DataFrame, mask: pd.Series, target: str, label: str, industry: str = "ALL") -> Dict[str, object]:
        valid = df[mask.notna() & df[target].notna()]
        if valid.empty:
            return {}
        selected = valid[mask.loc[valid.index]]
        rejected = valid[~mask.loc[valid.index]]
        if len(selected) < cfg.research_min_obs or len(rejected) < cfg.research_min_obs:
            return {}
        return {
            "group": industry,
            "condition": label,
            "target": target,
            "selected_obs": int(len(selected)),
            "rejected_obs": int(len(rejected)),
            "selected_mean": float(selected[target].mean()),
            "rejected_mean": float(rejected[target].mean()),
            "mean_diff": float(selected[target].mean() - rejected[target].mean()),
            "selected_win_rate": float((selected[target] > 0).mean()),
            "rejected_win_rate": float((rejected[target] > 0).mean()),
            "win_rate_diff": float((selected[target] > 0).mean() - (rejected[target] > 0).mean()),
        }

    overall_rows: List[Dict[str, object]] = []
    industry_rows: List[Dict[str, object]] = []
    for label, mask in conditions.items():
        for target in ["fwd_ret_20d", "fwd_ret_60d", "fwd_ret_90d"]:
            row = _summarize(base, mask, target, label)
            if row:
                overall_rows.append(row)
            for industry, g in base.groupby("industry", sort=True):
                if len(g) < cfg.research_min_obs * 2:
                    continue
                row = _summarize(g, mask.loc[g.index], target, label, industry=str(industry))
                if row:
                    industry_rows.append(row)

    return pd.DataFrame(overall_rows), pd.DataFrame(industry_rows)


def _candidate_masks(df: pd.DataFrame) -> List[Dict[str, object]]:
    work = df.copy()

    def _pct_rank(col: str) -> pd.Series:
        return work.groupby("date")[col].rank(method="average", pct=True)

    masks: List[Dict[str, object]] = []

    def add(condition_family: str, condition: str, rule_expr: str, mask: pd.Series) -> None:
        masks.append(
            {
                "condition_family": condition_family,
                "condition": condition,
                "rule_expr": rule_expr,
                "mask": mask.fillna(False),
            }
        )

    add("profitability", "op_margin_positive", "op_margin_pti > 0", work["op_margin_pti"] > 0)
    add("profitability", "net_margin_positive", "net_margin_pti > 0", work["net_margin_pti"] > 0)
    add("growth", "op_income_qoq_positive", "op_income_qoq_pti > 0", work["op_income_qoq_pti"] > 0)
    add("growth", "net_income_qoq_positive", "net_income_qoq_pti > 0", work["net_income_qoq_pti"] > 0)
    add("growth", "op_income_qoq_accel_positive", "op_income_qoq_accel > 0", work["op_income_qoq_accel"] > 0)
    add("growth", "net_income_qoq_accel_positive", "net_income_qoq_accel > 0", work["net_income_qoq_accel"] > 0)
    add("durability", "op_income_ttm_positive", "op_income_q_ttm > 0", work["op_income_q_ttm"] > 0)
    add("durability", "net_income_ttm_positive", "net_income_q_ttm > 0", work["net_income_q_ttm"] > 0)
    add("quality", "low_gap_ratio", "net_op_gap_ratio <= daily p30", _pct_rank("net_op_gap_ratio") <= 0.30)
    add("freshness", "fresh_filing_30d", "days_since_filing <= 30", work["days_since_filing"].between(0, 30))
    add("timing", "timing_ok", "timing_ok == True", work["timing_ok"].fillna(False))
    add("macro", "macro_gate_ok", "macro_gate_ok == True", work["macro_gate_ok"].fillna(False))
    add("macro", "risk_on_neutral", "exposure >= 0.3", work["exposure"].fillna(0.0) >= 0.3)

    add("profitability_rank", "op_margin_top30", "op_margin_pti >= daily p70", _pct_rank("op_margin_pti") >= 0.70)
    add("profitability_rank", "net_margin_top30", "net_margin_pti >= daily p70", _pct_rank("net_margin_pti") >= 0.70)
    add("growth_rank", "op_income_qoq_top30", "op_income_qoq_pti >= daily p70", _pct_rank("op_income_qoq_pti") >= 0.70)
    add("growth_rank", "net_income_qoq_top30", "net_income_qoq_pti >= daily p70", _pct_rank("net_income_qoq_pti") >= 0.70)
    add("durability_rank", "op_income_ttm_top30", "op_income_q_ttm >= daily p70", _pct_rank("op_income_q_ttm") >= 0.70)
    add("durability_rank", "net_income_ttm_top30", "net_income_q_ttm >= daily p70", _pct_rank("net_income_q_ttm") >= 0.70)
    add("stability_rank", "op_income_vol_low30", "op_income_q_vol_4q <= daily p30", _pct_rank("op_income_q_vol_4q") <= 0.30)
    add("stability_rank", "net_income_vol_low30", "net_income_q_vol_4q <= daily p30", _pct_rank("net_income_q_vol_4q") <= 0.30)

    add(
        "combo",
        "profit_quality_combo",
        "op_margin_pti > 0 and net_margin_pti > 0 and net_op_gap_ratio <= daily p30",
        (work["op_margin_pti"] > 0) & (work["net_margin_pti"] > 0) & (_pct_rank("net_op_gap_ratio") <= 0.30),
    )
    add(
        "combo",
        "growth_combo",
        "op_income_qoq_pti > 0 and net_income_qoq_pti > 0 and op_income_qoq_accel > 0",
        (work["op_income_qoq_pti"] > 0) & (work["net_income_qoq_pti"] > 0) & (work["op_income_qoq_accel"] > 0),
    )
    add(
        "combo",
        "quality_growth_combo",
        "op_margin_pti >= daily p70 and net_margin_pti >= daily p70 and op_income_qoq_pti > 0 and net_income_qoq_pti > 0",
        (_pct_rank("op_margin_pti") >= 0.70)
        & (_pct_rank("net_margin_pti") >= 0.70)
        & (work["op_income_qoq_pti"] > 0)
        & (work["net_income_qoq_pti"] > 0),
    )
    add(
        "combo",
        "fresh_profit_combo",
        "days_since_filing <= 45 and op_margin_pti >= daily p70 and net_margin_pti >= daily p70",
        work["days_since_filing"].between(0, 45)
        & (_pct_rank("op_margin_pti") >= 0.70)
        & (_pct_rank("net_margin_pti") >= 0.70),
    )

    return masks


def build_rule_candidates(
    strategy_df: pd.DataFrame,
    cfg: EarningsStrategyConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = strategy_df[strategy_df["is_trading_day"].fillna(False)].copy()
    targets = ["fwd_ret_20d", "fwd_ret_60d", "fwd_ret_90d"]

    def _summarize(df: pd.DataFrame, group: str) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for spec in _candidate_masks(df):
            mask = spec["mask"]
            for target in targets:
                valid = df[mask.notna() & df[target].notna()].copy()
                if valid.empty:
                    continue
                selected = valid[mask.loc[valid.index]]
                rejected = valid[~mask.loc[valid.index]]
                if len(selected) < cfg.research_min_obs or len(rejected) < cfg.research_min_obs:
                    continue
                mean_diff = float(selected[target].mean() - rejected[target].mean())
                win_sel = float((selected[target] > 0).mean())
                win_rej = float((rejected[target] > 0).mean())
                support = float(len(selected) / len(valid))
                rows.append(
                    {
                        "group": group,
                        "condition_family": spec["condition_family"],
                        "condition": spec["condition"],
                        "rule_expr": spec["rule_expr"],
                        "target": target,
                        "selected_obs": int(len(selected)),
                        "rejected_obs": int(len(rejected)),
                        "selected_mean": float(selected[target].mean()),
                        "rejected_mean": float(rejected[target].mean()),
                        "mean_diff": mean_diff,
                        "selected_win_rate": win_sel,
                        "rejected_win_rate": win_rej,
                        "win_rate_diff": float(win_sel - win_rej),
                        "support": support,
                        "score": float(mean_diff + win_sel - win_rej),
                    }
                )
        return rows

    overall_df = pd.DataFrame(_summarize(base, "ALL"))

    industry_rows: List[Dict[str, object]] = []
    for industry, g in base.groupby("industry", sort=True):
        if len(g) < cfg.research_min_obs * 3:
            continue
        industry_rows.extend(_summarize(g.copy(), str(industry)))
    industry_df = pd.DataFrame(industry_rows)

    top_source = pd.concat([overall_df, industry_df], ignore_index=True)
    if top_source.empty:
        top_df = pd.DataFrame()
    else:
        top_df = (
            top_source.sort_values(["group", "target", "score", "selected_obs"], ascending=[True, True, False, False])
            .groupby(["group", "target"], as_index=False)
            .head(5)
            .reset_index(drop=True)
        )

    return overall_df, industry_df, top_df


def write_strategy_outputs(
    signal_df: pd.DataFrame,
    trade_df: pd.DataFrame,
    decision_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    research_overall: pd.DataFrame,
    research_industry: pd.DataFrame,
    rule_overall: pd.DataFrame,
    rule_industry: pd.DataFrame,
    rule_top: pd.DataFrame,
    metadata: Dict[str, object],
    cfg: EarningsStrategyConfig,
    output_dir: Path,
) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    signal_df = dedupe_signal_rows(signal_df)
    paths = {
        "signal_daily": output_dir / "signal_daily.csv",
        "signal_latest": output_dir / "signal_daily_latest.csv",
        "trade_log": output_dir / "trade_log.csv",
        "decision_report": output_dir / "decision_report_daily.csv",
        "equity_curve": output_dir / "equity_curve.csv",
        "strategy_eval": output_dir / "strategy_eval.csv",
        "research_overall": output_dir / "research_condition_performance.csv",
        "research_industry": output_dir / "research_condition_performance_by_industry.csv",
        "rule_overall": output_dir / "research_rule_candidates.csv",
        "rule_industry": output_dir / "research_rule_candidates_by_industry.csv",
        "rule_top": output_dir / "research_rule_candidates_top.csv",
        "strategy_meta": output_dir / "strategy_metadata.json",
    }
    signal_df.to_csv(paths["signal_daily"], index=False, encoding="utf-8-sig")
    latest_date = signal_df["date"].max() if not signal_df.empty else pd.NaT
    signal_df[signal_df["date"] == latest_date].to_csv(paths["signal_latest"], index=False, encoding="utf-8-sig")
    trade_df.to_csv(paths["trade_log"], index=False, encoding="utf-8-sig")
    decision_df.to_csv(paths["decision_report"], index=False, encoding="utf-8-sig")
    curve_df.to_csv(paths["equity_curve"], index=False, encoding="utf-8-sig")
    eval_df.to_csv(paths["strategy_eval"], index=False, encoding="utf-8-sig")
    research_overall.to_csv(paths["research_overall"], index=False, encoding="utf-8-sig")
    research_industry.to_csv(paths["research_industry"], index=False, encoding="utf-8-sig")
    rule_overall.to_csv(paths["rule_overall"], index=False, encoding="utf-8-sig")
    rule_industry.to_csv(paths["rule_industry"], index=False, encoding="utf-8-sig")
    rule_top.to_csv(paths["rule_top"], index=False, encoding="utf-8-sig")
    meta = {
        "config": asdict(cfg),
        "runtime": metadata,
        "latest_signal_date": None if pd.isna(latest_date) else str(pd.Timestamp(latest_date).date()),
    }
    paths["strategy_meta"].write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def write_operational_latest_outputs(
    signal_df: pd.DataFrame,
    decision_df: pd.DataFrame,
    state_df: pd.DataFrame,
    metadata: Dict[str, object],
    cfg: EarningsStrategyConfig,
    output_dir: Path,
) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    signal_df = dedupe_signal_rows(signal_df)
    latest_date = signal_df["date"].max() if not signal_df.empty else pd.NaT
    paths = {
        "signal_latest": output_dir / "signal_daily_latest.csv",
        "decision_report": output_dir / "decision_report_daily.csv",
        "fast_state": output_dir / "fast_position_state.csv",
        "strategy_meta": output_dir / "strategy_metadata.json",
    }
    signal_df.to_csv(paths["signal_latest"], index=False, encoding="utf-8-sig")
    decision_df.to_csv(paths["decision_report"], index=False, encoding="utf-8-sig")
    state_df.to_csv(paths["fast_state"], index=False, encoding="utf-8-sig")
    meta = {
        "config": asdict(cfg),
        "runtime": metadata,
        "latest_signal_date": None if pd.isna(latest_date) else str(pd.Timestamp(latest_date).date()),
    }
    paths["strategy_meta"].write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def default_output_dir() -> Path:
    return strategy_output_path()


def default_inputs() -> Dict[str, Path]:
    return {
        "feature": data_path("feature_daily.pkl"),
        "fundamental": data_path("fundamental_quarterly_multi.csv"),
    }


def prepare_latest_strategy_frame(
    feature_path: Path,
    fundamental_path: Path,
    cfg: EarningsStrategyConfig,
    live_quotes_path: Optional[Path] = None,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    feature_df = load_feature_dataset(feature_path)
    live_applied = False
    if live_quotes_path is not None and live_quotes_path.exists():
        feature_df, live_applied = build_live_feature_history(feature_df, live_quotes_path)
    feature_df = add_multi_timeframe_ma_features(feature_df, cfg)
    latest_date = feature_df["date"].max()
    latest_df = feature_df.loc[feature_df["date"] == latest_date].copy()
    filing_features = build_filing_features(load_fundamental_dataset(fundamental_path))
    df = merge_filing_features(latest_df, filing_features)
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    fallback_cols = {
        "filing_date_pti": "filing_date",
        "fiscal_year_pti": "bsns_year",
        "reprt_code_pti": "reprt_code",
        "revenue_pti": "revenue_q",
        "op_income_pti": "op_income_q",
        "net_income_pti": "net_income_q",
        "op_margin_pti": "op_margin_q",
        "roe_simple_pti": "roe_simple_q",
        "revenue_qoq_pti": "revenue_q_qoq",
        "op_income_qoq_pti": "op_income_q_qoq",
        "net_income_qoq_pti": "net_income_q_qoq",
    }
    for target, source in fallback_cols.items():
        if target not in df.columns and source in df.columns:
            df[target] = df[source]
    if "days_since_filing" not in df.columns and "filing_date_pti" in df.columns:
        df["days_since_filing"] = (df["date"] - pd.to_datetime(df["filing_date_pti"], errors="coerce")).dt.days

    numeric_cols = [
        "close",
        "low",
        "adv20",
        "adv20_pct_rank",
        "ret_5",
        "ret_20",
        "ret_60",
        "atr_ratio",
        "dist_month_10",
        "exposure",
        "revenue_pti",
        "op_income_pti",
        "net_income_pti",
        "op_margin_pti",
        "days_since_filing",
        "revenue_q_qoq",
        "op_income_q_qoq",
        "net_income_q_qoq",
        "op_income_q_ttm",
        "net_income_q_ttm",
        "op_income_q_vol_4q",
        "net_income_q_vol_4q",
        "net_op_gap_ratio",
        "op_income_qoq_pti",
        "net_income_qoq_pti",
        "op_income_qoq_accel",
        "net_income_qoq_accel",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["net_margin_pti"] = df["net_income_pti"] / df["revenue_pti"].replace(0, np.nan)
    df["fresh_filing"] = df["days_since_filing"].between(0, cfg.recent_filing_days)
    df["macro_gate_ok"] = df["exposure"].fillna(1.0) > cfg.riskoff_target_ratio
    df["quality_gate_ok"] = (~df["earnings_exception_flag"].fillna(False)) & (df["net_op_gap_ratio"] <= 0.35)
    df["core_candidate"] = (
        df["is_trading_day"].fillna(False)
        & (df["adv20"] >= cfg.min_adv20)
    )

    score_map = {
        "op_margin_pti": "z_op_margin",
        "net_margin_pti": "z_net_margin",
        "op_income_qoq_pti": "z_op_qoq",
        "net_income_qoq_pti": "z_net_qoq",
        "op_income_qoq_accel": "z_op_accel",
        "net_income_qoq_accel": "z_net_accel",
        "op_income_q_ttm": "z_op_ttm",
        "net_income_q_ttm": "z_net_ttm",
        "op_income_q_vol_4q": "z_op_vol",
        "net_income_q_vol_4q": "z_net_vol",
        "net_op_gap_ratio": "z_gap",
        "days_since_filing": "z_freshness",
    }
    for src, zc in score_map.items():
        if src not in df.columns:
            df[src] = np.nan
        _zscore_by_date(df, src, zc)

    df["profitability_score"] = 0.55 * df["z_op_margin"] + 0.45 * df["z_net_margin"]
    df["growth_score"] = 0.30 * df["z_op_qoq"] + 0.30 * df["z_net_qoq"] + 0.20 * df["z_op_accel"] + 0.20 * df["z_net_accel"]
    df["durability_score"] = 0.50 * df["z_op_ttm"] + 0.50 * df["z_net_ttm"]
    df["stability_score"] = -0.45 * df["z_op_vol"] - 0.35 * df["z_net_vol"] - 0.20 * df["z_gap"]
    df["freshness_score"] = -df["z_freshness"]
    df["fundamental_score"] = (
        0.32 * df["profitability_score"]
        + 0.28 * df["growth_score"]
        + 0.20 * df["durability_score"]
        + 0.12 * df["stability_score"]
        + 0.08 * df["freshness_score"]
    )
    df["ml_assist_score"] = 0.0
    df = _apply_trend_logic(df, cfg, include_ml=False)

    metadata = {
        "strategy_id": cfg.strategy_id,
        "trend_mode": cfg.trend_mode,
        "rows": int(len(df)),
        "codes": int(df["code"].nunique()),
        "date_min": str(latest_date.date()),
        "date_max": str(latest_date.date()),
        "ml_backend_used": "none",
        "fast_mode": True,
        "live_quotes_applied": live_applied,
        "live_quotes_path": None if live_quotes_path is None else str(live_quotes_path),
    }
    return df, metadata


def _fast_state_path(output_dir: Path) -> Path:
    return output_dir / "fast_position_state.csv"


def _fast_signal_path(output_dir: Path) -> Path:
    return output_dir / "signal_daily_fast_latest.csv"


def _fast_decision_path(output_dir: Path) -> Path:
    return output_dir / "decision_report_fast_latest.csv"


def _fast_meta_path(output_dir: Path) -> Path:
    return output_dir / "fast_alert_metadata.json"


def _seed_fast_state_from_trade_log(output_dir: Path, cfg: EarningsStrategyConfig) -> pd.DataFrame:
    trade_path = output_dir / "trade_log.csv"
    if not trade_path.exists():
        return pd.DataFrame(
            columns=[
                "trade_id",
                "strategy_id",
                "code",
                "name",
                "entry_date",
                "entry_price",
                "last_close",
                "hold_bars",
                "stop_pct",
                "last_eval_date",
                "state_source",
            ]
        )
    trade_df = pd.read_csv(trade_path, dtype={"code": str}, low_memory=False)
    if trade_df.empty or "status" not in trade_df.columns:
        return pd.DataFrame()
    open_df = trade_df.loc[trade_df["status"] == "OPEN"].copy()
    if open_df.empty:
        return pd.DataFrame()
    open_df["last_eval_date"] = pd.NaT
    open_df["stop_pct"] = cfg.fixed_stop_loss
    open_df["state_source"] = "fast"
    open_df["hold_bars"] = pd.to_numeric(open_df["holding_days"], errors="coerce").fillna(0).astype(int)
    open_df["last_close"] = pd.to_numeric(open_df["exit_price"], errors="coerce")
    keep = ["trade_id", "strategy_id", "code", "name", "entry_date", "entry_price", "last_close", "hold_bars", "stop_pct", "last_eval_date", "state_source"]
    return open_df[keep].copy()


def load_fast_position_state(output_dir: Path, cfg: EarningsStrategyConfig) -> pd.DataFrame:
    state_path = _fast_state_path(output_dir)
    if state_path.exists():
        state = pd.read_csv(state_path, dtype={"code": str}, low_memory=False)
    else:
        state = _seed_fast_state_from_trade_log(output_dir, cfg)
    if state.empty:
        return pd.DataFrame(
            columns=[
                "trade_id",
                "strategy_id",
                "code",
                "name",
                "entry_date",
                "entry_price",
                "last_close",
                "hold_bars",
                "stop_pct",
                "last_eval_date",
                "state_source",
            ]
        )
    state["code"] = state["code"].astype(str).str.zfill(6)
    state["trade_id"] = pd.to_numeric(state["trade_id"], errors="coerce").fillna(0).astype(int)
    state["entry_price"] = pd.to_numeric(state["entry_price"], errors="coerce")
    state["last_close"] = pd.to_numeric(state["last_close"], errors="coerce")
    state["hold_bars"] = pd.to_numeric(state["hold_bars"], errors="coerce").fillna(0).astype(int)
    state["stop_pct"] = pd.to_numeric(state["stop_pct"], errors="coerce").fillna(cfg.fixed_stop_loss)
    state["last_eval_date"] = pd.to_datetime(state["last_eval_date"], errors="coerce")
    state["state_source"] = state.get("state_source", "fast")
    state["state_source"] = state["state_source"].fillna("fast").astype(str)
    return state


def _allowed_operational_chat_ids() -> set[str]:
    raw = os.getenv("NEW_STRATEGY_TELEGRAM_BRIDGE_ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        raw = os.getenv("NEW_STRATEGY_TELEGRAM_CHAT_ID", "").strip()
    return {item.strip() for item in raw.split(",") if item.strip()}


def _load_manual_portfolio_positions(output_dir: Path) -> pd.DataFrame:
    positions_path = output_dir / "telegram_bridge" / "manual_portfolio_positions.csv"
    if not positions_path.exists():
        return pd.DataFrame()
    try:
        positions = pd.read_csv(positions_path, dtype={"chat_id": str, "code": str}, low_memory=False)
    except Exception:
        return pd.DataFrame()
    if positions.empty or "code" not in positions.columns:
        return pd.DataFrame()
    positions["code"] = positions["code"].astype(str).str.zfill(6)
    allowed_chat_ids = _allowed_operational_chat_ids()
    if allowed_chat_ids and "chat_id" in positions.columns:
        positions = positions[positions["chat_id"].astype(str).isin(allowed_chat_ids)].copy()
    if "quantity" in positions.columns:
        qty = pd.to_numeric(positions["quantity"], errors="coerce").fillna(0.0)
        positions = positions[qty > 0].copy()
    return positions.reset_index(drop=True)


def _calendar_hold_bars(entry_dt: pd.Timestamp, eval_dt: pd.Timestamp) -> int:
    if pd.isna(entry_dt):
        return 0
    try:
        return max(0, int((pd.Timestamp(eval_dt).normalize() - pd.Timestamp(entry_dt).normalize()).days))
    except Exception:
        return 0


def _reconcile_manual_positions(
    positions: Dict[str, Dict[str, object]],
    today: pd.DataFrame,
    output_dir: Path,
    cfg: EarningsStrategyConfig,
    dt: pd.Timestamp,
    next_trade_id: int,
) -> int:
    manual_positions = _load_manual_portfolio_positions(output_dir)
    if manual_positions.empty:
        return next_trade_id

    for _, row in manual_positions.iterrows():
        code = str(row.get("code", "")).zfill(6)
        if not code or code in EXCLUDED_SECURITY_CODES:
            continue
        avg_price = _coerce_float(row.get("avg_price"))
        if not np.isfinite(avg_price) or avg_price <= 0:
            continue
        entry_dt = pd.to_datetime(row.get("last_trade_at"), errors="coerce")
        if pd.isna(entry_dt):
            entry_dt = pd.to_datetime(row.get("updated_at"), errors="coerce")
        if pd.isna(entry_dt):
            entry_dt = dt
        existing = positions.get(code, {})
        trade_id = int(existing.get("trade_id", 0) or 0)
        if trade_id <= 0:
            trade_id = next_trade_id
            next_trade_id += 1
        live_close = _coerce_float(today.at[code, "close"]) if code in today.index else float("nan")
        existing_close = _coerce_float(existing.get("last_close"))
        last_close = live_close if np.isfinite(live_close) else existing_close
        if not np.isfinite(last_close):
            last_close = avg_price
        existing_hold_bars = int(existing.get("hold_bars", 0) or 0)
        hold_bars = max(existing_hold_bars, _calendar_hold_bars(entry_dt, dt))
        positions[code] = {
            "trade_id": trade_id,
            "strategy_id": cfg.strategy_id,
            "code": code,
            "name": str(row.get("name") or existing.get("name") or (today.at[code, "name"] if code in today.index else code)),
            "entry_date": entry_dt,
            "entry_price": float(avg_price),
            "last_close": float(last_close),
            "hold_bars": int(hold_bars),
            "stop_pct": float(existing.get("stop_pct", cfg.fixed_stop_loss) or cfg.fixed_stop_loss),
            "last_eval_date": pd.to_datetime(existing.get("last_eval_date"), errors="coerce"),
            "state_source": "manual",
        }
    return next_trade_id


def _alert_trace_fields(
    row: pd.Series,
    cfg: EarningsStrategyConfig,
    *,
    position: Dict[str, object] | None = None,
    effective_stop_price: float | None = None,
    exit_reason: str = "",
) -> Dict[str, object]:
    weekly_ma = _coerce_float(row.get("v2_week_ma"))
    monthly_ma = _coerce_float(row.get("v2_month_ma"))
    current_price = _coerce_float(row.get("close"))
    safe_low = _safe_low_for_stop(row, current_price)
    entry_price = _coerce_float(position.get("entry_price")) if position else _coerce_float(row.get("close"))
    stop_price = _coerce_float(effective_stop_price)
    if not np.isfinite(stop_price) and np.isfinite(entry_price):
        stop_price = float(entry_price * (1.0 + cfg.fixed_stop_loss))
    weekly_trigger_price = float("nan")
    if np.isfinite(weekly_ma):
        weekly_trigger_price = weekly_ma * (1.0 + cfg.weekly_sell_threshold)
    return {
        "alert_quote_time": row.get("quote_time"),
        "alert_current_price": current_price,
        "alert_low_price": safe_low,
        "alert_low_price_raw": _coerce_float(row.get("low")),
        "alert_entry_price": entry_price,
        "alert_stop_loss_price": stop_price,
        "alert_weekly_ma": weekly_ma,
        "alert_weekly_trigger_price": weekly_trigger_price,
        "alert_monthly_ma": monthly_ma,
        "alert_exit_reason": str(exit_reason or ""),
        "alert_position_source": str((position or {}).get("state_source", "")),
    }


def simulate_fast_alert_cycle(
    latest_df: pd.DataFrame,
    cfg: EarningsStrategyConfig,
    output_dir: Path,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, object]]:
    today = latest_df.sort_values("code").copy()
    today["code"] = today["code"].astype(str).str.zfill(6)
    today = today[~today["code"].isin(EXCLUDED_SECURITY_CODES)]
    today = today.set_index("code")
    dt = pd.Timestamp(today["date"].iloc[0])
    exposure, regime = _resolve_macro_context(today, dt)
    target_positions = _target_positions(exposure, cfg)
    trend_mode = str(cfg.trend_mode or "optimal_ma_v2").strip().lower()

    state_df = load_fast_position_state(output_dir, cfg)
    positions: Dict[str, Dict[str, object]] = {}
    next_trade_id = 1
    if not state_df.empty:
        next_trade_id = int(state_df["trade_id"].max()) + 1
        for _, row in state_df.iterrows():
            code = str(row["code"]).zfill(6)
            if code in EXCLUDED_SECURITY_CODES:
                continue
            payload = row.to_dict()
            payload.setdefault("state_source", "fast")
            positions[code] = payload
    next_trade_id = _reconcile_manual_positions(positions, today, output_dir, cfg, dt, next_trade_id)

    signal_rows: List[Dict[str, object]] = []
    decision_rows: List[Dict[str, object]] = []
    state_rows: List[Dict[str, object]] = []
    trade_events: List[Dict[str, object]] = []

    buy_count = sell_count = hold_count = watch_count = 0
    buy_codes: List[str] = []
    sell_codes: List[str] = []
    watch_codes: List[str] = []
    to_remove: List[str] = []

    for code, pos in list(positions.items()):
        last_eval_date = pd.to_datetime(pos.get("last_eval_date"), errors="coerce")
        hold_bars = int(pos.get("hold_bars", 0))
        if pd.isna(last_eval_date) or last_eval_date.date() < dt.date():
            hold_bars += 1
        pos["hold_bars"] = hold_bars

        if code not in today.index:
            realized_return = float(pos["last_close"]) / float(pos["entry_price"]) - 1.0 if pd.notna(pos.get("last_close")) else np.nan
            row = pd.Series({"name": pos.get("name", code), "industry": "", "conviction_score": 0.0})
            row["_exit_reason"] = "missing_price_row"
            row["_realized_return"] = realized_return
            reason_1, reason_2, reason_3 = _row_reasons(row, "SELL")
            signal_rows.append(
                {
                    "date": dt,
                    "code": code,
                    "name": pos.get("name", code),
                    "industry": "",
                    "signal": "SELL",
                    "strategy_id": cfg.strategy_id,
                    "conviction_score": 0.0,
                    "holding_horizon": "중기(2~6개월)",
                    "reason_1": reason_1,
                    "reason_2": reason_2,
                    "reason_3": reason_3,
                    "risk_flag": "missing_price_row",
                    "stop_rule": f"{cfg.fixed_stop_loss:.0%}",
                    "target_exit_rule": "가격데이터 누락",
                    **_execution_plan_fields(row, "SELL"),
                    **_signal_context_fields(row),
                    **_alert_trace_fields(row, cfg, position=pos, exit_reason="missing_price_row"),
                }
            )
            sell_count += 1
            sell_codes.append(code)
            to_remove.append(code)
            trade_events.append(
                {
                    "trade_id": int(pos["trade_id"]),
                    "strategy_id": cfg.strategy_id,
                    "code": code,
                    "name": pos.get("name", code),
                    "entry_date": pos.get("entry_date"),
                    "exit_date": dt,
                    "entry_price": pos.get("entry_price"),
                    "exit_price": pos.get("last_close"),
                    "holding_days": hold_bars,
                    "realized_return": realized_return,
                    "exit_reason": "missing_price_row",
                    "status": "CLOSED",
                }
            )
            continue

        row = today.loc[code]
        close = float(row["close"])
        low = _safe_low_for_stop(row, close)
        pos["last_close"] = close
        effective_stop_price = _effective_stop_price(row, pos)
        stop_hit = bool(np.isfinite(low) and low <= effective_stop_price)
        timing_break = bool(_trend_break(row, cfg))
        sell_signal = stop_hit or timing_break

        if sell_signal:
            exit_price = effective_stop_price if stop_hit else close
            realized_return = exit_price / float(pos["entry_price"]) - 1.0
            if stop_hit:
                exit_reason = "stop_loss"
            else:
                exit_reason = "timing_break"
            sell_row = row.copy()
            sell_row["_exit_reason"] = exit_reason
            sell_row["_realized_return"] = realized_return
            reason_1, reason_2, reason_3 = _row_reasons(sell_row, "SELL")
            signal_rows.append(
                {
                    "date": dt,
                    "code": code,
                    "name": row["name"],
                    "industry": row["industry"],
                    "signal": "SELL",
                    "strategy_id": cfg.strategy_id,
                    "conviction_score": float(row["conviction_score"]),
                    "holding_horizon": "중기(2~6개월)",
                    "reason_1": reason_1,
                    "reason_2": reason_2,
                    "reason_3": reason_3,
                    "risk_flag": _risk_flag(row),
                    "stop_rule": f"{cfg.fixed_stop_loss:.0%}",
                    "target_exit_rule": "초기손절/원금보호/품질/타이밍",
                    **_execution_plan_fields(sell_row, "SELL"),
                    **_signal_context_fields(sell_row),
                    **_alert_trace_fields(sell_row, cfg, position=pos, effective_stop_price=effective_stop_price, exit_reason=exit_reason),
                }
            )
            sell_count += 1
            sell_codes.append(code)
            to_remove.append(code)
            trade_events.append(
                {
                    "trade_id": int(pos["trade_id"]),
                    "strategy_id": cfg.strategy_id,
                    "code": code,
                    "name": row["name"],
                    "entry_date": pos.get("entry_date"),
                    "exit_date": dt,
                    "entry_price": pos.get("entry_price"),
                    "exit_price": exit_price,
                    "holding_days": hold_bars,
                    "realized_return": realized_return,
                    "exit_reason": exit_reason,
                    "status": "CLOSED",
                }
            )

    for code in to_remove:
        positions.pop(code, None)

    candidates = _sort_candidates_by_ma_state(today[today["buy_candidate"]])
    slots = max(0, target_positions - len(positions))
    if slots > 0:
        for code, row in candidates.iterrows():
            if slots <= 0:
                break
            if code in positions:
                continue
            positions[code] = {
                "trade_id": next_trade_id,
                "strategy_id": cfg.strategy_id,
                "code": code,
                "name": row["name"],
                "entry_date": dt,
                "entry_price": float(row["close"]),
                "last_close": float(row["close"]),
                "hold_bars": 0,
                "stop_pct": cfg.fixed_stop_loss,
                "last_eval_date": dt,
                "state_source": "fast",
            }
            next_trade_id += 1
            reason_1, reason_2, reason_3 = _row_reasons(row, "BUY")
            signal_rows.append(
                {
                    "date": dt,
                    "code": code,
                    "name": row["name"],
                    "industry": row["industry"],
                    "signal": "BUY",
                    "strategy_id": cfg.strategy_id,
                    "conviction_score": float(row["conviction_score"]),
                    "holding_horizon": "중기(2~6개월)",
                    "reason_1": reason_1,
                    "reason_2": reason_2,
                    "reason_3": reason_3,
                    "risk_flag": _risk_flag(row),
                    "stop_rule": f"{cfg.fixed_stop_loss:.0%}",
                    "target_exit_rule": "품질 유지 + 타이밍 양호 시 보유",
                    **_execution_plan_fields(row, "BUY"),
                    **_signal_context_fields(row),
                    **_alert_trace_fields(row, cfg, position=positions[code]),
                }
            )
            buy_count += 1
            buy_codes.append(code)
            trade_events.append(
                {
                    "trade_id": int(positions[code]["trade_id"]),
                    "strategy_id": cfg.strategy_id,
                    "code": code,
                    "name": row["name"],
                    "entry_date": dt,
                    "exit_date": pd.NaT,
                    "entry_price": float(row["close"]),
                    "exit_price": float(row["close"]),
                    "holding_days": 0,
                    "realized_return": 0.0,
                    "exit_reason": "",
                    "status": "OPEN",
                }
            )
            slots -= 1

    for code in list(positions.keys()):
        if code not in today.index or code in buy_codes or code in sell_codes:
            continue
        row = today.loc[code]
        reason_1, reason_2, reason_3 = _row_reasons(row, "HOLD")
        signal_rows.append(
            {
                "date": dt,
                "code": code,
                "name": row["name"],
                "industry": row["industry"],
                "signal": "HOLD",
                "strategy_id": cfg.strategy_id,
                "conviction_score": float(row["conviction_score"]),
                "holding_horizon": "중기(2~6개월)",
                "reason_1": reason_1,
                "reason_2": reason_2,
                "reason_3": reason_3,
                "risk_flag": _risk_flag(row),
                "stop_rule": f"{cfg.fixed_stop_loss:.0%}",
                "target_exit_rule": "품질 유지 + 타이밍 양호 시 보유",
                **_execution_plan_fields(row, "HOLD"),
                **_signal_context_fields(row),
                **_alert_trace_fields(row, cfg, position=positions[code]),
            }
        )
        hold_count += 1

    watch_candidates = _sort_candidates_by_ma_state(today[today["watch_candidate"]])
    watch_candidates = watch_candidates[~watch_candidates.index.isin(positions.keys())].head(cfg.watchlist_size)
    for code, row in watch_candidates.iterrows():
        reason_1, reason_2, reason_3 = _row_reasons(row, "WATCH")
        signal_rows.append(
            {
                "date": dt,
                "code": code,
                "name": row["name"],
                "industry": row["industry"],
                "signal": "WATCH",
                "strategy_id": cfg.strategy_id,
                "conviction_score": float(row["conviction_score"]),
                "holding_horizon": "관찰",
                "reason_1": reason_1,
                "reason_2": reason_2,
                "reason_3": reason_3,
                "risk_flag": _risk_flag(row),
                "stop_rule": "",
                "target_exit_rule": "기존 코어점수 + 타이밍 확인 후 편입",
                **_execution_plan_fields(row, "WATCH"),
                **_signal_context_fields(row),
                **_alert_trace_fields(row, cfg),
            }
        )
        watch_count += 1
        watch_codes.append(code)

    for code, pos in positions.items():
        pos["last_eval_date"] = dt
        state_rows.append(
            {
                "trade_id": int(pos["trade_id"]),
                "strategy_id": cfg.strategy_id,
                "code": code,
                "name": pos["name"],
                "entry_date": pos["entry_date"],
                "entry_price": float(pos["entry_price"]),
                "last_close": float(pos["last_close"]),
                "hold_bars": int(pos["hold_bars"]),
                "stop_pct": float(pos["stop_pct"]),
                "last_eval_date": dt,
                "state_source": str(pos.get("state_source", "fast")),
            }
        )

    decision_rows.append(
        {
            "date": dt,
            "strategy_id": cfg.strategy_id,
            "market_regime": regime,
            "exposure": exposure,
            "target_positions": target_positions,
            "positions_after": len(positions),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hold_count": hold_count,
            "watch_count": watch_count,
            "buy_codes": ",".join(buy_codes),
            "sell_codes": ",".join(sell_codes),
            "watch_codes": ",".join(watch_codes),
            "summary_text": f"regime={regime}, exposure={exposure:.2f}, buy={buy_count}, sell={sell_count}, hold={hold_count}, watch={watch_count}",
        }
    )

    signal_df = pd.DataFrame(signal_rows).sort_values(["signal", "code"], ascending=[True, True]).reset_index(drop=True)
    decision_df = pd.DataFrame(decision_rows)
    if state_rows:
        state_df_out = pd.DataFrame(state_rows).sort_values(["entry_date", "trade_id"]).reset_index(drop=True)
    else:
        state_df_out = pd.DataFrame(
            columns=[
                "trade_id",
                "strategy_id",
                "code",
                "name",
                "entry_date",
                "entry_price",
                "last_close",
                "hold_bars",
                "stop_pct",
                "last_eval_date",
                "state_source",
            ]
        )
    metadata = {
        "strategy_id": cfg.strategy_id,
        "latest_signal_date": str(dt.date()),
        "rows": int(len(today)),
        "positions_after": int(len(positions)),
        "trade_events": int(len(trade_events)),
        "fast_mode": True,
    }
    return signal_df, decision_df, state_df_out, metadata


def write_fast_alert_outputs(
    signal_df: pd.DataFrame,
    decision_df: pd.DataFrame,
    state_df: pd.DataFrame,
    metadata: Dict[str, object],
    output_dir: Path,
) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    signal_df = dedupe_signal_rows(signal_df)
    paths = {
        "signal_fast_latest": _fast_signal_path(output_dir),
        "decision_fast_latest": _fast_decision_path(output_dir),
        "fast_state": _fast_state_path(output_dir),
        "fast_meta": _fast_meta_path(output_dir),
    }
    signal_df.to_csv(paths["signal_fast_latest"], index=False, encoding="utf-8-sig")
    decision_df.to_csv(paths["decision_fast_latest"], index=False, encoding="utf-8-sig")
    state_df.to_csv(paths["fast_state"], index=False, encoding="utf-8-sig")
    paths["fast_meta"].write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


