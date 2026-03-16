import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from new_strategy.legacy_analysis.build_quarterly_stock_panel import build_panel
from new_strategy.paths import data_path, output_path


PAIR_SPECS = [
    ("revenue_q", "period_ret"),
    ("op_income_q", "period_ret"),
    ("net_income_q", "period_ret"),
    ("op_margin_q", "period_ret"),
    ("net_margin_q", "period_ret"),
    ("revenue_q_qoq", "period_ret"),
    ("op_income_q_qoq", "period_ret"),
    ("net_income_q_qoq", "period_ret"),
    ("net_margin_q_qoq", "period_ret"),
    ("op_margin_q_qoq", "period_ret"),
    ("op_income_vs_revenue_qoq_gap", "period_ret"),
    ("net_income_vs_revenue_qoq_gap", "period_ret"),
    ("op_income_qoq_accel", "period_ret"),
    ("net_income_qoq_accel", "period_ret"),
    ("revenue_t4_sum", "period_ret"),
    ("op_income_t4_sum", "period_ret"),
    ("net_income_t4_sum", "period_ret"),
    ("op_income_t4_std", "period_ret"),
    ("net_income_t4_std", "period_ret"),
    ("period_kospi_ret", "period_ret"),
    ("period_avg_vix", "period_ret"),
    ("period_avg_usdkrw", "period_ret"),
    ("period_avg_us10y", "period_ret"),
    ("period_avg_kr10y", "period_ret"),
    ("period_avg_gold_kr_close", "period_ret"),
    ("period_avg_risk_count", "period_ret"),
    ("period_avg_exposure", "period_ret"),
    ("revenue_q", "post_filing_30d_ret"),
    ("op_income_q", "post_filing_30d_ret"),
    ("net_income_q", "post_filing_30d_ret"),
    ("op_margin_q", "post_filing_30d_ret"),
    ("net_margin_q", "post_filing_30d_ret"),
    ("revenue_q_qoq", "post_filing_30d_ret"),
    ("op_income_q_qoq", "post_filing_30d_ret"),
    ("net_income_q_qoq", "post_filing_30d_ret"),
    ("net_margin_q_qoq", "post_filing_30d_ret"),
    ("op_margin_q_qoq", "post_filing_30d_ret"),
    ("op_income_vs_revenue_qoq_gap", "post_filing_30d_ret"),
    ("net_income_vs_revenue_qoq_gap", "post_filing_30d_ret"),
    ("op_income_qoq_accel", "post_filing_30d_ret"),
    ("net_income_qoq_accel", "post_filing_30d_ret"),
    ("revenue_t4_sum", "post_filing_30d_ret"),
    ("op_income_t4_sum", "post_filing_30d_ret"),
    ("net_income_t4_sum", "post_filing_30d_ret"),
    ("op_income_t4_std", "post_filing_30d_ret"),
    ("net_income_t4_std", "post_filing_30d_ret"),
    ("period_kospi_ret", "post_filing_30d_ret"),
    ("period_avg_vix", "post_filing_30d_ret"),
    ("period_avg_usdkrw", "post_filing_30d_ret"),
    ("period_avg_us10y", "post_filing_30d_ret"),
    ("period_avg_kr10y", "post_filing_30d_ret"),
    ("period_avg_gold_kr_close", "post_filing_30d_ret"),
    ("period_avg_risk_count", "post_filing_30d_ret"),
    ("period_avg_exposure", "post_filing_30d_ret"),
    ("revenue_q", "post_filing_60d_ret"),
    ("op_income_q", "post_filing_60d_ret"),
    ("net_income_q", "post_filing_60d_ret"),
    ("op_margin_q", "post_filing_60d_ret"),
    ("net_margin_q", "post_filing_60d_ret"),
    ("revenue_q_qoq", "post_filing_60d_ret"),
    ("op_income_q_qoq", "post_filing_60d_ret"),
    ("net_income_q_qoq", "post_filing_60d_ret"),
    ("net_margin_q_qoq", "post_filing_60d_ret"),
    ("op_margin_q_qoq", "post_filing_60d_ret"),
    ("op_income_vs_revenue_qoq_gap", "post_filing_60d_ret"),
    ("net_income_vs_revenue_qoq_gap", "post_filing_60d_ret"),
    ("op_income_qoq_accel", "post_filing_60d_ret"),
    ("net_income_qoq_accel", "post_filing_60d_ret"),
    ("revenue_t4_sum", "post_filing_60d_ret"),
    ("op_income_t4_sum", "post_filing_60d_ret"),
    ("net_income_t4_sum", "post_filing_60d_ret"),
    ("op_income_t4_std", "post_filing_60d_ret"),
    ("net_income_t4_std", "post_filing_60d_ret"),
    ("period_kospi_ret", "post_filing_60d_ret"),
    ("period_avg_vix", "post_filing_60d_ret"),
    ("period_avg_usdkrw", "post_filing_60d_ret"),
    ("period_avg_us10y", "post_filing_60d_ret"),
    ("period_avg_kr10y", "post_filing_60d_ret"),
    ("period_avg_gold_kr_close", "post_filing_60d_ret"),
    ("period_avg_risk_count", "post_filing_60d_ret"),
    ("period_avg_exposure", "post_filing_60d_ret"),
    ("revenue_q", "post_filing_90d_ret"),
    ("op_income_q", "post_filing_90d_ret"),
    ("net_income_q", "post_filing_90d_ret"),
    ("op_margin_q", "post_filing_90d_ret"),
    ("net_margin_q", "post_filing_90d_ret"),
    ("revenue_q_qoq", "post_filing_90d_ret"),
    ("op_income_q_qoq", "post_filing_90d_ret"),
    ("net_income_q_qoq", "post_filing_90d_ret"),
    ("net_margin_q_qoq", "post_filing_90d_ret"),
    ("op_margin_q_qoq", "post_filing_90d_ret"),
    ("op_income_vs_revenue_qoq_gap", "post_filing_90d_ret"),
    ("net_income_vs_revenue_qoq_gap", "post_filing_90d_ret"),
    ("op_income_qoq_accel", "post_filing_90d_ret"),
    ("net_income_qoq_accel", "post_filing_90d_ret"),
    ("revenue_t4_sum", "post_filing_90d_ret"),
    ("op_income_t4_sum", "post_filing_90d_ret"),
    ("net_income_t4_sum", "post_filing_90d_ret"),
    ("op_income_t4_std", "post_filing_90d_ret"),
    ("net_income_t4_std", "post_filing_90d_ret"),
    ("period_kospi_ret", "post_filing_90d_ret"),
    ("period_avg_vix", "post_filing_90d_ret"),
    ("period_avg_usdkrw", "post_filing_90d_ret"),
    ("period_avg_us10y", "post_filing_90d_ret"),
    ("period_avg_kr10y", "post_filing_90d_ret"),
    ("period_avg_gold_kr_close", "post_filing_90d_ret"),
    ("period_avg_risk_count", "post_filing_90d_ret"),
    ("period_avg_exposure", "post_filing_90d_ret"),
]

