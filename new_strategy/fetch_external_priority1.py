from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable, Dict

import pandas as pd

from new_strategy.external_sources import (
    DEFAULT_START_DATE,
    ensure_external_dirs,
    initialize_empty_file,
    iter_specs,
    resolve_storage_path,
    today_str,
    upsert_by_date,
)
from new_strategy.paths import data_path


def _fetch_fred_series(series_id: str, value_name: str, start_date: str, end_date: str) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    raw = pd.read_csv(url)
    raw = raw.rename(columns={"observation_date": "date", series_id: value_name})
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw[value_name] = pd.to_numeric(raw[value_name], errors="coerce")
    raw = raw.dropna(subset=["date"])
    raw = raw[(raw["date"] >= pd.Timestamp(start_date)) & (raw["date"] <= pd.Timestamp(end_date))].copy()
    raw["date"] = raw["date"].dt.strftime("%Y-%m-%d")
    return raw[["date", value_name]].reset_index(drop=True)


def fetch_oil_brent(start_date: str, end_date: str) -> pd.DataFrame:
    return _fetch_fred_series("DCOILBRENTEU", "brent", start_date, end_date)


def fetch_consumer_sentiment_kr(start_date: str, end_date: str) -> pd.DataFrame:
    return _fetch_fred_series("CSCICP02KRM066S", "consumer_sentiment", start_date, end_date)


def fetch_retail_sales_kr(start_date: str, end_date: str) -> pd.DataFrame:
    return _fetch_fred_series("KORSLRTTO01GPSAM", "retail_sales_index", start_date, end_date)


def fetch_china_pmi(start_date: str, end_date: str) -> pd.DataFrame:
    # Public proxy via FRED/OECD manufacturing business tendency survey.
    return _fetch_fred_series(
        "CHNBSCICP02STSAM",
        "china_mfg_confidence_proxy",
        start_date,
        end_date,
    )


def fetch_kr_short_rate_proxy(start_date: str, end_date: str) -> pd.DataFrame:
    return _fetch_fred_series(
        "IR3TIB01KRM156N",
        "kr_short_rate_proxy",
        start_date,
        end_date,
    )


def fetch_kr_interest_rate_spread_proxy(start_date: str, end_date: str) -> pd.DataFrame:
    return _fetch_fred_series(
        "KORLOCOSIORSTM",
        "kr_interest_rate_spread_proxy",
        start_date,
        end_date,
    )


def fetch_grains(start_date: str, end_date: str) -> pd.DataFrame:
    series_map = {
        "wheat": "PWHEAMTUSDM",
        "corn": "PMAIZMTUSDM",
        "soybean": "PSOYBUSDM",
    }
    dfs = []
    for value_name, series_id in series_map.items():
        dfs.append(_fetch_fred_series(series_id, value_name, start_date, end_date))
    out = dfs[0]
    for df in dfs[1:]:
        out = out.merge(df, on="date", how="outer")
    out = out.sort_values("date").reset_index(drop=True)
    out["grain_composite"] = out[["wheat", "corn", "soybean"]].mean(axis=1)
    return out


