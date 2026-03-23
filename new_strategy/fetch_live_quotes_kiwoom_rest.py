from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import re

from new_strategy.kiwoom_rest_client import DEFAULT_KIWOOM_API_ROOT, fetch_current_quotes, save_live_quotes
from new_strategy.paths import data_path, strategy_output_path


PORTFOLIO_PATH = strategy_output_path("telegram_bridge", "manual_portfolio_positions.csv")
SIGNAL_LATEST_PATH = strategy_output_path("signal_daily_fast_latest.csv")
VALID_CODE_RE = re.compile(r"^[0-9A-Za-z]{6}$")


def _load_codes_from_portfolio() -> list[str]:
    if not PORTFOLIO_PATH.exists():
        return []
    df = pd.read_csv(PORTFOLIO_PATH, dtype={"code": str}, low_memory=False)
    if "code" not in df.columns:
        return []
    return sorted(df["code"].dropna().astype(str).str.zfill(6).unique().tolist())


def _load_codes_from_signals(signals: Iterable[str], limit: int) -> list[str]:
    if not SIGNAL_LATEST_PATH.exists():
        return []
    df = pd.read_csv(SIGNAL_LATEST_PATH, dtype={"code": str}, low_memory=False)
    if df.empty or "signal" not in df.columns:
        return []
    view = df[df["signal"].astype(str).isin(list(signals))].copy()
    sort_cols = [c for c in ["conviction_score", "signal", "code"] if c in view.columns]
    if sort_cols:
        ascending = [False if c == "conviction_score" else True for c in sort_cols]
        view = view.sort_values(sort_cols, ascending=ascending)
    return view["code"].dropna().astype(str).str.zfill(6).head(limit).tolist()


def resolve_codes(explicit_codes: str, include_portfolio: bool, include_signal_watchlist: bool, signal_limit: int) -> list[str]:
    codes: list[str] = []
    if explicit_codes:
        codes.extend([x.strip() for x in explicit_codes.split(",") if x.strip()])
    if include_portfolio:
        codes.extend(_load_codes_from_portfolio())
    if include_signal_watchlist:
        codes.extend(_load_codes_from_signals(["BUY", "HOLD", "WATCH"], signal_limit))
    deduped = []
    seen = set()
    for code in codes:
        code = str(code).replace(".0", "")
        code = code.zfill(6) if code.isdigit() else code
        if not VALID_CODE_RE.fullmatch(code) or code.lower() == "000nan":
            continue
        if code and code not in seen:
            seen.add(code)
            deduped.append(code)
    return deduped


def run_once(
    codes: list[str],
    *,
    api_root: Path,
    output_path_value: Path,
    use_mock: bool = False,
    per_request_sleep_seconds: float = 0.22,
) -> Path:
    if not codes:
        raise ValueError("No codes selected for Kiwoom live quote fetch")
    df = fetch_current_quotes(
        codes,
        use_mock=use_mock,
        api_root=api_root,
        per_request_sleep_seconds=per_request_sleep_seconds,
    )
    return save_live_quotes(df, output_path_value)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fetch live quotes from Kiwoom REST API into live_quotes.csv")
    p.add_argument("--codes", default="", help="Comma-separated stock codes. Example: 005930,000660")
    p.add_argument("--api-root", default=str(DEFAULT_KIWOOM_API_ROOT), help="Directory containing Kiwoom appkey/secretkey files")
    p.add_argument("--output", default=str(data_path("live_quotes.csv")), help="Output CSV path for live quotes")
    p.add_argument("--signal-limit", type=int, default=30, help="Max number of codes loaded from latest strategy signals")
    p.add_argument("--no-portfolio", action="store_true", help="Do not include manual portfolio codes")
    p.add_argument("--no-signal-watchlist", action="store_true", help="Do not include BUY/HOLD/WATCH codes from latest signals")
    p.add_argument("--use-mock", action="store_true", help="Use Kiwoom mock domain")
    p.add_argument("--interval-seconds", type=int, default=30, help="Loop interval seconds")
    p.add_argument("--per-request-sleep-seconds", type=float, default=0.22, help="Sleep between per-code API requests")
    p.add_argument("--once", action="store_true", help="Run once and exit")
    return p


def main() -> None:
    args = build_parser().parse_args()
    api_root = Path(args.api_root)
    output_path_value = Path(args.output)
    while True:
        try:
            codes = resolve_codes(
                explicit_codes=args.codes,
                include_portfolio=not args.no_portfolio,
                include_signal_watchlist=not args.no_signal_watchlist,
                signal_limit=args.signal_limit,
            )
            output = run_once(
                codes,
                api_root=api_root,
                output_path_value=output_path_value,
                use_mock=args.use_mock,
                per_request_sleep_seconds=args.per_request_sleep_seconds,
            )
            print(f"[saved] {output} | codes={len(codes)}")
        except Exception as exc:
            print(f"[warn] live quote fetch failed: {exc}")
        if args.once:
            break
        time.sleep(max(args.interval_seconds, 5))


if __name__ == "__main__":
    main()