LABEL_MAP = {
    "revenue_q": "분기매출액",
    "op_income_q": "분기영업이익",
    "net_income_q": "분기당기순이익",
    "op_margin_q": "분기영업이익률",
    "net_margin_q": "분기순이익률",
    "revenue_q_qoq": "분기매출액QoQ증감액",
    "op_income_q_qoq": "분기영업이익QoQ증감액",
    "net_income_q_qoq": "분기당기순이익QoQ증감액",
    "net_margin_q_qoq": "분기순이익률QoQ변화",
    "op_margin_q_qoq": "분기영업이익률QoQ변화",
    "op_income_vs_revenue_qoq_gap": "영업이익대비매출QoQ격차",
    "net_income_vs_revenue_qoq_gap": "당기순이익대비매출QoQ격차",
    "op_income_qoq_accel": "영업이익QoQ가속도",
    "net_income_qoq_accel": "당기순이익QoQ가속도",
    "revenue_t4_sum": "최근4분기매출합",
    "op_income_t4_sum": "최근4분기영업이익합",
    "net_income_t4_sum": "최근4분기당기순이익합",
    "op_income_t4_std": "최근4분기영업이익변동성",
    "net_income_t4_std": "최근4분기당기순이익변동성",
    "period_ret": "분기주가수익률",
    "period_kospi_ret": "분기KOSPI수익률",
    "period_avg_vix": "분기평균VIX",
    "period_avg_usdkrw": "분기평균USDKRW",
    "period_avg_us10y": "분기평균미국10년금리",
    "period_avg_kr10y": "분기평균국고10년금리",
    "period_avg_gold_kr_close": "분기평균금가격",
    "period_avg_risk_count": "분기평균리스크카운트",
    "period_avg_exposure": "분기평균노출비중",
    "post_filing_30d_ret": "공시후30일수익률",
    "post_filing_60d_ret": "공시후60일수익률",
    "post_filing_90d_ret": "공시후90일수익률",
}


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


