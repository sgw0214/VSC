import argparse
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from new_strategy.paths import data_path


FUND_KR_TO_EN = {
    "종목코드": "code",
    "법인코드": "corp_code",
    "법인명": "corp_name",
    "사업연도": "fiscal_year",
    "보고서코드": "reprt_code",
    "접수번호": "rcept_no",
    "공시일": "filing_date",
    "매출액": "revenue_cum",
    "영업이익": "op_income_cum",
    "당기순이익": "net_income_cum",
    "자산총계": "total_assets",
    "부채총계": "total_liab",
    "자본총계": "total_equity",
    "영업이익률": "op_margin_cum",
    "ROE(단순)": "roe_simple_cum",
    "분기매출액": "revenue_q",
    "분기영업이익": "op_income_q",
    "분기당기순이익": "net_income_q",
    "분기영업이익률": "op_margin_q",
    "분기ROE(단순)": "roe_simple_q",
}


def period_bounds(year: int, reprt_code: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    code = str(reprt_code)
    year = int(year)
    if code == "11013":
        return pd.Timestamp(year=year, month=1, day=1), pd.Timestamp(year=year, month=3, day=31)
    if code == "11012":
        return pd.Timestamp(year=year, month=4, day=1), pd.Timestamp(year=year, month=6, day=30)
    if code == "11014":
        return pd.Timestamp(year=year, month=7, day=1), pd.Timestamp(year=year, month=9, day=30)
    if code == "11011":
        return pd.Timestamp(year=year, month=10, day=1), pd.Timestamp(year=year, month=12, day=31)
    return pd.NaT, pd.NaT


def load_fundamental(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False).rename(columns=FUND_KR_TO_EN)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["fiscal_year"] = pd.to_numeric(df["fiscal_year"], errors="coerce").astype("Int64")
    df["reprt_code"] = df["reprt_code"].astype(str)
    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    bounds = df.apply(
        lambda row: period_bounds(row["fiscal_year"], row["reprt_code"]),
        axis=1,
        result_type="expand",
    )
    df["period_start"] = bounds[0]
    df["period_end"] = bounds[1]
    df["quarter_order"] = df["reprt_code"].map({"11013": 1, "11012": 2, "11014": 3, "11011": 4}).fillna(9)
    df = df.sort_values(["code", "fiscal_year", "quarter_order", "filing_date"]).drop_duplicates(
        ["code", "fiscal_year", "reprt_code"], keep="last"
    )
    df = df.sort_values(["code", "fiscal_year", "quarter_order", "filing_date"]).reset_index(drop=True)
    grp = df.groupby("code", sort=False)
    for col in ["revenue_q", "op_income_q", "net_income_q", "op_margin_q", "roe_simple_q"]:
        df[f"{col}_yoy"] = df[col] - grp[col].shift(4)
        prev_y = grp[col].shift(4).abs().replace(0, np.nan)
        df[f"{col}_yoy_pct"] = df[f"{col}_yoy"] / prev_y
        df[f"{col}_qoq"] = df[col] - grp[col].shift(1)
        prev_q = grp[col].shift(1).abs().replace(0, np.nan)
        df[f"{col}_qoq_pct"] = df[f"{col}_qoq"] / prev_q

    df["net_margin_q"] = df["net_income_q"] / df["revenue_q"].replace(0, np.nan)
    df["net_margin_q_qoq"] = df["net_margin_q"] - grp["net_margin_q"].shift(1)
    df["op_margin_q_qoq"] = df["op_margin_q"] - grp["op_margin_q"].shift(1)
    df["op_income_vs_revenue_qoq_gap"] = df["op_income_q_qoq"] - df["revenue_q_qoq"]
    df["net_income_vs_revenue_qoq_gap"] = df["net_income_q_qoq"] - df["revenue_q_qoq"]
    df["op_income_qoq_accel"] = df["op_income_q_qoq"] - grp["op_income_q_qoq"].shift(1)
    df["net_income_qoq_accel"] = df["net_income_q_qoq"] - grp["net_income_q_qoq"].shift(1)
    df["revenue_t4_sum"] = grp["revenue_q"].transform(lambda s: s.rolling(4, min_periods=4).sum())
    df["op_income_t4_sum"] = grp["op_income_q"].transform(lambda s: s.rolling(4, min_periods=4).sum())
    df["net_income_t4_sum"] = grp["net_income_q"].transform(lambda s: s.rolling(4, min_periods=4).sum())
    df["op_income_t4_std"] = grp["op_income_q"].transform(lambda s: s.rolling(4, min_periods=4).std())
    df["net_income_t4_std"] = grp["net_income_q"].transform(lambda s: s.rolling(4, min_periods=4).std())
    df["non_operating_profit_flag"] = (df["op_income_q"] <= 0) & (df["net_income_q"] > 0)
    df["net_op_gap_ratio"] = (df["net_income_q"] - df["op_income_q"]).abs() / df["revenue_q"].abs().replace(0, np.nan)
    df["extreme_net_margin_flag"] = df["net_margin_q"].abs() > 0.5
    df["earnings_exception_flag"] = df["non_operating_profit_flag"] | (
        df["extreme_net_margin_flag"] & (df["net_op_gap_ratio"] > 0.2)
    )
    return df.reset_index(drop=True)


def load_price(path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if path.suffix.lower() == ".pkl":
        df = pd.read_pickle(path)
    else:
        df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["code", "date"]).reset_index(drop=True)
    meta = (
        df.sort_values(["code", "date"])
        .groupby("code", as_index=False)
        .agg({"name": "last", "market": "last", "industry": "last"})
    )
    return df, meta


def build_macro_lookup(price_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Tuple[np.ndarray, np.ndarray]]]:
    macro_cols = [
        "date",
        "kospi",
        "vix",
        "usdkrw",
        "us10y",
        "kr10y",
        "gold_kr_close",
        "risk_count",
        "exposure",
        "regime",
    ]
    available = [c for c in macro_cols if c in price_df.columns]
    macro = price_df[available].drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    lookup = {}
    for col in [c for c in available if c != "date" and c != "regime"]:
        lookup[col] = (
            macro["date"].to_numpy(dtype="datetime64[ns]"),
            pd.to_numeric(macro[col], errors="coerce").to_numpy(dtype="float64"),
        )
    if "regime" in macro.columns:
        lookup["regime"] = (
            macro["date"].to_numpy(dtype="datetime64[ns]"),
            macro["regime"].astype(str).to_numpy(),
        )
    return macro, lookup


