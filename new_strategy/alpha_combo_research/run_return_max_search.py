from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable

import pandas as pd

from new_strategy.paths import data_path, output_path


FEATURE_PATH = data_path("feature_daily.pkl")
PRICE_PATH = data_path("price_panel.csv")
OPTIMAL_MA_PATH = output_path(
    "ma_breakout_research",
    "published",
    "optimal_ma_selection_monthly_weekly.csv",
)
OUTPUT_DIR = output_path("alpha_combo_research")
HORIZONS = [5, 20, 60]


@dataclass(frozen=True)
class ConditionSpec:
    name: str
    label: str
    mask: pd.Series


def _normalize_code(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.upper().str.strip()
    return text.where(~text.str.fullmatch(r"\d+"), text.str.zfill(6))


def load_forward_returns() -> pd.DataFrame:
    price = pd.read_csv(PRICE_PATH, usecols=["date", "code", "close"], dtype={"code": str}, low_memory=False)
    price["code"] = _normalize_code(price["code"])
    price["date"] = pd.to_datetime(price["date"], errors="coerce")
    price["close"] = pd.to_numeric(price["close"], errors="coerce")
    price = price.dropna(subset=["date", "close"]).sort_values(["code", "date"]).reset_index(drop=True)
    grouped = price.groupby("code", sort=False)
    out = price[["code", "date"]].copy()
    for horizon in HORIZONS:
        out[f"fwd_ret_{horizon}d"] = grouped["close"].shift(-horizon) / price["close"] - 1.0
    return out


def load_base_frame() -> pd.DataFrame:
    use_cols = [
        "date",
        "code",
        "name",
        "industry",
        "market_cap",
        "days_since_filing",
        "op_margin_pti",
        "ret_5",
        "atr_ratio",
        "dist_ma_mid",
        "gold_kr_close",
        "vix",
        "usdkrw",
        "us10y",
        "kr10y",
    ]
    feature = pd.read_pickle(FEATURE_PATH)
    feature = feature[use_cols].copy()
    feature["code"] = _normalize_code(feature["code"])
    feature["date"] = pd.to_datetime(feature["date"], errors="coerce")
    feature = feature.dropna(subset=["date", "code"]).copy()
    feature["days_since_filing"] = pd.to_numeric(feature["days_since_filing"], errors="coerce")
    feature = feature[feature["days_since_filing"].between(0, 90, inclusive="both")].copy()

    fwd = load_forward_returns()
    df = feature.merge(fwd, on=["code", "date"], how="left")

    if OPTIMAL_MA_PATH.exists():
        optimal = pd.read_csv(OPTIMAL_MA_PATH, dtype={"code": str}, low_memory=False)
        optimal["code"] = _normalize_code(optimal["code"])
        for col in ["ma_window", "excess_return", "annualized_return", "max_drawdown", "win_rate"]:
            if col in optimal.columns:
                optimal[col] = pd.to_numeric(optimal[col], errors="coerce")
        df = df.merge(
            optimal[
                [
                    "code",
                    "ma_timeframe",
                    "action_mode",
                    "ma_window",
                    "excess_return",
                    "annualized_return",
                    "max_drawdown",
                    "win_rate",
                ]
            ],
            on="code",
            how="left",
        )
    return df


def _quantile_bounds(series: pd.Series) -> tuple[float, float]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return float("nan"), float("nan")
    return float(clean.quantile(0.3)), float(clean.quantile(0.7))


def build_conditions(df: pd.DataFrame, top_industries: Iterable[str]) -> list[ConditionSpec]:
    specs: list[ConditionSpec] = []
    market_low, market_high = _quantile_bounds(df["market_cap"])
    gold_low, gold_high = _quantile_bounds(df["gold_kr_close"])
    vix_low, vix_high = _quantile_bounds(df["vix"])
    usd_low, usd_high = _quantile_bounds(df["usdkrw"])
    us10y_low, us10y_high = _quantile_bounds(df["us10y"])

    def add(name: str, label: str, mask: pd.Series) -> None:
        clean_mask = mask.fillna(False)
        df[f"cond__{name}"] = clean_mask.astype(bool)
        specs.append(ConditionSpec(name=name, label=label, mask=clean_mask))

    add("filing_30", "공시 30일 이내", df["days_since_filing"].le(30))
    add("filing_60", "공시 60일 이내", df["days_since_filing"].le(60))
    add("op_margin_pos", "영업이익률 양수", pd.to_numeric(df["op_margin_pti"], errors="coerce").gt(0))
    add("op_margin_5p", "영업이익률 5% 이상", pd.to_numeric(df["op_margin_pti"], errors="coerce").ge(0.05))
    add("op_margin_10p", "영업이익률 10% 이상", pd.to_numeric(df["op_margin_pti"], errors="coerce").ge(0.10))
    add("ret5_pos", "최근 5일 수익률 양수", pd.to_numeric(df["ret_5"], errors="coerce").gt(0))
    add("ret5_cool", "최근 5일 과열 아님", pd.to_numeric(df["ret_5"], errors="coerce").between(-0.02, 0.12, inclusive="both"))
    add("atr_calm", "ATR 비율 0.10 이하", pd.to_numeric(df["atr_ratio"], errors="coerce").le(0.10))
    add("atr_very_calm", "ATR 비율 0.08 이하", pd.to_numeric(df["atr_ratio"], errors="coerce").le(0.08))
    add("dist_mid_ok", "중기 이평 이격 0.18 이하", pd.to_numeric(df["dist_ma_mid"], errors="coerce").le(0.18))
    add("dist_mid_tight", "중기 이평 이격 0.10 이하", pd.to_numeric(df["dist_ma_mid"], errors="coerce").le(0.10))
    add("cap_large", "시총 상위 30%", pd.to_numeric(df["market_cap"], errors="coerce").ge(market_high))
    add("cap_small", "시총 하위 30%", pd.to_numeric(df["market_cap"], errors="coerce").le(market_low))
    add("gold_high", "금 가격 상위 30%", pd.to_numeric(df["gold_kr_close"], errors="coerce").ge(gold_high))
    add("gold_low", "금 가격 하위 30%", pd.to_numeric(df["gold_kr_close"], errors="coerce").le(gold_low))
    add("vix_low", "VIX 하위 30%", pd.to_numeric(df["vix"], errors="coerce").le(vix_low))
    add("vix_high", "VIX 상위 30%", pd.to_numeric(df["vix"], errors="coerce").ge(vix_high))
    add("usdkrw_low", "환율 하위 30%", pd.to_numeric(df["usdkrw"], errors="coerce").le(usd_low))
    add("usdkrw_high", "환율 상위 30%", pd.to_numeric(df["usdkrw"], errors="coerce").ge(usd_high))
    add("us10y_low", "미국 10년 금리 하위 30%", pd.to_numeric(df["us10y"], errors="coerce").le(us10y_low))
    add("us10y_high", "미국 10년 금리 상위 30%", pd.to_numeric(df["us10y"], errors="coerce").ge(us10y_high))
    add("ma_monthly", "최적 MA 월봉", df["ma_timeframe"].astype(str).str.lower().eq("monthly"))
    add("ma_weekly", "최적 MA 주봉", df["ma_timeframe"].astype(str).str.lower().eq("weekly"))
    add("ma_native", "최적 MA 봉마감형", df["action_mode"].astype(str).eq("native_timeframe_close"))
    add("ma_daily_action", "최적 MA 일별판정형", df["action_mode"].astype(str).eq("daily_close_action"))
    add("ma_window_short", "최적 MA 20 이하", pd.to_numeric(df["ma_window"], errors="coerce").le(20))
    add("ma_window_mid", "최적 MA 21~50", pd.to_numeric(df["ma_window"], errors="coerce").between(21, 50, inclusive="both"))
    add("ma_window_long", "최적 MA 51 이상", pd.to_numeric(df["ma_window"], errors="coerce").ge(51))

    for industry in top_industries:
        add(f"industry::{industry}", f"업종 {industry}", df["industry"].astype(str).eq(industry))
    return specs


def evaluate_conditions(
    df: pd.DataFrame,
    conditions: list[ConditionSpec],
    *,
    min_obs: int,
    max_pairwise: int,
) -> pd.DataFrame:
    results: list[dict[str, object]] = []
    pair_candidates = conditions[:max_pairwise]
    for horizon in HORIZONS:
        target_col = f"fwd_ret_{horizon}d"
        valid_target = pd.to_numeric(df[target_col], errors="coerce")
        valid_mask = valid_target.notna()

        def record(names: list[str], labels: list[str], mask: pd.Series) -> None:
            final_mask = valid_mask & mask
            obs = int(final_mask.sum())
            if obs < min_obs:
                return
            values = valid_target[final_mask]
            results.append(
                {
                    "horizon_days": horizon,
                    "condition_count": len(names),
                    "condition_names": " + ".join(names),
                    "condition_labels": " + ".join(labels),
                    "obs": obs,
                    "mean_return": float(values.mean()),
                    "median_return": float(values.median()),
                    "win_rate": float((values > 0).mean()),
                    "p10_return": float(values.quantile(0.10)),
                    "p90_return": float(values.quantile(0.90)),
                    "score": float(values.mean() * 100 + (values > 0).mean() * 5),
                }
            )

        for condition in conditions:
            record([condition.name], [condition.label], condition.mask)
        for left, right in combinations(pair_candidates, 2):
            record(
                [left.name, right.name],
                [left.label, right.label],
                left.mask & right.mask,
            )
    out = pd.DataFrame(results)
    if out.empty:
        return out
    return out.sort_values(
        ["horizon_days", "score", "mean_return", "win_rate", "obs"],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)


def summarize_by_group(df: pd.DataFrame, results: pd.DataFrame, group_col: str, *, min_obs: int) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()
    top_results = results[results["horizon_days"] == 20].head(25).copy()
    summaries: list[dict[str, object]] = []
    for group_value, group_df in df.groupby(group_col, dropna=True):
        if len(group_df) < min_obs:
            continue
        target = pd.to_numeric(group_df["fwd_ret_20d"], errors="coerce")
        valid = target.notna()
        if int(valid.sum()) < min_obs:
            continue
        best_row = None
        for _, combo in top_results.iterrows():
            names = str(combo["condition_names"]).split(" + ")
            mask = pd.Series(True, index=group_df.index)
            for name in names:
                col = f"cond__{name}"
                if col in group_df.columns:
                    mask = mask & group_df[col].astype(bool)
            obs = int((valid & mask).sum())
            if obs < max(3, min_obs // 4):
                continue
            values = target[valid & mask]
            candidate = {
                "group": str(group_value),
                "condition_names": combo["condition_names"],
                "condition_labels": combo["condition_labels"],
                "obs": obs,
                "mean_return": float(values.mean()),
                "win_rate": float((values > 0).mean()),
            }
            if best_row is None or candidate["mean_return"] > best_row["mean_return"]:
                best_row = candidate
        if best_row is not None:
            summaries.append(best_row)
    return pd.DataFrame(summaries).sort_values(["mean_return", "win_rate", "obs"], ascending=[False, False, False]).reset_index(drop=True)


def summarize_by_stock(df: pd.DataFrame, results: pd.DataFrame, *, min_stock_obs: int) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()
    top_results = results[results["horizon_days"] == 20].head(25).copy()
    summaries: list[dict[str, object]] = []
    for code, group_df in df.groupby("code", dropna=True):
        target = pd.to_numeric(group_df["fwd_ret_20d"], errors="coerce")
        if int(target.notna().sum()) < min_stock_obs:
            continue
        best_row = None
        for _, combo in top_results.iterrows():
            names = str(combo["condition_names"]).split(" + ")
            mask = pd.Series(True, index=group_df.index)
            for name in names:
                col = f"cond__{name}"
                if col in group_df.columns:
                    mask = mask & group_df[col].astype(bool)
            obs = int((target.notna() & mask).sum())
            if obs < min_stock_obs:
                continue
            values = target[target.notna() & mask]
            candidate = {
                "code": code,
                "name": str(group_df["name"].dropna().iloc[-1]) if group_df["name"].notna().any() else code,
                "condition_names": combo["condition_names"],
                "condition_labels": combo["condition_labels"],
                "obs": obs,
                "mean_return": float(values.mean()),
                "win_rate": float((values > 0).mean()),
            }
            if best_row is None or candidate["mean_return"] > best_row["mean_return"]:
                best_row = candidate
        if best_row is not None:
            summaries.append(best_row)
    return pd.DataFrame(summaries).sort_values(["mean_return", "win_rate", "obs"], ascending=[False, False, False]).reset_index(drop=True)


def write_outputs(
    df: pd.DataFrame,
    results: pd.DataFrame,
    industry_summary: pd.DataFrame,
    stock_summary: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(OUTPUT_DIR / "global_combo_results.csv", index=False, encoding="utf-8-sig")
    industry_summary.to_csv(OUTPUT_DIR / "industry_best_combos_20d.csv", index=False, encoding="utf-8-sig")
    stock_summary.to_csv(OUTPUT_DIR / "stock_best_combos_20d.csv", index=False, encoding="utf-8-sig")

    meta = {
        "created_at": pd.Timestamp.now().isoformat(),
        "feature_path": str(FEATURE_PATH),
        "price_path": str(PRICE_PATH),
        "optimal_ma_path": str(OPTIMAL_MA_PATH),
        "rows": int(len(df)),
        "stocks": int(df["code"].nunique()),
        "min_obs": int(args.min_obs),
        "top_industries": int(args.top_industries),
        "max_pairwise": int(args.max_pairwise),
    }
    (OUTPUT_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    top20 = results[results["horizon_days"] == 20].head(20)
    lines = [
        "# Alpha Combo Research",
        "",
        f"- rows: {len(df):,}",
        f"- stocks: {df['code'].nunique():,}",
        f"- min_obs: {args.min_obs}",
        "",
        "## Top 20 combos by 20-day forward return",
    ]
    if top20.empty:
        lines.append("- no results")
    else:
        for _, row in top20.iterrows():
            lines.append(
                f"- {row['condition_labels']} | obs {int(row['obs'])} | mean {float(row['mean_return']):+.2%} | win {float(row['win_rate']):.2%}"
            )
    lines.extend(
        [
            "",
            "## Files",
            "- global_combo_results.csv",
            "- industry_best_combos_20d.csv",
            "- stock_best_combos_20d.csv",
            "- meta.json",
        ]
    )
    (OUTPUT_DIR / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-obs", type=int, default=250)
    parser.add_argument("--top-industries", type=int, default=12)
    parser.add_argument("--max-pairwise", type=int, default=18)
    parser.add_argument("--min-stock-obs", type=int, default=3)
    args = parser.parse_args()

    df = load_base_frame()
    top_industries = (
        df["industry"]
        .astype(str)
        .value_counts()
        .head(args.top_industries)
        .index
        .tolist()
    )
    conditions = build_conditions(df, top_industries)
    results = evaluate_conditions(df, conditions, min_obs=args.min_obs, max_pairwise=args.max_pairwise)
    industry_summary = summarize_by_group(df, results, "industry", min_obs=max(60, args.min_obs // 2))
    stock_summary = summarize_by_stock(df, results, min_stock_obs=args.min_stock_obs)
    write_outputs(df, results, industry_summary, stock_summary, args)


if __name__ == "__main__":
    main()
