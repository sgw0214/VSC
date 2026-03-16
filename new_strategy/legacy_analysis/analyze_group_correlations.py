import argparse
from pathlib import Path

import pandas as pd

from new_strategy.paths import data_path, output_path
from new_strategy.legacy_analysis.analyze_stock_correlations import FEATURE_COLS, TARGET_WINDOWS, load_feature_dataset, add_forward_returns


def add_cap_bucket(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["mcap_pct_rank"] = out.groupby("date")["market_cap"].rank(pct=True, method="average")
    out["cap_bucket"] = "mid"
    out.loc[out["mcap_pct_rank"] <= 0.3, "cap_bucket"] = "small"
    out.loc[out["mcap_pct_rank"] >= 0.7, "cap_bucket"] = "large"
    return out


def grouped_corr(df: pd.DataFrame, group_col: str, min_obs: int) -> pd.DataFrame:
    rows = []
    features = [c for c in FEATURE_COLS if c in df.columns]
    for group_value, g in df.groupby(group_col, dropna=False):
        if pd.isna(group_value):
            continue
        for w in TARGET_WINDOWS:
            target = f"fwd_ret_{w}d"
            for feat in features:
                pair = g[[feat, target]].apply(pd.to_numeric, errors="coerce").dropna()
                n = len(pair)
                if n < min_obs:
                    continue
                corr = pair[feat].corr(pair[target])
                rows.append(
                    {
                        "group_type": group_col,
                        "group_value": group_value,
                        "target": target,
                        "feature": feat,
                        "corr": float(corr) if pd.notna(corr) else None,
                        "abs_corr": abs(float(corr)) if pd.notna(corr) else None,
                        "n_obs": int(n),
                        "n_codes": int(g["code"].nunique()),
                    }
                )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["group_type", "group_value", "target", "abs_corr"], ascending=[True, True, True, False])
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Grouped correlation analysis by industry and cap bucket.")
    p.add_argument("--input", default=str(data_path("feature_daily.pkl")))
    p.add_argument("--min-obs", type=int, default=500)
    p.add_argument("--industry-output", default=str(output_path("industry_feature_corr_summary.csv")))
    p.add_argument("--cap-output", default=str(output_path("capbucket_feature_corr_summary.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    df = load_feature_dataset(Path(args.input))
    df = add_forward_returns(df)
    df = add_cap_bucket(df)

    industry = grouped_corr(df, "industry", min_obs=args.min_obs)
    cap = grouped_corr(df, "cap_bucket", min_obs=args.min_obs)

    industry_out = Path(args.industry_output)
    cap_out = Path(args.cap_output)
    industry_out.parent.mkdir(parents=True, exist_ok=True)
    industry.to_csv(industry_out, index=False, encoding="utf-8-sig")
    cap.to_csv(cap_out, index=False, encoding="utf-8-sig")

    print(f"[saved] {industry_out}")
    print(f"[saved] {cap_out}")
    print(f"[industry_rows] {len(industry):,}")
    print(f"[cap_rows] {len(cap):,}")
    if not industry.empty:
        print("[industry top]")
        print(industry.groupby(["group_value", "target"]).head(3).head(30).to_string(index=False))
    if not cap.empty:
        print("[cap top]")
        print(cap.groupby(["group_value", "target"]).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