def build_price_lookup(price_df: pd.DataFrame) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    out: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for code, grp in price_df.groupby("code", sort=False):
        dates = grp["date"].to_numpy(dtype="datetime64[ns]")
        close = grp["close"].to_numpy(dtype="float64")
        out[code] = (dates, close)
    return out


def get_close_on_or_after(dates: np.ndarray, closes: np.ndarray, target: pd.Timestamp, max_gap_days: int = 10):
    pos = np.searchsorted(dates, np.datetime64(target), side="left")
    if pos >= len(dates):
        return np.nan
    chosen_date = pd.Timestamp(dates[pos])
    if chosen_date < target or (chosen_date - target).days > max_gap_days:
        return np.nan
    return float(closes[pos])


def get_close_on_or_before(dates: np.ndarray, closes: np.ndarray, target: pd.Timestamp, max_gap_days: int = 10):
    pos = np.searchsorted(dates, np.datetime64(target), side="right") - 1
    if pos < 0:
        return np.nan
    chosen_date = pd.Timestamp(dates[pos])
    if chosen_date > target or (target - chosen_date).days > max_gap_days:
        return np.nan
    return float(closes[pos])


def get_value_on_or_after(dates: np.ndarray, values: np.ndarray, target: pd.Timestamp):
    pos = np.searchsorted(dates, np.datetime64(target), side="left")
    if pos >= len(dates):
        return np.nan
    chosen_date = pd.Timestamp(dates[pos])
    if chosen_date < target or (chosen_date - target).days > 10:
        return np.nan
    return values[pos]


