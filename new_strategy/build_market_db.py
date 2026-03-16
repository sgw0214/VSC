import argparse
import sqlite3
from pathlib import Path

import pandas as pd

from new_strategy.paths import cache_path, data_path, stock_root

from new_strategy.build_price_panel import build_panel


FUND_COL_MAP = {
    "종목코드": "code",
    "법인코드": "corp_code",
    "법인명": "corp_name",
    "사업연도": "bsns_year",
    "보고서코드": "reprt_code",
    "접수번호": "rcept_no",
    "공시일": "rcept_dt",
    "기간": "period",
    "분기매출액": "revenue",
    "분기영업이익": "op_income",
    "분기당기순이익": "net_income",
    "자산총계": "total_assets",
    "부채총계": "total_liab",
    "자본총계": "total_equity",
    "분기영업이익률": "op_margin",
    "분기ROE(단순)": "roe_simple",
}


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except sqlite3.OperationalError:
        # Some environments (network/virtualized FS) reject WAL and raise disk I/O errors.
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("PRAGMA synchronous=FULL;")
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS dim_symbol (
            code TEXT PRIMARY KEY,
            name TEXT,
            market TEXT,
            industry TEXT,
            first_seen TEXT,
            last_seen TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS fact_price_daily (
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            trading_value REAL,
            market_cap REAL,
            shares_outstanding REAL,
            source TEXT,
            loaded_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (date, code),
            FOREIGN KEY (code) REFERENCES dim_symbol(code)
        );

        CREATE TABLE IF NOT EXISTS fact_macro_daily (
            date TEXT PRIMARY KEY,
            kospi REAL,
            vix REAL,
            usdkrw REAL,
            us10y REAL,
            kr10y REAL,
            gold_kr_close REAL,
            gold_kr_ret REAL,
            gold_kr_volume REAL,
            gold_kr_trading_value REAL,
            kospi_source TEXT,
            vix_source TEXT,
            usdkrw_source TEXT,
            us10y_source TEXT,
            kr10y_source TEXT,
            loaded_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS fact_fundamental_quarterly (
            code TEXT NOT NULL,
            corp_code TEXT,
            corp_name TEXT,
            bsns_year INTEGER NOT NULL,
            reprt_code TEXT NOT NULL,
            rcept_no TEXT,
            rcept_dt TEXT,
            period TEXT,
            revenue REAL,
            op_income REAL,
            net_income REAL,
            total_assets REAL,
            total_liab REAL,
            total_equity REAL,
            op_margin REAL,
            roe_simple REAL,
            source TEXT,
            loaded_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (code, bsns_year, reprt_code),
            FOREIGN KEY (code) REFERENCES dim_symbol(code)
        );

        CREATE INDEX IF NOT EXISTS idx_price_code_date ON fact_price_daily(code, date);
        CREATE INDEX IF NOT EXISTS idx_fund_code_year ON fact_fundamental_quarterly(code, bsns_year);
        """
    )
    conn.commit()


def load_price(conn: sqlite3.Connection, price_df: pd.DataFrame, source: str) -> None:
    base = price_df.copy()
    base["code"] = base["code"].astype(str).str.zfill(6)
    base["date"] = pd.to_datetime(base["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    symbols = (
        base.sort_values(["code", "date"])
        .groupby("code", as_index=False)
        .agg(
            name=("name", "last"),
            market=("market", "last"),
            industry=("industry", "last"),
            first_seen=("date", "first"),
            last_seen=("date", "last"),
        )
    )

    symbols.to_sql("tmp_dim_symbol", conn, if_exists="replace", index=False)
    conn.executescript(
        """
        INSERT OR REPLACE INTO dim_symbol(code, name, market, industry, first_seen, last_seen, updated_at)
        SELECT code, name, market, industry, first_seen, last_seen, datetime('now')
        FROM tmp_dim_symbol;
        DROP TABLE tmp_dim_symbol;
        """
    )

    price_cols = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trading_value",
        "market_cap",
        "shares_outstanding",
    ]
    price = base[price_cols].copy()
    price["source"] = source
    price.to_sql("tmp_price", conn, if_exists="replace", index=False)
    conn.executescript(
        """
        INSERT OR REPLACE INTO fact_price_daily(
            date, code, open, high, low, close, volume, trading_value, market_cap, shares_outstanding, source, loaded_at
        )
        SELECT date, code, open, high, low, close, volume, trading_value, market_cap, shares_outstanding, source, datetime('now')
        FROM tmp_price;
        DROP TABLE tmp_price;
        """
    )
    conn.commit()


def load_macro(conn: sqlite3.Connection, macro_csv: Path, source: str) -> None:
    if not macro_csv.exists():
        print(f"[skip] macro file not found: {macro_csv}")
        return

    macro = pd.read_csv(macro_csv)
    macro["date"] = pd.to_datetime(macro["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    cols = [
        "date",
        "kospi",
        "vix",
        "usdkrw",
        "us10y",
        "kr10y",
        "gold_kr_close",
        "gold_kr_ret",
        "gold_kr_volume",
        "gold_kr_trading_value",
        "kospi_source",
        "vix_source",
        "usdkrw_source",
        "us10y_source",
        "kr10y_source",
    ]
    keep = [c for c in cols if c in macro.columns]
    macro = macro[keep].copy()
    for c in ["kospi_source", "vix_source", "usdkrw_source", "us10y_source", "kr10y_source"]:
        if c not in macro.columns:
            macro[c] = source

    macro.to_sql("tmp_macro", conn, if_exists="replace", index=False)
    conn.executescript(
        """
        INSERT OR REPLACE INTO fact_macro_daily(
            date, kospi, vix, usdkrw, us10y, kr10y,
            gold_kr_close, gold_kr_ret, gold_kr_volume, gold_kr_trading_value,
            kospi_source, vix_source, usdkrw_source, us10y_source, kr10y_source, loaded_at
        )
        SELECT
            date, kospi, vix, usdkrw, us10y, kr10y,
            gold_kr_close, gold_kr_ret, gold_kr_volume, gold_kr_trading_value,
            kospi_source, vix_source, usdkrw_source, us10y_source, kr10y_source, datetime('now')
        FROM tmp_macro;
        DROP TABLE tmp_macro;
        """
    )
    conn.commit()


def load_fundamental(conn: sqlite3.Connection, fundamental_csv: Path, source: str) -> None:
    if not fundamental_csv.exists():
        print(f"[skip] fundamental file not found: {fundamental_csv}")
        return

    f = pd.read_csv(fundamental_csv)
    if f.empty:
        print(f"[skip] fundamental file is empty: {fundamental_csv}")
        return

    f = f.rename(columns={k: v for k, v in FUND_COL_MAP.items() if k in f.columns})

    f["code"] = f["code"].astype(str).str.zfill(6)
    needed = [
        "code",
        "corp_code",
        "corp_name",
        "bsns_year",
        "reprt_code",
        "rcept_no",
        "rcept_dt",
        "period",
        "revenue",
        "op_income",
        "net_income",
        "total_assets",
        "total_liab",
        "total_equity",
        "op_margin",
        "roe_simple",
    ]
    keep = [c for c in needed if c in f.columns]
    f = f[keep].copy()
    for c in needed:
        if c not in f.columns:
            f[c] = None
    f["source"] = source

    f.to_sql("tmp_fund", conn, if_exists="replace", index=False)
    conn.executescript(
        """
        INSERT OR REPLACE INTO fact_fundamental_quarterly(
            code, corp_code, corp_name, bsns_year, reprt_code, rcept_no, rcept_dt, period,
            revenue, op_income, net_income, total_assets, total_liab, total_equity, op_margin, roe_simple,
            source, loaded_at
        )
        SELECT
            code, corp_code, corp_name, bsns_year, reprt_code, rcept_no, rcept_dt, period,
            revenue, op_income, net_income, total_assets, total_liab, total_equity, op_margin, roe_simple,
            source, datetime('now')
        FROM tmp_fund;
        DROP TABLE tmp_fund;
        """
    )
    conn.commit()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build integrated SQLite DB for price, macro, and fundamentals.")
    p.add_argument("--db-path", default=str(data_path("market_data.db")))
    p.add_argument("--stock-dir", default=str(stock_root()))
    p.add_argument("--start-year", type=int, default=2015)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--market", default="KOSPI")
    p.add_argument("--cache-dir", default=str(cache_path("yearly")))
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--macro-csv", default=str(data_path("macro_daily.csv")))
    p.add_argument("--fundamental-csv", default=str(data_path("fundamental_quarterly_multi.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    conn = _connect(Path(args.db_path))
    try:
        create_tables(conn)
        price = build_panel(
            stock_dir=Path(args.stock_dir),
            start_year=args.start_year,
            end_year=args.end_year,
            market=args.market,
            trading_only=True,
            cache_dir=Path(args.cache_dir),
            use_cache=not args.no_cache,
        )
        load_price(conn, price, source=f"xlsx:{args.stock_dir}/{args.start_year}..{args.end_year}")
        print(f"[ok] price rows={len(price):,}")

        load_macro(conn, Path(args.macro_csv), source=f"csv:{args.macro_csv}")
        load_fundamental(conn, Path(args.fundamental_csv), source=f"csv:{args.fundamental_csv}")

        c = conn.cursor()
        price_cnt = c.execute("SELECT COUNT(*) FROM fact_price_daily").fetchone()[0]
        macro_cnt = c.execute("SELECT COUNT(*) FROM fact_macro_daily").fetchone()[0]
        fund_cnt = c.execute("SELECT COUNT(*) FROM fact_fundamental_quarterly").fetchone()[0]
        sym_cnt = c.execute("SELECT COUNT(*) FROM dim_symbol").fetchone()[0]
        print(
            f"[saved] {args.db_path} symbols={sym_cnt:,} price={price_cnt:,} macro={macro_cnt:,} fundamental={fund_cnt:,}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
