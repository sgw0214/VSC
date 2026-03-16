import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from new_strategy.paths import data_path, output_path
from new_strategy.legacy_analysis.analyze_stock_correlations import TARGET_WINDOWS, add_forward_returns, load_feature_dataset


CORR_FEATURES = [
    "op_income_yoy_pct_pti",
    "net_income_yoy_pct_pti",
    "op_income_qoq_pct_pti",
    "net_income_qoq_pct_pti",
    "op_margin_pti",
    "revenue_yoy_pct_pti",
    "op_income_yoy_pct_period",
    "net_income_yoy_pct_period",
    "op_income_qoq_pct_period",
    "net_income_qoq_pct_period",
]


def add_profit_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Infer previous comparable values from delta columns already present in feature_daily.
    out["op_income_prev_y"] = pd.to_numeric(out["op_income_pti"], errors="coerce") - pd.to_numeric(
        out["op_income_yoy_pti"], errors="coerce"
    )
    out["net_income_prev_y"] = pd.to_numeric(out["net_income_pti"], errors="coerce") - pd.to_numeric(
        out["net_income_yoy_pti"], errors="coerce"
    )
    out["op_income_prev_q"] = pd.to_numeric(out["op_income_pti"], errors="coerce") - pd.to_numeric(
        out["op_income_qoq_pti"], errors="coerce"
    )
    out["net_income_prev_q"] = pd.to_numeric(out["net_income_pti"], errors="coerce") - pd.to_numeric(
        out["net_income_qoq_pti"], errors="coerce"
    )

    # Separate flags for later industry-specific rule choice.
    out["flag_op_turnaround"] = (out["op_income_pti"] > 0) & (out["op_income_prev_y"] <= 0)
    out["flag_net_turnaround"] = (out["net_income_pti"] > 0) & (out["net_income_prev_y"] <= 0)
    out["flag_op_2q_positive"] = (out["op_income_pti"] > 0) & (out["op_income_prev_q"] > 0)
    out["flag_net_2q_positive"] = (out["net_income_pti"] > 0) & (out["net_income_prev_q"] > 0)

    out["flag_any_turnaround"] = out["flag_op_turnaround"] | out["flag_net_turnaround"]
    out["flag_any_2q_positive"] = out["flag_op_2q_positive"] | out["flag_net_2q_positive"]
    return out


def industry_corr(df: pd.DataFrame, min_obs: int) -> pd.DataFrame:
    rows = []
    features = [c for c in CORR_FEATURES if c in df.columns]
    for industry, g in df.groupby("industry", dropna=False):
        if pd.isna(industry):
            continue
        n_codes = int(g["code"].nunique())
        for w in TARGET_WINDOWS:
            target = f"fwd_ret_{w}d"
            for feat in features:
                pair = g[[feat, target]].apply(pd.to_numeric, errors="coerce").dropna()
                if len(pair) < min_obs:
                    continue
                corr = pair[feat].corr(pair[target])
                rows.append(
                    {
                        "industry": industry,
                        "target": target,
                        "feature": feat,
                        "corr": float(corr) if pd.notna(corr) else np.nan,
                        "abs_corr": float(abs(corr)) if pd.notna(corr) else np.nan,
                        "n_obs": int(len(pair)),
                        "n_codes": n_codes,
                    }
                )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["industry", "target", "abs_corr"], ascending=[True, True, False]).reset_index(drop=True)
    return out


def industry_flag_performance(df: pd.DataFrame, min_obs: int) -> pd.DataFrame:
    flag_cols = [
        "flag_op_turnaround",
        "flag_net_turnaround",
        "flag_op_2q_positive",
        "flag_net_2q_positive",
        "flag_any_turnaround",
        "flag_any_2q_positive",
    ]
    rows = []
    for industry, g in df.groupby("industry", dropna=False):
        if pd.isna(industry):
            continue
        n_codes = int(g["code"].nunique())
        for w in TARGET_WINDOWS:
            target = f"fwd_ret_{w}d"
            for flag in flag_cols:
                tmp = g[[flag, target]].copy()
                tmp[flag] = tmp[flag].fillna(False).astype(bool)
                tmp[target] = pd.to_numeric(tmp[target], errors="coerce")
                pos = tmp[tmp[flag]].dropna(subset=[target])
                neg = tmp[~tmp[flag]].dropna(subset=[target])
                if len(pos) < min_obs or len(neg) < min_obs:
                    continue
                rows.append(
                    {
                        "industry": industry,
                        "target": target,
                        "flag": flag,
                        "n_codes": n_codes,
                        "n_true": int(len(pos)),
                        "n_false": int(len(neg)),
                        "mean_true": float(pos[target].mean()),
                        "mean_false": float(neg[target].mean()),
                        "median_true": float(pos[target].median()),
                        "median_false": float(neg[target].median()),
                        "win_rate_true": float((pos[target] > 0).mean()),
                        "win_rate_false": float((neg[target] > 0).mean()),
                        "mean_diff": float(pos[target].mean() - neg[target].mean()),
                        "median_diff": float(pos[target].median() - neg[target].median()),
                    }
                )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["industry", "target", "mean_diff"], ascending=[True, True, False]).reset_index(drop=True)
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Industry-level fundamental variable analysis.")
    p.add_argument("--input", default=str(data_path("feature_daily.pkl")))
    p.add_argument("--min-obs-corr", type=int, default=500)
    p.add_argument("--min-obs-flag", type=int, default=100)
    p.add_argument("--corr-output", default=str(output_path("industry_fundamental_corr.csv")))
    p.add_argument("--flag-output", default=str(output_path("industry_fundamental_flag_perf.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    df = load_feature_dataset(Path(args.input))
    df = add_forward_returns(df)
    df = add_profit_flags(df)

    corr = industry_corr(df, min_obs=args.min_obs_corr)
    perf = industry_flag_performance(df, min_obs=args.min_obs_flag)

    corr_out = Path(args.corr_output)
    perf_out = Path(args.flag_output)
    corr_out.parent.mkdir(parents=True, exist_ok=True)
    corr.to_csv(corr_out, index=False, encoding="utf-8-sig")
    perf.to_csv(perf_out, index=False, encoding="utf-8-sig")

    print(f"[saved] {corr_out}")
    print(f"[saved] {perf_out}")
    print(f"[corr_rows] {len(corr):,}")
    print(f"[flag_rows] {len(perf):,}")
    if not corr.empty:
        print("[corr top]")
        print(corr.groupby(["industry", "target"]).head(3).head(30).to_string(index=False))
    if not perf.empty:
        print("[flag top]")
        print(perf.groupby(["industry", "target"]).head(3).head(30).to_string(index=False))


if __name__ == "__main__":
    main()