def get_offset_close(dates: np.ndarray, closes: np.ndarray, target: pd.Timestamp, offset: int, max_gap_days: int = 10):
    pos = np.searchsorted(dates, np.datetime64(target), side="left")
    if pos >= len(dates):
        return np.nan
    chosen_date = pd.Timestamp(dates[pos])
    if dates[pos] != np.datetime64(target):
        if chosen_date < target or (chosen_date - target).days > max_gap_days:
            return np.nan
        if offset >= 0:
            pass
        else:
            pos = pos - 1
            if pos < 0:
                return np.nan
            prev_date = pd.Timestamp(dates[pos])
            if prev_date > target or (target - prev_date).days > max_gap_days:
                return np.nan
    idx = pos + offset
    if idx < 0 or idx >= len(dates):
        return np.nan
    return float(closes[idx])


def safe_ret(end_value, start_value):
    if pd.isna(end_value) or pd.isna(start_value) or start_value == 0:
        return np.nan
    return float(end_value / start_value - 1.0)


def enrich_with_price(
    panel: pd.DataFrame,
    price_lookup: Dict[str, Tuple[np.ndarray, np.ndarray]],
    macro_lookup: Dict[str, Tuple[np.ndarray, np.ndarray]],
) -> pd.DataFrame:
    records = []
    for row in panel.itertuples(index=False):
        dates, closes = price_lookup.get(row.code, (None, None))
        if dates is None:
            records.append(
                {
                    "period_start_close": np.nan,
                    "period_end_close": np.nan,
                    "period_ret": np.nan,
                    "pre_filing_20d_close": np.nan,
                    "filing_close": np.nan,
                    "post_filing_5d_close": np.nan,
                    "post_filing_30d_close": np.nan,
                    "post_filing_60d_close": np.nan,
                    "post_filing_90d_close": np.nan,
                    "pre_filing_20d_ret": np.nan,
                    "post_filing_5d_ret": np.nan,
                    "post_filing_30d_ret": np.nan,
                    "post_filing_60d_ret": np.nan,
                    "post_filing_90d_ret": np.nan,
                    "period_kospi_ret": np.nan,
                    "period_avg_vix": np.nan,
                    "period_avg_usdkrw": np.nan,
                    "period_avg_us10y": np.nan,
                    "period_avg_kr10y": np.nan,
                    "period_avg_gold_kr_close": np.nan,
                    "period_avg_risk_count": np.nan,
                    "period_avg_exposure": np.nan,
                }
            )
            continue

        first_trade_date = pd.Timestamp(dates[0]).to_datetime64()
        filing_before_listing = pd.notna(row.filing_date) and np.datetime64(row.filing_date) < first_trade_date
        period_start_close = get_close_on_or_after(dates, closes, row.period_start)
        period_end_close = get_close_on_or_before(dates, closes, row.period_end)
        if pd.notna(row.filing_date) and not filing_before_listing:
            filing_close = get_close_on_or_after(dates, closes, row.filing_date)
            pre_filing_20d_close = get_offset_close(dates, closes, row.filing_date, -20)
            post_filing_5d_close = get_offset_close(dates, closes, row.filing_date, 5)
            post_filing_30d_close = get_offset_close(dates, closes, row.filing_date, 30)
            post_filing_60d_close = get_offset_close(dates, closes, row.filing_date, 60)
            post_filing_90d_close = get_offset_close(dates, closes, row.filing_date, 90)
        else:
            filing_close = np.nan
            pre_filing_20d_close = np.nan
            post_filing_5d_close = np.nan
            post_filing_30d_close = np.nan
            post_filing_60d_close = np.nan
            post_filing_90d_close = np.nan

        period_kospi_start = get_value_on_or_after(*macro_lookup["kospi"], row.period_start) if "kospi" in macro_lookup else np.nan
        period_kospi_end = get_value_on_or_after(*macro_lookup["kospi"], row.period_end) if "kospi" in macro_lookup else np.nan
        period_avg_vix = np.nan
        period_avg_usdkrw = np.nan
        period_avg_us10y = np.nan
        period_avg_kr10y = np.nan
        period_avg_gold = np.nan
        period_avg_risk_count = np.nan
        period_avg_exposure = np.nan
        p0 = np.datetime64(row.period_start)
        p1 = np.datetime64(row.period_end)
        if "vix" in macro_lookup:
            md, mv = macro_lookup["vix"]
            mask = (md >= p0) & (md <= p1)
            period_avg_vix = float(np.nanmean(mv[mask])) if mask.any() else np.nan
        if "usdkrw" in macro_lookup:
            md, mv = macro_lookup["usdkrw"]
            mask = (md >= p0) & (md <= p1)
            period_avg_usdkrw = float(np.nanmean(mv[mask])) if mask.any() else np.nan
        if "us10y" in macro_lookup:
            md, mv = macro_lookup["us10y"]
            mask = (md >= p0) & (md <= p1)
            period_avg_us10y = float(np.nanmean(mv[mask])) if mask.any() else np.nan
        if "kr10y" in macro_lookup:
            md, mv = macro_lookup["kr10y"]
            mask = (md >= p0) & (md <= p1)
            period_avg_kr10y = float(np.nanmean(mv[mask])) if mask.any() else np.nan
        if "gold_kr_close" in macro_lookup:
            md, mv = macro_lookup["gold_kr_close"]
            mask = (md >= p0) & (md <= p1)
            period_avg_gold = float(np.nanmean(mv[mask])) if mask.any() else np.nan
        if "risk_count" in macro_lookup:
            md, mv = macro_lookup["risk_count"]
            mask = (md >= p0) & (md <= p1)
            period_avg_risk_count = float(np.nanmean(mv[mask])) if mask.any() else np.nan
        if "exposure" in macro_lookup:
            md, mv = macro_lookup["exposure"]
            mask = (md >= p0) & (md <= p1)
            period_avg_exposure = float(np.nanmean(mv[mask])) if mask.any() else np.nan
        records.append(
            {
                "period_start_close": period_start_close,
                "period_end_close": period_end_close,
                "period_ret": safe_ret(period_end_close, period_start_close),
                "pre_filing_20d_close": pre_filing_20d_close,
                "filing_close": filing_close,
                "post_filing_5d_close": post_filing_5d_close,
                "post_filing_30d_close": post_filing_30d_close,
                "post_filing_60d_close": post_filing_60d_close,
                "post_filing_90d_close": post_filing_90d_close,
                "pre_filing_20d_ret": safe_ret(filing_close, pre_filing_20d_close),
                "post_filing_5d_ret": safe_ret(post_filing_5d_close, filing_close),
                "post_filing_30d_ret": safe_ret(post_filing_30d_close, filing_close),
                "post_filing_60d_ret": safe_ret(post_filing_60d_close, filing_close),
                "post_filing_90d_ret": safe_ret(post_filing_90d_close, filing_close),
                "period_kospi_ret": safe_ret(period_kospi_end, period_kospi_start),
                "period_avg_vix": period_avg_vix,
                "period_avg_usdkrw": period_avg_usdkrw,
                "period_avg_us10y": period_avg_us10y,
                "period_avg_kr10y": period_avg_kr10y,
                "period_avg_gold_kr_close": period_avg_gold,
                "period_avg_risk_count": period_avg_risk_count,
                "period_avg_exposure": period_avg_exposure,
            }
        )
    return pd.concat([panel.reset_index(drop=True), pd.DataFrame.from_records(records)], axis=1)


