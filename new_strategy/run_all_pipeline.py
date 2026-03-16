import argparse
import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List

from new_strategy.paths import data_path, stock_root


def _run(cmd: List[str]) -> None:
    print(f"[run] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run integrated market data pipeline end-to-end.")
    p.add_argument("--stock-dir", default=str(stock_root()))
    p.add_argument("--start-year", type=int, default=2015)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--price-output", default=str(data_path("price_panel.csv")))
    p.add_argument("--macro-output", default=str(data_path("macro_daily.csv")))
    p.add_argument("--macro-regime-output", default=str(data_path("macro_regime_v3_rec.csv")))
    p.add_argument("--fund-output", default=str(data_path("fundamental_quarterly_multi.csv")))
    p.add_argument("--db-path", default=str(data_path("market_data.db")))
    p.add_argument("--fetch-macro", action="store_true", help="Fetch macro from online sources before regime build.")
    p.add_argument("--fetch-fundamental", action="store_true", help="Fetch DART fundamentals before DB build.")
    p.add_argument("--dart-api-key", default="", help="DART API key (or set DART_API_KEY env var).")
    p.add_argument("--max-fund-codes", type=int, default=0, help="Limit number of codes for test runs.")
    p.add_argument("--no-cache", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    py = sys.executable

    # 1) Price panel
    cmd_price = [
        py,
        "new_strategy/build_price_panel.py",
        "--stock-dir",
        args.stock_dir,
        "--start-year",
        str(args.start_year),
        "--end-year",
        str(args.end_year),
        "--output",
        args.price_output,
    ]
    if args.no_cache:
        cmd_price.append("--no-cache")
    _run(cmd_price)

    # 2) Macro (optional fetch + regime)
    if args.fetch_macro:
        _run(
            [
                py,
                "new_strategy/fetch_macro_investing.py",
                "--start",
                f"{args.start_year}-01-01",
                "--end",
                f"{args.end_year + 1}-12-31",
                "--output",
                args.macro_output,
                "--merge-existing",
            ]
        )

    _run(
        [
            py,
            "new_strategy/macro_pipeline.py",
            "--input",
            args.macro_output,
            "--output",
            args.macro_regime_output,
        ]
    )

    # 3) Fundamentals (optional fetch)
    if args.fetch_fundamental:
        key = (args.dart_api_key or os.getenv("DART_API_KEY", "")).strip()
        if not key:
            raise RuntimeError("Set --dart-api-key or DART_API_KEY to use --fetch-fundamental.")
        cmd_f = [
            py,
            "new_strategy/fetch_fundamental_dart.py",
            "--api-key",
            key,
            "--price-panel",
            args.price_output,
            "--start-year",
            str(args.start_year),
            "--end-year",
            str(args.end_year),
            "--output",
            args.fund_output,
        ]
        if args.max_fund_codes > 0:
            cmd_f.extend(["--max-codes", str(args.max_fund_codes)])
        _run(cmd_f)

    # 4) Build DB
    _run(
        [
            py,
            "new_strategy/build_market_db.py",
            "--stock-dir",
            args.stock_dir,
            "--start-year",
            str(args.start_year),
            "--end-year",
            str(args.end_year),
            "--macro-csv",
            args.macro_output,
            "--fundamental-csv",
            args.fund_output,
            "--db-path",
            args.db_path,
        ]
    )

    print("[done] pipeline completed")


if __name__ == "__main__":
    main()
