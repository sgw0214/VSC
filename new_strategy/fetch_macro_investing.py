import argparse
import io
import re
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

from new_strategy.paths import data_path
from bs4 import BeautifulSoup


HEADERS = {"User-Agent": "Mozilla/5.0"}
MACRO_COLS = ["kospi", "vix", "usdkrw", "us10y", "kr10y"]


def _parse_date(text: str) -> Optional[pd.Timestamp]:
    if not text:
        return None
    t = text.strip().replace(".", "-").replace("/", "-")
    t = re.sub(r"[^\d\- ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    for fmt in ("%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y"):
        try:
            return pd.to_datetime(t, format=fmt, errors="raise")
        except Exception:
            pass
    d = pd.to_datetime(t, errors="coerce")
    if pd.isna(d):
        return None
    return d


def _to_float(text: str) -> Optional[float]:
    if text is None:
        return None
    t = text.replace(",", "").replace("%", "").strip()
    if t in ("", "-", "N/A", "null"):
        return None
    try:
        return float(t)
    except Exception:
        return None


def fetch_fred_series(series_id: str) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    date_col = None
    for c in df.columns:
        if str(c).strip().lower() in ("date", "observation_date"):
            date_col = c
            break
    if date_col is None:
        preview = ",".join([str(c) for c in df.columns[:8]])
        raise ValueError(f"Unexpected FRED format for {series_id}: missing DATE-like column (columns={preview})")

    value_cols = [c for c in df.columns if c != date_col]
    if not value_cols:
        raise ValueError(f"Unexpected FRED format for {series_id}: missing value column")
    # FRED may return DATE/observation_date + series_id (e.g., VIXCLS).
    value_col = value_cols[0]
    df = df.rename(columns={date_col: "date", value_col: "value"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["date", "value"]).sort_values("date")[["date", "value"]]


def fetch_yahoo_series(symbol: str, scale: float = 1.0) -> pd.DataFrame:
    sym = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v7/finance/download/{sym}"
    params = {
        "period1": 0,
        "period2": int(time.time()),
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    }
    resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    if "Date" not in df.columns or "Close" not in df.columns:
        raise ValueError(f"Unexpected Yahoo format for {symbol}")
    df = df.rename(columns={"Date": "date", "Close": "value"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce") / scale
    return df.dropna(subset=["date", "value"]).sort_values("date")[["date", "value"]]


def fetch_stooq_vix() -> pd.DataFrame:
    # Stooq format: Date,Open,High,Low,Close,Volume
    url = "https://stooq.com/q/d/l/?s=%5Evix&i=d"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    if "Date" not in df.columns or "Close" not in df.columns:
        raise ValueError("Unexpected Stooq format for ^VIX")
    df = df.rename(columns={"Date": "date", "Close": "value"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["date", "value"]).sort_values("date")[["date", "value"]]


def fetch_stooq_series(symbol: str) -> pd.DataFrame:
    # Stooq format: Date,Open,High,Low,Close,Volume
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    lower_cols = {c.lower(): c for c in df.columns}
    if "date" not in lower_cols or "close" not in lower_cols:
        raise ValueError(f"Unexpected Stooq format for {symbol}")
    dcol = lower_cols["date"]
    ccol = lower_cols["close"]
    df = df.rename(columns={dcol: "date", ccol: "value"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["date", "value"]).sort_values("date")[["date", "value"]]


def fetch_investing_series(url: str, max_rows: int = 10000) -> pd.DataFrame:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for tr in soup.select("table tbody tr"):
        tds = tr.select("td")
        if len(tds) < 2:
            continue
        d = _parse_date(tds[0].get_text(" ", strip=True))
        v = _to_float(tds[1].get_text(" ", strip=True))
        if d is not None and v is not None:
            rows.append((d.normalize(), v))
        if len(rows) >= max_rows:
            break
    return pd.DataFrame(rows, columns=["date", "value"]).drop_duplicates("date").sort_values("date")


def build_kospi_proxy_from_panel(price_panel: Path) -> pd.DataFrame:
    if not price_panel.exists():
        raise FileNotFoundError(f"Missing price panel for proxy KOSPI: {price_panel}")
    df = pd.read_csv(price_panel, usecols=["date", "code", "close"], dtype={"code": str}, low_memory=False)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "code", "close"]).sort_values(["code", "date"])
    df["ret"] = df.groupby("code")["close"].pct_change()
    daily_ret = df.groupby("date")["ret"].median().fillna(0.0).sort_index()
    proxy = (1.0 + daily_ret).cumprod() * 100.0
    return proxy.rename("value").reset_index().rename(columns={"date": "date"})


def build_vix_proxy_from_panel(price_panel: Path) -> pd.DataFrame:
    # Proxy VIX from cross-sectional median return volatility (not a real VIX series).
    if not price_panel.exists():
        raise FileNotFoundError(f"Missing price panel for proxy VIX: {price_panel}")
    df = pd.read_csv(price_panel, usecols=["date", "code", "close"], dtype={"code": str}, low_memory=False)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "code", "close"]).sort_values(["code", "date"])
    df["ret"] = df.groupby("code")["close"].pct_change()
    mkt_ret = df.groupby("date")["ret"].median().sort_index()
    rv20 = mkt_ret.rolling(20, min_periods=10).std() * np.sqrt(252) * 100
    out = rv20.rename("value").reset_index()
    return out.dropna(subset=["value"])


def build_usdkrw_from_summary(summary_csv: Path = Path("Summary.csv")) -> pd.DataFrame:
    if not summary_csv.exists():
        raise FileNotFoundError(f"Missing summary file: {summary_csv}")
    raw = pd.read_csv(summary_csv, low_memory=False)
    date_col = None
    usd_col = None
    for c in raw.columns:
        if "일자" in str(c):
            date_col = c
        if str(c).strip().upper() == "USD":
            usd_col = c
    if date_col is None or usd_col is None:
        raise ValueError("Summary.csv missing date/USD columns")

    df = raw[[date_col, usd_col]].copy()
    df["date"] = pd.to_datetime(df[date_col].astype(str).str.replace(".", "-", regex=False), errors="coerce")
    # value pattern like "1,444.80/2.30"
    df["value"] = (
        df[usd_col]
        .astype(str)
        .str.split("/", n=1, expand=True)[0]
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["date", "value"]).sort_values("date")
    return df[["date", "value"]]


def _try_chain(chain: List[Tuple[str, Callable[[], pd.DataFrame]]], name: str) -> Tuple[pd.DataFrame, str]:
    last_err = None
    for source_name, fn in chain:
        try:
            out = fn()
            if out.empty:
                raise ValueError("empty dataframe")
            print(f"[ok] {name}: {len(out)} rows (source={source_name})")
            return out, source_name
        except Exception as exc:
            last_err = exc
            print(f"[warn] {name} source failed: {exc}")
    raise RuntimeError(f"All sources failed for {name}: {last_err}")


def build_macro(
    start: str,
    end: str,
    output: Path,
    price_panel: Path,
    merge_existing: bool = True,
    allow_local_proxy: bool = True,
) -> pd.DataFrame:
    dates = pd.DataFrame({"date": pd.date_range(start=start, end=end, freq="D")})

    chains: Dict[str, List[Tuple[str, Callable[[], pd.DataFrame]]]] = {
        "vix": [
            ("fred_vixcls", lambda: fetch_fred_series("VIXCLS")),
            ("yahoo_^VIX", lambda: fetch_yahoo_series("^VIX")),
            ("stooq_^vix", lambda: fetch_stooq_vix()),
            ("investing_vix", lambda: fetch_investing_series("https://kr.investing.com/indices/volatility-s-p-500-historical-data")),
        ],
        "usdkrw": [
            ("fred_dexkous", lambda: fetch_fred_series("DEXKOUS")),
            ("yahoo_KRW=X", lambda: fetch_yahoo_series("KRW=X")),
            ("stooq_usdkrw", lambda: fetch_stooq_series("usdkrw")),
            ("investing_usdkrw", lambda: fetch_investing_series("https://kr.investing.com/currencies/usd-krw-historical-data")),
            ("summary_csv_usd", lambda: build_usdkrw_from_summary(Path("Summary.csv"))),
        ],
        "us10y": [
            ("fred_dgs10", lambda: fetch_fred_series("DGS10")),
            ("yahoo_^TNX", lambda: fetch_yahoo_series("^TNX", scale=10.0)),
            ("investing_us10y", lambda: fetch_investing_series("https://kr.investing.com/rates-bonds/u.s.-10-year-bond-yield-historical-data")),
        ],
        "kr10y": [
            ("fred_kr10y", lambda: fetch_fred_series("IRLTLT01KRM156N")),
            ("investing_kr10y", lambda: fetch_investing_series("https://kr.investing.com/rates-bonds/south-korea-10-year-bond-yield-historical-data")),
        ],
        "kospi": [
            ("investing_kospi", lambda: fetch_investing_series("https://kr.investing.com/indices/kospi-historical-data")),
            ("yahoo_^KS11", lambda: fetch_yahoo_series("^KS11")),
        ],
    }
    if allow_local_proxy:
        chains["kospi"].append(("local_price_panel_proxy", lambda: build_kospi_proxy_from_panel(price_panel)))
        chains["vix"].append(("local_price_panel_proxy", lambda: build_vix_proxy_from_panel(price_panel)))

    out = dates.copy()
    source_meta = {}
    for col in MACRO_COLS:
        s, src = _try_chain(chains[col], col)
        source_meta[col] = src
        s = s.rename(columns={"value": col})
        out = out.merge(s[["date", col]], on="date", how="left")
        out[f"{col}_source"] = src

    if merge_existing and output.exists():
        base = pd.read_csv(output)
        base["date"] = pd.to_datetime(base["date"], errors="coerce")
        out = base.merge(out, on="date", how="outer", suffixes=("_old", ""))
        for col in MACRO_COLS:
            old = f"{col}_old"
            if old in out.columns:
                out[col] = out[col].combine_first(out[old])
                out = out.drop(columns=[old])

    out = out.sort_values("date").reset_index(drop=True)
    for col in MACRO_COLS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
        out[col] = out[col].ffill()

    # Grounded bridge: if kr10y sparse, fill missing from us10y + observed median spread.
    overlap = out[["kr10y", "us10y"]].dropna()
    if not overlap.empty:
        spread = float((overlap["kr10y"] - overlap["us10y"]).median())
        need_fill = out["kr10y"].isna() & out["us10y"].notna()
        if int(need_fill.sum()) > 0:
            out.loc[need_fill, "kr10y"] = out.loc[need_fill, "us10y"] + spread
            out.loc[need_fill, "kr10y_source"] = "inferred_from_us10y_median_spread"

    non_null = {c: int(out[c].notna().sum()) for c in MACRO_COLS}
    print("[non-null-count]", non_null)
    if max(non_null.values()) == 0:
        raise RuntimeError("macro_daily is empty: all series failed. Check network/proxy settings.")

    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"[saved] {output}")
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch macro daily series with fallback sources.")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default="2026-12-31")
    p.add_argument("--output", default=str(data_path("macro_daily.csv")))
    p.add_argument("--price-panel", default=str(data_path("price_panel.csv")))
    p.add_argument("--no-merge-existing", action="store_true")
    p.add_argument("--no-local-proxy", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    build_macro(
        start=args.start,
        end=args.end,
        output=Path(args.output),
        price_panel=Path(args.price_panel),
        merge_existing=not args.no_merge_existing,
        allow_local_proxy=not args.no_local_proxy,
    )


if __name__ == "__main__":
    main()