def build_panel(feature_path: Path, fundamental_path: Path, output_csv: Path) -> pd.DataFrame:
    price_df, meta = load_price(feature_path)
    fund_df = load_fundamental(fundamental_path)
    panel = fund_df.merge(meta, on="code", how="left")
    price_lookup = build_price_lookup(price_df[["code", "date", "close"]])
    _, macro_lookup = build_macro_lookup(price_df)
    panel = enrich_with_price(panel, price_lookup, macro_lookup)

    panel["quarter_label"] = (
        panel["fiscal_year"].astype(str)
        + "-"
        + panel["reprt_code"].map(
            {"11013": "Q1", "11012": "Q2", "11014": "Q3", "11011": "Q4"}
        ).fillna(panel["reprt_code"])
    )
    panel["quarter_order"] = panel["reprt_code"].map({"11013": 1, "11012": 2, "11014": 3, "11011": 4}).fillna(9)
    panel["period_excess_ret"] = panel["period_ret"] - panel["period_kospi_ret"]

    ordered = [
        "code",
        "name",
        "market",
        "industry",
        "corp_code",
        "corp_name",
        "fiscal_year",
        "reprt_code",
        "quarter_label",
        "period_start",
        "period_end",
        "filing_date",
        "rcept_no",
        "revenue_q",
        "op_income_q",
        "net_income_q",
        "op_margin_q",
        "roe_simple_q",
        "net_margin_q",
        "revenue_q_yoy",
        "op_income_q_yoy",
        "net_income_q_yoy",
        "revenue_q_yoy_pct",
        "op_income_q_yoy_pct",
        "net_income_q_yoy_pct",
        "revenue_q_qoq",
        "op_income_q_qoq",
        "net_income_q_qoq",
        "net_margin_q_qoq",
        "op_margin_q_qoq",
        "op_income_vs_revenue_qoq_gap",
        "net_income_vs_revenue_qoq_gap",
        "op_income_qoq_accel",
        "net_income_qoq_accel",
        "revenue_t4_sum",
        "op_income_t4_sum",
        "net_income_t4_sum",
        "op_income_t4_std",
        "net_income_t4_std",
        "non_operating_profit_flag",
        "net_op_gap_ratio",
        "extreme_net_margin_flag",
        "earnings_exception_flag",
        "revenue_q_qoq_pct",
        "op_income_q_qoq_pct",
        "net_income_q_qoq_pct",
        "period_start_close",
        "period_end_close",
        "period_ret",
        "period_excess_ret",
        "pre_filing_20d_close",
        "filing_close",
        "post_filing_5d_close",
        "post_filing_30d_close",
        "post_filing_60d_close",
        "post_filing_90d_close",
        "pre_filing_20d_ret",
        "post_filing_5d_ret",
        "post_filing_30d_ret",
        "post_filing_60d_ret",
        "post_filing_90d_ret",
        "period_kospi_ret",
        "period_avg_vix",
        "period_avg_usdkrw",
        "period_avg_us10y",
        "period_avg_kr10y",
        "period_avg_gold_kr_close",
        "period_avg_risk_count",
        "period_avg_exposure",
    ]
    panel = panel.sort_values(["code", "fiscal_year", "quarter_order"]).reset_index(drop=True)
    panel = panel[ordered]

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_csv, index=False, encoding="utf-8-sig")
    panel.to_pickle(output_csv.with_suffix(".pkl"))
    return panel


def main():
    parser = argparse.ArgumentParser(description="Build quarterly stock panel: one row per stock-quarter.")
    parser.add_argument(
        "--feature",
        type=Path,
        default=data_path("feature_daily.pkl"),
        help="Path to feature_daily.pkl/csv",
    )
    parser.add_argument(
        "--fundamental",
        type=Path,
        default=data_path("fundamental_quarterly_multi.csv"),
        help="Path to quarterly fundamental csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=data_path("quarterly_stock_panel.csv"),
        help="Output csv path",
    )
    args = parser.parse_args()

    panel = build_panel(args.feature, args.fundamental, args.output)
    print(f"[saved] {args.output}")
    print(f"[rows] {len(panel):,}")
    print(f"[codes] {panel['code'].nunique():,}")


if __name__ == "__main__":
    main()
