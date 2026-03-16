import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from new_strategy.paths import data_path, output_path


FEATURE_COLS = [
    "momentum_score",
    "quality_score",
    "ret_20",
    "ret_60",
    "ret_120",
    "atr_ratio",
    "dist_ma_mid",
    "trend_strength",
    "liq_strength",
    "adv20_pct_rank",
    "exposure",
    "risk_count",
    "revenue_yoy_pct_pti",
    "op_income_yoy_pct_pti",
    "net_income_yoy_pct_pti",
    "revenue_qoq_pct_pti",
    "op_income_qoq_pct_pti",
    "net_income_qoq_pct_pti",
    "revenue_yoy_pct_period",
    "op_income_yoy_pct_period",
    "net_income_yoy_pct_period",
]

TARGET_WINDOWS = [5, 20, 60]


def load_feature_dataset(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".pkl":
        df = pd.read_pickle(path)
    elif path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values(["code", "date"]).reset_index(drop=True)


def add_forward_returns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    g = out.groupby("code", sort=False)
    for w in TARGET_WINDOWS:
        out[f"fwd_ret_{w}d"] = g["close"].transform(lambda s: s.shift(-w) / s - 1.0)
    return out


def corr_one_stock(g: pd.DataFrame, min_obs: int) -> list:
    rows = []
    base_cols = [c for c in FEATURE_COLS if c in g.columns]
    if not base_cols:
        return rows

    for target_w in TARGET_WINDOWS:
        target_col = f"fwd_ret_{target_w}d"
        cols = base_cols + [target_col]
        tmp = g[cols].apply(pd.to_numeric, errors="coerce")
        for feat in base_cols:
            pair = tmp[[feat, target_col]].dropna()
            n = len(pair)
            if n < min_obs:
                continue
            corr = pair[feat].corr(pair[target_col])
            rows.append(
                {
                    "code": g["code"].iloc[0],
                    "name": g["name"].iloc[0],
                    "target": target_col,
                    "feature": feat,
                    "corr": float(corr) if pd.notna(corr) else np.nan,
                    "abs_corr": float(abs(corr)) if pd.notna(corr) else np.nan,
                    "n_obs": int(n),
                }
            )
    return rows


def build_correlation_report(df: pd.DataFrame, min_obs: int) -> tuple:
    rows = []
    for _, g in df.groupby("code", sort=False):
        rows.extend(corr_one_stock(g, min_obs=min_obs))

    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, pd.DataFrame()

    summary = (
        detail.groupby(["target", "feature"], as_index=False)
        .agg(
            stock_count=("code", "nunique"),
            mean_corr=("corr", "mean"),
            median_corr=("corr", "median"),
            mean_abs_corr=("abs_corr", "mean"),
            median_abs_corr=("abs_corr", "median"),
            positive_share=("corr", lambda s: float((s > 0).mean())),
            negative_share=("corr", lambda s: float((s < 0).mean())),
        )
        .sort_values(["target", "median_abs_corr"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return detail, summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Per-stock correlation analysis between features and forward returns.")
    p.add_argument("--input", default=str(data_path("feature_daily.pkl")))
    p.add_argument("--min-obs", type=int, default=120)
    p.add_argument("--detail-output", default=str(output_path("stock_feature_corr_detail.csv")))
    p.add_argument("--summary-output", default=str(output_path("stock_feature_corr_summary.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    df = load_feature_dataset(Path(args.input))
    df = add_forward_returns(df)
    detail, summary = build_correlation_report(df, min_obs=args.min_obs)

    detail_out = Path(args.detail_output)
    summary_out = Path(args.summary_output)
    detail_out.parent.mkdir(parents=True, exist_ok=True)
    detail.to_csv(detail_out, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_out, index=False, encoding="utf-8-sig")

    print(f"[saved] {detail_out}")
    print(f"[saved] {summary_out}")
    print(f"[detail_rows] {len(detail):,}")
    print(f"[summary_rows] {len(summary):,}")
    if not summary.empty:
        print(summary.groupby("target").head(10).to_string(index=False))


if __name__ == "__main__":
    main()
