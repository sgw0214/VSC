import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from new_strategy.paths import data_path, output_path
from new_strategy.legacy_analysis.analyze_stock_correlations import load_feature_dataset


PERIOD_FEATURES = [
    "revenue_yoy_pct_period",
    "op_income_yoy_pct_period",
    "net_income_yoy_pct_period",
    "revenue_qoq_pct_period",
    "op_income_qoq_pct_period",
    "net_income_qoq_pct_period",
    "op_margin_period",
]


EVENT_FEATURES = [
    "revenue_yoy_pct_pti",
    "op_income_yoy_pct_pti",
    "net_income_yoy_pct_pti",
    "revenue_qoq_pct_pti",
    "op_income_qoq_pct_pti",
    "net_income_qoq_pct_pti",
    "op_margin_pti",
]


def add_period_price_change(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    grp_cols = ["code", "fiscal_year_period", "reprt_code_period"]
    period_ret = (
        out.groupby(grp_cols)
        .agg(period_start_close=("close", "first"), period_end_close=("close", "last"))
        .reset_index()
    )
    period_ret["period_ret"] = period_ret["period_end_close"] / period_ret["period_start_close"] - 1.0
    period_ret["period_log_ret"] = np.log(period_ret["period_end_close"] / period_ret["period_start_close"])

    feat_cols = ["industry"] + [c for c in PERIOD_FEATURES if c in out.columns]
    period_feat = (
        out.groupby(grp_cols, as_index=False)[feat_cols]
        .last()
    )
    return period_ret.merge(period_feat, on=grp_cols, how="left")


def build_period_industry_corr(df: pd.DataFrame, min_obs: int) -> pd.DataFrame:
    rows = []
    for industry, g in df.groupby("industry", dropna=False):
        if pd.isna(industry):
            continue
        n_codes = int(g["code"].nunique())
        for feat in [c for c in PERIOD_FEATURES if c in g.columns]:
            pair = g[[feat, "period_ret"]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(pair) < min_obs:
                continue
            corr = pair[feat].corr(pair["period_ret"])
            rows.append(
                {
                    "industry": industry,
                    "feature": feat,
                    "corr_with_period_ret": float(corr) if pd.notna(corr) else np.nan,
                    "abs_corr": float(abs(corr)) if pd.notna(corr) else np.nan,
                    "n_obs": int(len(pair)),
                    "n_codes": n_codes,
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["industry", "abs_corr"], ascending=[True, False]).reset_index(drop=True)
    return out


def _event_window_return(price_map: pd.DataFrame, code: str, base_date: pd.Timestamp, offset: int) -> float:
    g = price_map[price_map["code"] == code]
    if g.empty:
        return np.nan
    dates = g["date"].values
    idx = g.index[g["date"] == base_date]
    if len(idx) == 0:
        return np.nan
    pos = g.index.get_loc(idx[0])
    if isinstance(pos, slice):
        return np.nan
    tgt_pos = pos + offset
    if tgt_pos < 0 or tgt_pos >= len(g):
        return np.nan
    base_close = g.iloc[pos]["close"]
    tgt_close = g.iloc[tgt_pos]["close"]
    if pd.isna(base_close) or pd.isna(tgt_close) or base_close == 0:
        return np.nan
    return float(tgt_close / base_close - 1.0)


def build_event_base(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "code",
        "name",
        "industry",
        "date",
        "close",
        "filing_date_pti",
        "reprt_code_pti",
        "fiscal_year_pti",
    ] + [c for c in EVENT_FEATURES if c in df.columns]

    base = df[cols].copy()
    base["date"] = pd.to_datetime(base["date"], errors="coerce")
    base["filing_date_pti"] = pd.to_datetime(base["filing_date_pti"], errors="coerce")
    base = base.dropna(subset=["date"])
    price_map = base[["code", "date", "close"]].drop_duplicates(["code", "date"]).sort_values(["code", "date"]).reset_index(drop=True)

    events = (
        base.dropna(subset=["filing_date_pti"])
        .sort_values(["code", "date"])
        .groupby(["code", "filing_date_pti"], as_index=False)
        .last()
    )

    for offset in [-20, -10, -5, 0, 5, 20, 60]:
        events[f"ret_{offset:+d}d"] = events.apply(
            lambda x: _event_window_return(price_map, x["code"], x["filing_date_pti"], offset), axis=1
        )
    return events


def build_event_industry_summary(events: pd.DataFrame, min_obs: int) -> pd.DataFrame:
    rows = []
    ret_cols = [c for c in events.columns if c.startswith("ret_")]
    for industry, g in events.groupby("industry", dropna=False):
        if pd.isna(industry):
            continue
        n_codes = int(g["code"].nunique())
        for feat in [c for c in EVENT_FEATURES if c in g.columns]:
            for ret_col in ret_cols:
                pair = g[[feat, ret_col]].apply(pd.to_numeric, errors="coerce").dropna()
                if len(pair) < min_obs:
                    continue
                corr = pair[feat].corr(pair[ret_col])
                rows.append(
                    {
                        "industry": industry,
                        "feature": feat,
                        "event_ret": ret_col,
                        "corr": float(corr) if pd.notna(corr) else np.nan,
                        "abs_corr": float(abs(corr)) if pd.notna(corr) else np.nan,
                        "n_obs": int(len(pair)),
                        "n_codes": n_codes,
                    }
                )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["industry", "event_ret", "abs_corr"], ascending=[True, True, False]).reset_index(drop=True)
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Explanatory analysis between fundamentals and price behavior.")
    p.add_argument("--input", default=str(data_path("feature_daily.pkl")))
    p.add_argument("--min-obs", type=int, default=300)
    p.add_argument("--period-output", default=str(output_path("industry_period_price_relationship.csv")))
    p.add_argument("--event-output", default=str(output_path("industry_event_relationship.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    df = load_feature_dataset(Path(args.input))

    period_base = add_period_price_change(df)
    period_out_df = build_period_industry_corr(period_base, min_obs=args.min_obs)

    event_base = build_event_base(df)
    event_out_df = build_event_industry_summary(event_base, min_obs=args.min_obs)

    period_out = Path(args.period_output)
    event_out = Path(args.event_output)
    period_out.parent.mkdir(parents=True, exist_ok=True)
    period_out_df.to_csv(period_out, index=False, encoding="utf-8-sig")
    event_out_df.to_csv(event_out, index=False, encoding="utf-8-sig")

    print(f"[saved] {period_out}")
    print(f"[saved] {event_out}")
    print(f"[period_rows] {len(period_out_df):,}")
    print(f"[event_rows] {len(event_out_df):,}")
    if not period_out_df.empty:
        print("[period top]")
        print(period_out_df.groupby("industry").head(3).head(30).to_string(index=False))
    if not event_out_df.empty:
        print("[event top]")
        print(event_out_df.groupby(["industry", "event_ret"]).head(3).head(30).to_string(index=False))


if __name__ == "__main__":
    main()