def corr_value(df: pd.DataFrame, x_col: str, y_col: str, min_obs: int):
    tmp = df[[x_col, y_col]].apply(pd.to_numeric, errors="coerce").dropna()
    n = len(tmp)
    if n < min_obs:
        return np.nan, n
    corr = tmp[x_col].corr(tmp[y_col])
    return float(corr) if pd.notna(corr) else np.nan, n


def build_stock_summary(panel: pd.DataFrame, min_obs: int) -> pd.DataFrame:
    rows = []
    for _, g in panel.groupby("code", sort=False):
        if "earnings_exception_flag" in g.columns:
            g = g[~g["earnings_exception_flag"].fillna(False)].copy()
        if g.empty:
            continue
        sorted_g = g.sort_values(["fiscal_year", "reprt_code"], key=lambda s: s.map({"11013": 1, "11012": 2, "11014": 3, "11011": 4}) if s.name == "reprt_code" else s)
        row = {
            "code": g["code"].iloc[0],
            "name": g["name"].iloc[0],
            "market": g["market"].iloc[0],
            "industry": g["industry"].iloc[0],
            "quarter_count": int(g["quarter_label"].nunique()),
            "exception_filtered_count": int(panel.loc[panel["code"] == g["code"].iloc[0], "earnings_exception_flag"].fillna(False).sum()) if "earnings_exception_flag" in panel.columns else 0,
            "first_quarter": sorted_g["quarter_label"].iloc[0],
            "last_quarter": sorted_g["quarter_label"].iloc[-1],
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
        "code": "종목코드",
        "name": "종목명",
        "market": "시장구분",
        "industry": "업종",
        "quarter_count": "분기수",
        "exception_filtered_count": "예외필터제외분기수",
        "first_quarter": "시작분기",
        "last_quarter": "종료분기",
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
    p = argparse.ArgumentParser(description="One-row-per-stock quarterly/filing relationship summary.")
    p.add_argument("--panel", default=str(data_path("quarterly_stock_panel.pkl")))
    p.add_argument("--min-obs", type=int, default=8)
    p.add_argument("--output", default=str(output_path("stock_quarterly_relationship_summary.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    panel = load_or_build_panel(Path(args.panel))
    if not Path(args.panel).exists():
        panel.to_pickle(Path(args.panel))
    summary = build_stock_summary(panel, min_obs=args.min_obs)
    summary = to_korean_columns(summary)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[saved] {out}")
    print(f"[rows] {len(summary):,}")
    code_col = "종목코드" if "종목코드" in summary.columns else "code"
    print(f"[codes] {summary[code_col].nunique():,}")


if __name__ == "__main__":
    main()
