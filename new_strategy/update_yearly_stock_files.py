import argparse
from pathlib import Path

import pandas as pd

from new_strategy.paths import stock_root


REQUIRED_COLS = [
    "종목코드",
    "종목명",
    "종가",
    "대비",
    "등락률",
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


def _load_market_industry_map(stock_dir: Path, years):
    market_map = {}
    industry_map = {}

    for year in years:
        path = stock_dir / f"{year}.xlsx"
        if not path.exists():
            continue
        df = pd.read_excel(path, engine="openpyxl")
        if "종목코드" not in df.columns:
            continue
        df["종목코드"] = df["종목코드"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
        if "시장구분" in df.columns:
            tmp = df[["종목코드", "시장구분"]].dropna().drop_duplicates("종목코드", keep="last")
            market_map.update(dict(zip(tmp["종목코드"], tmp["시장구분"])))
        if "업종명" in df.columns:
            tmp = df[["종목코드", "업종명"]].dropna().drop_duplicates("종목코드", keep="last")
            industry_map.update(dict(zip(tmp["종목코드"], tmp["업종명"])))

    return market_map, industry_map


def _load_basic_files(paths, market_map, industry_map) -> pd.DataFrame:
    frames = []
    for path in sorted(paths):
        df = pd.read_excel(path, engine="openpyxl")
        for col in REQUIRED_COLS:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[REQUIRED_COLS].copy()
        df["종목코드"] = df["종목코드"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
        df["시장구분"] = df["시장구분"].fillna(df["종목코드"].map(market_map))
        df["업종명"] = df["업종명"].fillna(df["종목코드"].map(industry_map))
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=REQUIRED_COLS)
    return pd.concat(frames, ignore_index=True)


def _normalize_year_file(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, engine="openpyxl")
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[REQUIRED_COLS].copy()
    df["종목코드"] = df["종목코드"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
    return df


def update_yearly_files(stock_dir: Path) -> None:
    market_map, industry_map = _load_market_industry_map(stock_dir, [2023, 2024, 2025])

    late_2025_files = [
        p for p in stock_dir.glob("basic_202512*.xlsx") if int(p.stem.split("_")[1]) >= 20251222
    ]
    if late_2025_files:
        add_2025 = _load_basic_files(late_2025_files, market_map, industry_map)
        path_2025 = stock_dir / "2025.xlsx"
        base_2025 = _normalize_year_file(path_2025)
        merged_2025 = (
            pd.concat([base_2025, add_2025], ignore_index=True)
            .drop_duplicates(subset=["종목코드", "일자"], keep="last")
            .sort_values(["일자", "종목코드"])
            .reset_index(drop=True)
        )
        merged_2025.to_excel(path_2025, index=False)
        print(f"[saved] {path_2025} rows={len(merged_2025):,}")
    else:
        print("[skip] no late 2025 basic files")

    files_2026 = list(stock_dir.glob("basic_2026*.xlsx"))
    if files_2026:
        year_2026 = (
            _load_basic_files(files_2026, market_map, industry_map)
            .drop_duplicates(subset=["종목코드", "일자"], keep="last")
            .sort_values(["일자", "종목코드"])
            .reset_index(drop=True)
        )
        path_2026 = stock_dir / "2026.xlsx"
        year_2026.to_excel(path_2026, index=False)
        print(
            f"[saved] {path_2026} rows={len(year_2026):,} "
            f"date={year_2026['일자'].min()}~{year_2026['일자'].max()}"
        )
    else:
        print("[skip] no 2026 basic files")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Update yearly stock xlsx files from basic_YYYYMMDD.xlsx files.")
    p.add_argument("--stock-dir", default=str(stock_root()))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    update_yearly_files(Path(args.stock_dir))


if __name__ == "__main__":
    main()
