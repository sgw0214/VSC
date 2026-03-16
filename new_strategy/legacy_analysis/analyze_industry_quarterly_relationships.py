import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from new_strategy.legacy_analysis.analyze_stock_quarterly_relationships import PAIR_SPECS, LABEL_MAP, corr_value
from new_strategy.legacy_analysis.build_quarterly_stock_panel import build_panel
from new_strategy.paths import data_path, output_path


def load_or_build_panel(path: Path) -> pd.DataFrame:
    if path.exists():
        if path.suffix.lower() == ".pkl":
            return pd.read_pickle(path)
        return pd.read_csv(path, dtype={"code": str}, low_memory=False, parse_dates=["period_start", "period_end", "filing_date"])
    csv_path = path.with_suffix(".csv") if path.suffix.lower() == ".pkl" else path
    return build_panel(
        data_path("feature_daily.pkl"),
        data_path("fundamental_quarterly_multi.csv"),
        csv_path,
    )


def build_industry_summary(panel: pd.DataFrame, min_obs: int) -> pd.DataFrame:
    rows = []
    for industry, g in panel.groupby("industry", sort=False, dropna=False):
        if pd.isna(industry):
            continue
        raw_g = g
        if "earnings_exception_flag" in g.columns:
            g = g[~g["earnings_exception_flag"].fillna(False)].copy()
        if g.empty:
            continue
        row = {
            "industry": industry,
            "stock_count": int(g["code"].nunique()),
            "quarter_rows": int(len(g)),
            "exception_filtered_count": int(raw_g["earnings_exception_flag"].fillna(False).sum()) if "earnings_exception_flag" in raw_g.columns else 0,
            "avg_period_ret": pd.to_numeric(g["period_ret"], errors="coerce").mean(),
            "avg_post_filing_30d_ret": pd.to_numeric(g["post_filing_30d_ret"], errors="coerce").mean(),
            "avg_post_filing_60d_ret": pd.to_numeric(g["post_filing_60d_ret"], errors="coerce").mean(),
            "avg_post_filing_90d_ret": pd.to_numeric(g["post_filing_90d_ret"], errors="coerce").mean(),
        }
        strongest = {
            "period_ret": ("", np.nan),
            "post_filing_30d_ret": ("", np.nan),
            "post_filing_60d_ret": ("", np.nan),
            "post_filing_90d_ret": ("", np.nan),
        }
        overall_best_feature = ""
        overall_best_target = ""
        overall_best_corr = np.nan
        overall_best_n = np.nan
        for x_col, y_col in PAIR_SPECS:
            corr, n_obs = corr_value(g, x_col, y_col, min_obs=min_obs)
            row[f"corr__{x_col}__{y_col}"] = corr
            row[f"n__{x_col}__{y_col}"] = int(n_obs)
            if pd.notna(corr):
                _, current = strongest[y_col]
                if pd.isna(current) or abs(corr) > abs(current):
                    strongest[y_col] = (x_col, corr)
                if pd.isna(overall_best_corr) or abs(corr) > abs(overall_best_corr):
                    overall_best_feature = x_col
                    overall_best_target = y_col
                    overall_best_corr = corr
                    overall_best_n = n_obs
        row["best_period_feature"] = strongest["period_ret"][0]
        row["best_period_corr"] = strongest["period_ret"][1]
        row["best_post30_feature"] = strongest["post_filing_30d_ret"][0]
        row["best_post30_corr"] = strongest["post_filing_30d_ret"][1]
        row["best_post60_feature"] = strongest["post_filing_60d_ret"][0]
        row["best_post60_corr"] = strongest["post_filing_60d_ret"][1]
        row["best_post90_feature"] = strongest["post_filing_90d_ret"][0]
        row["best_post90_corr"] = strongest["post_filing_90d_ret"][1]
        row["best_overall_feature"] = overall_best_feature
        row["best_overall_target"] = overall_best_target
        row["best_overall_corr"] = overall_best_corr
        row["best_overall_abs_corr"] = abs(overall_best_corr) if pd.notna(overall_best_corr) else np.nan
        row["best_overall_n"] = overall_best_n
        rows.append(row)
    return pd.DataFrame(rows)


def to_korean_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    fixed = {
        "industry": "업종",
        "stock_count": "종목수",
        "quarter_rows": "분기행수",
        "exception_filtered_count": "예외필터제외분기수",
        "avg_period_ret": "평균분기수익률",
        "avg_post_filing_30d_ret": "평균공시후30일수익률",
        "avg_post_filing_60d_ret": "평균공시후60일수익률",
        "avg_post_filing_90d_ret": "평균공시후90일수익률",
        "best_period_feature": "대표분기상관변수",
        "best_period_corr": "대표분기상관계수",
        "best_post30_feature": "대표공시후30일상관변수",
        "best_post30_corr": "대표공시후30일상관계수",
        "best_post60_feature": "대표공시후60일상관변수",
        "best_post60_corr": "대표공시후60일상관계수",
        "best_post90_feature": "대표공시후90일상관변수",
        "best_post90_corr": "대표공시후90일상관계수",
        "best_overall_feature": "최고상관변수",
        "best_overall_target": "최고상관대상",
        "best_overall_corr": "최고상관계수",
        "best_overall_abs_corr": "최고상관계수절대값",
        "best_overall_n": "최고상관표본수",
    }
    for col in df.columns:
        if col in fixed:
            renamed[col] = fixed[col]
            continue
        if col.startswith("corr__"):
            _, left, right = col.split("__", 2)
            renamed[col] = f"상관계수__{LABEL_MAP.get(left, left)}__{LABEL_MAP.get(right, right)}"
            continue
        if col.startswith("n__"):
            _, left, right = col.split("__", 2)
            renamed[col] = f"표본수__{LABEL_MAP.get(left, left)}__{LABEL_MAP.get(right, right)}"
            continue
    out = df.rename(columns=renamed)
    for col in ["대표분기상관변수", "대표공시후30일상관변수", "대표공시후60일상관변수", "대표공시후90일상관변수", "최고상관변수"]:
        if col in out.columns:
            out[col] = out[col].map(lambda x: LABEL_MAP.get(x, x) if pd.notna(x) else x)
    if "최고상관대상" in out.columns:
        out["최고상관대상"] = out["최고상관대상"].map(lambda x: LABEL_MAP.get(x, x) if pd.notna(x) else x)
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="One-row-per-industry quarterly/filing relationship summary.")
    p.add_argument("--panel", default=str(data_path("quarterly_stock_panel.pkl")))
    p.add_argument("--min-obs", type=int, default=30)
    p.add_argument("--output", default=str(output_path("industry_quarterly_relationship_summary.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    panel = load_or_build_panel(Path(args.panel))
    if not Path(args.panel).exists():
        panel.to_pickle(Path(args.panel))
    summary = build_industry_summary(panel, min_obs=args.min_obs)
    summary = to_korean_columns(summary)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[saved] {out}")
    print(f"[rows] {len(summary):,}")


if __name__ == "__main__":
    main()
