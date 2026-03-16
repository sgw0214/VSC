import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from new_strategy.paths import data_path


REQUIRED = ["date", "kospi", "vix", "usdkrw", "us10y", "kr10y"]
OPTIONAL = ["gold_kr_close", "gold_kr_ret", "gold_kr_volume", "gold_kr_trading_value"]


def build_macro_features(raw: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f"Missing macro columns: {missing}")

    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    coverage_rows = []
    for col in REQUIRED[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        raw_non_null = int(df[col].notna().sum())
        if raw_non_null == 0:
            raise ValueError(f"Column `{col}` has no values. Fill macro_daily first.")
        df[col] = df[col].ffill()
        filled_non_null = int(df[col].notna().sum())
        coverage_rows.append(
            {
                "column": col,
                "raw_non_null": raw_non_null,
                "raw_coverage": raw_non_null / len(df),
                "filled_non_null": filled_non_null,
                "filled_coverage": filled_non_null / len(df),
            }
        )

    has_gold = "gold_kr_close" in df.columns
    if has_gold:
        for col in OPTIONAL:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                raw_non_null = int(df[col].notna().sum())
                if col == "gold_kr_close" and raw_non_null > 0:
                    df[col] = df[col].ffill()
                coverage_rows.append(
                    {
                        "column": col,
                        "raw_non_null": raw_non_null,
                        "raw_coverage": raw_non_null / len(df),
                        "filled_non_null": int(df[col].notna().sum()),
                        "filled_coverage": int(df[col].notna().sum()) / len(df),
                    }
                )

    # Coverage-based grounded correction for sparse kr10y:
    # fill from us10y using median spread computed only on overlapping observed points.
    overlap = df[["kr10y", "us10y"]].dropna()
    if not overlap.empty:
        spread = float((overlap["kr10y"] - overlap["us10y"]).median())
        need_fill = df["kr10y"].isna() & df["us10y"].notna()
        if int(need_fill.sum()) > 0:
            df.loc[need_fill, "kr10y"] = df.loc[need_fill, "us10y"] + spread

    df["vix_ma60"] = df["vix"].rolling(60, min_periods=30).mean()
    df["usdkrw_ma60"] = df["usdkrw"].rolling(60, min_periods=30).mean()
    df["us10y_ma60"] = df["us10y"].rolling(60, min_periods=30).mean()
    df["kr10y_ma60"] = df["kr10y"].rolling(60, min_periods=30).mean()
    if has_gold and int(df["gold_kr_close"].notna().sum()) > 0:
        df["gold_kr_ma60"] = df["gold_kr_close"].rolling(60, min_periods=30).mean()
    else:
        df["gold_kr_ma60"] = np.nan

    df["cond_vix_high"] = df["vix"] > (df["vix_ma60"] * 1.2)
    df["cond_fx_risk"] = df["usdkrw"] > df["usdkrw_ma60"]
    df["cond_rate_risk"] = (df["us10y"] > df["us10y_ma60"]) | (df["kr10y"] > df["kr10y_ma60"])
    df["cond_gold_risk"] = False
    if has_gold and int(df["gold_kr_close"].notna().sum()) > 0:
        # Rising gold above trend often aligns with a defensive regime.
        df["cond_gold_risk"] = df["gold_kr_close"] > (df["gold_kr_ma60"] * 1.05)

    signal_cols = ["cond_vix_high", "cond_fx_risk", "cond_rate_risk"]
    if has_gold and int(df["gold_kr_close"].notna().sum()) > 0:
        signal_cols.append("cond_gold_risk")

    df["risk_count"] = sum(df[c].astype(int) for c in signal_cols)
    n_signals = len(signal_cols)
    if n_signals == 3:
        risk_on = df["risk_count"] == 0
        neutral = df["risk_count"] == 1
        risk_off = df["risk_count"] >= 2
    else:
        risk_on = df["risk_count"] <= 1
        neutral = df["risk_count"] == 2
        risk_off = df["risk_count"] >= 3

    df["regime"] = np.select([risk_on, neutral, risk_off], ["risk_on", "neutral", "risk_off"], default="neutral")
    df["exposure"] = df["regime"].map({"risk_on": 1.0, "neutral": 0.3, "risk_off": 0.1}).astype(float)
    df.attrs["coverage_report"] = pd.DataFrame(coverage_rows)
    return df


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build macro regime file.")
    p.add_argument("--input", default=str(data_path("macro_daily.csv")))
    p.add_argument("--output", default=str(data_path("macro_regime.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    raw = pd.read_csv(args.input)
    df = build_macro_features(raw)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[saved] {out}")
    print(df["regime"].value_counts(dropna=False).to_string())
    coverage = df.attrs.get("coverage_report")
    if coverage is not None:
        cov_out = out.with_name("macro_coverage_report.csv")
        coverage.to_csv(cov_out, index=False, encoding="utf-8-sig")
        print(f"[saved] {cov_out}")
        print(coverage.to_string(index=False))


if __name__ == "__main__":
    main()
