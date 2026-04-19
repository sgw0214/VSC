import argparse
from pathlib import Path

import pandas as pd

from new_strategy.paths import data_path
from new_strategy.strategy_rules import StrategyConfig, add_features


FUND_RENAME = {
    "종목코드": "code",
    "법인코드": "corp_code",
    "법인명": "corp_name",
    "사업연도": "bsns_year",
    "보고서코드": "reprt_code",
    "접수번호": "rcept_no",
    "공시일": "rcept_dt",
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

RAW_PRICE_COLS = [
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

REPORT_ORDER = {"11013": 0, "11012": 1, "11014": 2, "11011": 3}


def load_price(path: Path, cfg: StrategyConfig) -> pd.DataFrame:
    if path.suffix.lower() == ".pkl":
        df = pd.read_pickle(path)
    else:
        df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["code", "date"]).reset_index(drop=True)
    return add_features(df, cfg)


def load_price_raw(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".pkl":
        df = pd.read_pickle(path)
    else:
        df = pd.read_csv(path, dtype={"code": str}, usecols=lambda c: c in RAW_PRICE_COLS, low_memory=False)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values(["code", "date"]).reset_index(drop=True)


def load_macro(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    drop_cols = [c for c in df.columns if str(c).endswith("_old")]
    if drop_cols:
        df = df.drop(columns=drop_cols)
    return df


def _reprt_period_bounds(bsns_year: int, reprt_code: str) -> tuple:
    year = int(bsns_year)
    code = str(reprt_code)
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
    df = pd.read_csv(path, low_memory=False)
    df = df.rename(columns={k: v for k, v in FUND_RENAME.items() if k in df.columns})
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["bsns_year"] = pd.to_numeric(df["bsns_year"], errors="coerce").astype("Int64")
    df["reprt_code"] = df["reprt_code"].astype(str)
    df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], errors="coerce")

    for col in ["revenue_q", "op_income_q", "net_income_q", "op_margin_q", "roe_simple_q"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    bounds = df.apply(lambda x: _reprt_period_bounds(x["bsns_year"], x["reprt_code"]), axis=1, result_type="expand")
    df["period_start"] = bounds[0]
    df["period_end"] = bounds[1]
    df["_report_order"] = df["reprt_code"].map(REPORT_ORDER).fillna(999)
    df = df.sort_values(["code", "bsns_year", "_report_order", "rcept_dt"]).reset_index(drop=True)
    grp = df.groupby("code", sort=False)
    for src in ["revenue_q", "op_income_q", "net_income_q", "op_margin_q", "roe_simple_q"]:
        prev_y = grp[src].shift(4)
        prev_q = grp[src].shift(1)
        df[f"{src}_yoy"] = df[src] - prev_y
        df[f"{src}_qoq"] = df[src] - prev_q
        df[f"{src}_yoy_pct"] = df[f"{src}_yoy"] / prev_y.abs().replace(0, pd.NA)
        df[f"{src}_qoq_pct"] = df[f"{src}_qoq"] / prev_q.abs().replace(0, pd.NA)
    df = df.sort_values(["code", "rcept_dt", "bsns_year", "_report_order"]).reset_index(drop=True)
    df = df.drop(columns=["_report_order"])
    return df


def merge_pti(price_df: pd.DataFrame, fund_df: pd.DataFrame) -> pd.DataFrame:
    parts = []
    keep = [
        "rcept_dt",
        "bsns_year",
        "reprt_code",
        "revenue_q",
        "op_income_q",
        "net_income_q",
        "op_margin_q",
        "roe_simple_q",
        "revenue_q_yoy",
        "op_income_q_yoy",
        "net_income_q_yoy",
        "revenue_q_qoq",
        "op_income_q_qoq",
        "net_income_q_qoq",
        "revenue_q_yoy_pct",
        "op_income_q_yoy_pct",
        "net_income_q_yoy_pct",
        "revenue_q_qoq_pct",
        "op_income_q_qoq_pct",
        "net_income_q_qoq_pct",
    ]

    for code, left in price_df.groupby("code", sort=False):
        right = fund_df.loc[fund_df["code"] == code, keep].dropna(subset=["rcept_dt"]).sort_values("rcept_dt")
        left = left.sort_values("date").copy()
        if right.empty:
            left["filing_date_pti"] = pd.NaT
            left["days_since_filing"] = pd.NA
            left["revenue_pti"] = pd.NA
            left["op_income_pti"] = pd.NA
            left["net_income_pti"] = pd.NA
            left["op_margin_pti"] = pd.NA
            left["roe_simple_pti"] = pd.NA
            left["revenue_yoy_pti"] = pd.NA
            left["op_income_yoy_pti"] = pd.NA
            left["net_income_yoy_pti"] = pd.NA
            left["revenue_qoq_pti"] = pd.NA
            left["op_income_qoq_pti"] = pd.NA
            left["net_income_qoq_pti"] = pd.NA
            left["revenue_yoy_pct_pti"] = pd.NA
            left["op_income_yoy_pct_pti"] = pd.NA
            left["net_income_yoy_pct_pti"] = pd.NA
            left["revenue_qoq_pct_pti"] = pd.NA
            left["op_income_qoq_pct_pti"] = pd.NA
            left["net_income_qoq_pct_pti"] = pd.NA
            left["fiscal_year_pti"] = pd.NA
            left["reprt_code_pti"] = pd.NA
            parts.append(left)
            continue

        merged = pd.merge_asof(
            left,
            right.rename(
                columns={
                    "rcept_dt": "filing_date_pti",
                    "bsns_year": "fiscal_year_pti",
                    "reprt_code": "reprt_code_pti",
                    "revenue_q": "revenue_pti",
                    "op_income_q": "op_income_pti",
                    "net_income_q": "net_income_pti",
                    "op_margin_q": "op_margin_pti",
                    "roe_simple_q": "roe_simple_pti",
                    "revenue_q_yoy": "revenue_yoy_pti",
                    "op_income_q_yoy": "op_income_yoy_pti",
                    "net_income_q_yoy": "net_income_yoy_pti",
                    "revenue_q_qoq": "revenue_qoq_pti",
                    "op_income_q_qoq": "op_income_qoq_pti",
                    "net_income_q_qoq": "net_income_qoq_pti",
                    "revenue_q_yoy_pct": "revenue_yoy_pct_pti",
                    "op_income_q_yoy_pct": "op_income_yoy_pct_pti",
                    "net_income_q_yoy_pct": "net_income_yoy_pct_pti",
                    "revenue_q_qoq_pct": "revenue_qoq_pct_pti",
                    "op_income_q_qoq_pct": "op_income_qoq_pct_pti",
                    "net_income_q_qoq_pct": "net_income_qoq_pct_pti",
                }
            ).sort_values("filing_date_pti"),
            left_on="date",
            right_on="filing_date_pti",
            direction="backward",
        )
        merged["days_since_filing"] = (merged["date"] - merged["filing_date_pti"]).dt.days
        parts.append(merged)

    return pd.concat(parts, ignore_index=True)


def quarter_code_from_date(series: pd.Series) -> pd.Series:
    month = series.dt.month
    out = pd.Series(index=series.index, dtype="object")
    out[(month >= 1) & (month <= 3)] = "11013"
    out[(month >= 4) & (month <= 6)] = "11012"
    out[(month >= 7) & (month <= 9)] = "11014"
    out[(month >= 10) & (month <= 12)] = "11011"
    return out


def merge_period(df: pd.DataFrame, fund_df: pd.DataFrame) -> pd.DataFrame:
    period_ref = fund_df[
        [
            "code",
            "bsns_year",
            "reprt_code",
            "period_start",
            "period_end",
            "revenue_q",
            "op_income_q",
            "net_income_q",
            "op_margin_q",
            "roe_simple_q",
            "revenue_q_yoy",
            "op_income_q_yoy",
            "net_income_q_yoy",
            "revenue_q_qoq",
            "op_income_q_qoq",
            "net_income_q_qoq",
            "revenue_q_yoy_pct",
            "op_income_q_yoy_pct",
            "net_income_q_yoy_pct",
            "revenue_q_qoq_pct",
            "op_income_q_qoq_pct",
            "net_income_q_qoq_pct",
        ]
    ].copy()
    period_ref = period_ref.rename(
        columns={
            "bsns_year": "fiscal_year_period",
            "reprt_code": "reprt_code_period",
            "revenue_q": "revenue_period",
            "op_income_q": "op_income_period",
            "net_income_q": "net_income_period",
            "op_margin_q": "op_margin_period",
            "roe_simple_q": "roe_simple_period",
            "revenue_q_yoy": "revenue_yoy_period",
            "op_income_q_yoy": "op_income_yoy_period",
            "net_income_q_yoy": "net_income_yoy_period",
            "revenue_q_qoq": "revenue_qoq_period",
            "op_income_q_qoq": "op_income_qoq_period",
            "net_income_q_qoq": "net_income_qoq_period",
            "revenue_q_yoy_pct": "revenue_yoy_pct_period",
            "op_income_q_yoy_pct": "op_income_yoy_pct_period",
            "net_income_q_yoy_pct": "net_income_yoy_pct_period",
            "revenue_q_qoq_pct": "revenue_qoq_pct_period",
            "op_income_q_qoq_pct": "op_income_qoq_pct_period",
            "net_income_q_qoq_pct": "net_income_qoq_pct_period",
        }
    )
    period_ref = period_ref.sort_values(["code", "fiscal_year_period", "reprt_code_period"])

    out = df.copy()
    out["fiscal_year_period"] = out["date"].dt.year
    out["reprt_code_period"] = quarter_code_from_date(out["date"])
    out = out.merge(period_ref, on=["code", "fiscal_year_period", "reprt_code_period"], how="left")
    return out


def build_feature_dataset(price_path: Path, macro_path: Path, fund_path: Path, output_path: Path) -> pd.DataFrame:
    cfg = StrategyConfig()
    price = load_price(price_path, cfg)
    macro = load_macro(macro_path)
    fund = load_fundamental(fund_path)

    merged = price.merge(macro, on="date", how="left")
    merged = merge_pti(merged, fund)
    merged = merge_period(merged, fund)
    merged = merged.sort_values(["date", "code"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False, encoding="utf-8-sig")
    parquet_path = output_path.with_suffix(".parquet")
    pickle_path = output_path.with_suffix(".pkl")
    merged.to_pickle(pickle_path)
    print(f"[saved] {output_path}")
    print(f"[saved] {pickle_path}")
    try:
        merged.to_parquet(parquet_path, index=False)
        print(f"[saved] {parquet_path}")
    except Exception as exc:
        print(f"[warn] parquet save skipped: {exc}")
    print(f"[rows] {len(merged):,}")
    print(f"[codes] {merged['code'].nunique():,}")
    print(
        "[coverage]",
        {
            "pti_non_null": int(merged["revenue_pti"].notna().sum()),
            "period_non_null": int(merged["revenue_period"].notna().sum()),
        },
    )
    return merged


def build_feature_dataset_incremental(
    price_path: Path,
    macro_path: Path,
    fund_path: Path,
    output_path: Path,
    history_rows: int = 140,
    write_csv: bool = True,
    write_pickle: bool = True,
    write_parquet: bool = False,
) -> pd.DataFrame:
    pickle_path = output_path.with_suffix(".pkl")
    parquet_path = output_path.with_suffix(".parquet")

    if pickle_path.exists():
        existing = pd.read_pickle(pickle_path)
    elif output_path.exists():
        existing = pd.read_csv(output_path, dtype={"code": str}, low_memory=False)
    else:
        return build_feature_dataset(price_path=price_path, macro_path=macro_path, fund_path=fund_path, output_path=output_path)

    existing["code"] = existing["code"].astype(str).str.zfill(6)
    existing["date"] = pd.to_datetime(existing["date"], errors="coerce")
    existing = existing.dropna(subset=["date"]).sort_values(["code", "date"]).reset_index(drop=True)
    if existing.empty:
        return build_feature_dataset(price_path=price_path, macro_path=macro_path, fund_path=fund_path, output_path=output_path)

    existing_max = existing["date"].max()
    price_raw = load_price_raw(price_path)
    new_price = price_raw.loc[price_raw["date"] > existing_max].copy()
    if new_price.empty:
        print("[incremental] no new price rows; feature dataset unchanged")
        return existing

    history = (
        existing[[c for c in RAW_PRICE_COLS if c in existing.columns]]
        .sort_values(["code", "date"])
        .groupby("code", group_keys=False)
        .tail(history_rows)
        .copy()
    )
    calc_input = (
        pd.concat([history, new_price], ignore_index=True)
        .drop_duplicates(subset=["code", "date"], keep="last")
        .sort_values(["code", "date"])
        .reset_index(drop=True)
    )
    calc_features = add_features(calc_input, StrategyConfig())
    delta = calc_features.loc[calc_features["date"] > existing_max].copy()

    macro = load_macro(macro_path)
    fund = load_fundamental(fund_path)
    delta = delta.merge(macro, on="date", how="left")
    delta = merge_pti(delta, fund)
    delta = merge_period(delta, fund)
    delta = delta.sort_values(["date", "code"]).reset_index(drop=True)

    updated = pd.concat([existing, delta], ignore_index=True).sort_values(["date", "code"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if write_pickle:
        updated.to_pickle(pickle_path)
        print(f"[saved] {pickle_path}")

    if write_csv:
        if output_path.exists():
            aligned = delta.reindex(columns=existing.columns)
            aligned.to_csv(output_path, mode="a", header=False, index=False, encoding="utf-8")
        else:
            updated.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"[saved] {output_path}")

    if write_parquet:
        try:
            updated.to_parquet(parquet_path, index=False)
            print(f"[saved] {parquet_path}")
        except Exception as exc:
            print(f"[warn] parquet save skipped: {exc}")

    print(
        "[incremental]",
        {
            "appended_dates": sorted(pd.to_datetime(delta["date"]).dt.strftime("%Y-%m-%d").unique().tolist()),
            "appended_rows": int(len(delta)),
            "new_max_date": None if updated.empty else str(updated["date"].max().date()),
        },
    )
    return updated


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build date+code feature dataset with PTI and period fundamentals.")
    p.add_argument("--price-panel", default=str(data_path("price_panel.csv")))
    p.add_argument("--macro", default=str(data_path("macro_regime_v3_rec.csv")))
    p.add_argument("--fundamental", default=str(data_path("fundamental_quarterly_multi.csv")))
    p.add_argument("--output", default=str(data_path("feature_daily.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    build_feature_dataset(
        price_path=Path(args.price_panel),
        macro_path=Path(args.macro),
        fund_path=Path(args.fundamental),
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    main()
