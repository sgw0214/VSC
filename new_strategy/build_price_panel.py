import argparse
from pathlib import Path

import pandas as pd

from new_strategy.paths import cache_path, data_path, stock_root


RAW_COLUMNS = [
    "종목코드",
    "종목명",
    "종가",
    "시가",
    "고가",
    "저가",
    "거래량",
    "거래대금",
    "시가총액",
    "상장주식수",
    "일자",
    "시장구분",
    "업종명",
]

NUMERIC_COLS = ["종가", "시가", "고가", "저가", "거래량", "거래대금", "시가총액", "상장주식수"]


def read_year_file(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, usecols=lambda c: c in RAW_COLUMNS, engine="openpyxl")

    for col in RAW_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    df = df[RAW_COLUMNS].copy()
    df["종목코드"] = df["종목코드"].astype(str).str.zfill(6)
    df["일자"] = pd.to_datetime(df["일자"].astype(str), format="%Y%m%d", errors="coerce")

    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["is_trading_day"] = df["종가"].notna() & (df["거래량"] > 0)
    return df


def read_year_with_cache(path: Path, cache_dir: Path, use_cache: bool = True) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{path.stem}.pkl"
    if use_cache and cache_file.exists() and cache_file.stat().st_mtime >= path.stat().st_mtime:
        print(f"[cache] {cache_file}")
        return pd.read_pickle(cache_file)

    df = read_year_file(path)
    df.to_pickle(cache_file)
    print(f"[cache-write] {cache_file}")
    return df


def build_panel(
    stock_dir: Path,
    start_year: int,
    end_year: int,
    market: str = "KOSPI",
    trading_only: bool = True,
    cache_dir: Path = cache_path("yearly"),
    use_cache: bool = True,
) -> pd.DataFrame:
    frames = []
    for year in range(start_year, end_year + 1):
        path = stock_dir / f"{year}.xlsx"
        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path}")
        print(f"[read] {path}")
        frames.append(read_year_with_cache(path, cache_dir=cache_dir, use_cache=use_cache))

    df = pd.concat(frames, ignore_index=True)
    # If later years have missing market labels, backfill from 2023 by code.
    ref_2023 = df[(df["일자"].dt.year == 2023) & df["시장구분"].notna()][["종목코드", "시장구분"]].drop_duplicates(
        subset=["종목코드"]
    )
    market_map = dict(zip(ref_2023["종목코드"], ref_2023["시장구분"]))

    missing_market = df["시장구분"].isna() | (df["시장구분"].astype(str).str.strip() == "")
    missing_count = int(missing_market.sum())
    if missing_count > 0:
        df.loc[missing_market, "시장구분"] = df.loc[missing_market, "종목코드"].map(market_map)
        still_missing = int((df["시장구분"].isna() | (df["시장구분"].astype(str).str.strip() == "")).sum())
        if still_missing > 0:
            print(f"[warn] market still missing after 2023-map: {still_missing}, fallback={market}")
            df.loc[df["시장구분"].isna(), "시장구분"] = market

    normalized_market = df["시장구분"].astype(str).str.strip().str.upper()
    df = df[normalized_market == market.upper()].copy()
    if trading_only:
        df = df[df["is_trading_day"]].copy()

    df = df.rename(
        columns={
            "일자": "date",
            "종목코드": "code",
            "종목명": "name",
            "시장구분": "market",
            "업종명": "industry",
            "종가": "close",
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "거래량": "volume",
            "거래대금": "trading_value",
            "시가총액": "market_cap",
            "상장주식수": "shares_outstanding",
        }
    )
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    return df


def save_panel(df: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".parquet":
        try:
            df.to_parquet(output, index=False)
            print(f"[saved] {output}")
            return
        except Exception as exc:
            fallback = output.with_suffix(".csv")
            print(f"[warn] parquet save failed ({exc}), saving csv: {fallback}")
            df.to_csv(fallback, index=False, encoding="utf-8-sig")
            print(f"[saved] {fallback}")
            return

    df.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"[saved] {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build KOSPI price panel from yearly xlsx files.")
    parser.add_argument(
        "--stock-dir",
        default=str(stock_root()),
        help="Directory containing 2015.xlsx ... 2025.xlsx",
    )
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--market", default="KOSPI")
    parser.add_argument("--include-non-trading", action="store_true")
    parser.add_argument("--cache-dir", default=str(cache_path("yearly")))
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", default=str(data_path("price_panel.parquet")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    panel = build_panel(
        stock_dir=Path(args.stock_dir),
        start_year=args.start_year,
        end_year=args.end_year,
        market=args.market,
        trading_only=not args.include_non_trading,
        cache_dir=Path(args.cache_dir),
        use_cache=not args.no_cache,
    )
    save_panel(panel, Path(args.output))

    summary = panel.groupby("date")["code"].nunique().describe()
    print("[summary] daily universe count")
    print(summary.to_string())


if __name__ == "__main__":
    main()