def fetch_kospi_trading_value(start_date: str, end_date: str) -> pd.DataFrame:
    frames = []

    feature_src = data_path("feature_daily-001.csv")
    if feature_src.exists():
        usecols = ["date", "market", "trading_value"]
        for chunk in pd.read_csv(feature_src, usecols=usecols, chunksize=250_000, low_memory=False):
            chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce")
            chunk = chunk[
                (chunk["market"] == "KOSPI")
                & chunk["date"].notna()
                & (chunk["date"] >= pd.Timestamp(start_date))
                & (chunk["date"] <= pd.Timestamp(end_date))
            ].copy()
            if chunk.empty:
                continue
            chunk["trading_value"] = pd.to_numeric(chunk["trading_value"], errors="coerce")
            agg = chunk.groupby("date", as_index=False)["trading_value"].sum()
            agg["source_rank"] = 0
            frames.append(agg)

    stock_root = data_path("..", "Stock").resolve()
    xlsx_files = sorted(stock_root.glob("basic_*.xlsx")) if stock_root.exists() else []
    for xlsx in xlsx_files:
        try:
            day = pd.to_datetime(xlsx.stem.replace("basic_", ""), format="%Y%m%d", errors="coerce")
        except Exception:
            day = pd.NaT
        if pd.isna(day) or day < pd.Timestamp(start_date) or day > pd.Timestamp(end_date):
            continue
        try:
            day_df = pd.read_excel(xlsx, usecols=["거래대금", "일자"])
        except Exception:
            continue
        day_df["거래대금"] = pd.to_numeric(day_df["거래대금"], errors="coerce")
        total = float(day_df["거래대금"].sum())
        frames.append(pd.DataFrame({"date": [day], "trading_value": [total], "source_rank": [1]}))

    if not frames:
        return pd.DataFrame(columns=["date", "kospi_trading_value"])

    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["date", "source_rank"]).drop_duplicates(subset=["date"], keep="last")
    out = out.rename(columns={"trading_value": "kospi_trading_value"})
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out = out[["date", "kospi_trading_value"]].sort_values("date").reset_index(drop=True)
    return out


FETCHERS: Dict[str, Callable[[str, str], pd.DataFrame]] = {
    "china_pmi": fetch_china_pmi,
    "kr_3y": fetch_kr_short_rate_proxy,
    "yield_curve_10y3y": fetch_kr_interest_rate_spread_proxy,
    "oil_brent": fetch_oil_brent,
    "consumer_sentiment_kr": fetch_consumer_sentiment_kr,
    "retail_sales_kr": fetch_retail_sales_kr,
    "grains": fetch_grains,
    "kospi_trading_value": fetch_kospi_trading_value,
}


def build_status_row(indicator_id: str, storage_path: Path, fetched_rows: int, status: str, message: str) -> dict:
    return {
        "indicator_id": indicator_id,
        "storage_file": str(storage_path),
        "fetched_rows": int(fetched_rows),
        "status": status,
        "message": message,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch or initialize priority-1 external indicators.")
    p.add_argument("--start-date", default=DEFAULT_START_DATE)
    p.add_argument("--end-date", default=today_str())
    p.add_argument("--only", default="", help="Optional comma-separated indicator ids")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    ensure_external_dirs()
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    status_rows = []

    for spec in iter_specs(priority=1):
        if only and spec.indicator_id not in only:
            continue
        storage_path = resolve_storage_path(spec.storage_file)
        initialize_empty_file(spec)
        fetcher = FETCHERS.get(spec.indicator_id)
        if fetcher is None:
            status_rows.append(
                build_status_row(
                    indicator_id=spec.indicator_id,
                    storage_path=storage_path,
                    fetched_rows=0,
                    status="pending_source_impl",
                    message=f"collection_mode={spec.collection_mode}, primary_source={spec.primary_source}",
                )
            )
            continue
        try:
            fetched = fetcher(args.start_date, args.end_date)
            merged = upsert_by_date(storage_path, fetched, date_column=spec.date_column)
            status_rows.append(
                build_status_row(
                    indicator_id=spec.indicator_id,
                    storage_path=storage_path,
                    fetched_rows=len(merged),
                    status="ok",
                    message=f"{args.start_date}..{args.end_date}",
                )
            )
            print(f"[saved] {storage_path} rows={len(merged):,}")
        except Exception as exc:
            status_rows.append(
                build_status_row(
                    indicator_id=spec.indicator_id,
                    storage_path=storage_path,
                    fetched_rows=0,
                    status="error",
                    message=str(exc),
                )
            )

    out = resolve_storage_path("priority1_fetch_run_status.csv")
    pd.DataFrame(status_rows).to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[saved] {out}")


if __name__ == "__main__":
    main()
