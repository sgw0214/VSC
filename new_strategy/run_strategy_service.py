from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from new_strategy.paths import output_path


def _market_hours(now: datetime, open_hhmm: str, close_hhmm: str) -> bool:
    open_h, open_m = map(int, open_hhmm.split(":"))
    close_h, close_m = map(int, close_hhmm.split(":"))
    if now.weekday() >= 5:
        return False
    current = now.hour * 60 + now.minute
    return open_h * 60 + open_m <= current <= close_h * 60 + close_m


def _run_pipeline(
    send_alerts: bool,
    fast_alerts: bool,
    refresh_data: bool,
    refresh_macro: bool,
    refresh_gold: bool,
    refresh_db: bool,
    live_quotes: str,
) -> None:
    cmd = [sys.executable, "-m", "new_strategy.run_signal_pipeline"]
    if send_alerts:
        cmd.append("--send-alerts")
    if fast_alerts:
        cmd.append("--fast-alerts")
    if refresh_data:
        cmd.append("--refresh-data")
    if refresh_macro:
        cmd.append("--refresh-macro")
    if refresh_gold:
        cmd.append("--refresh-gold")
    if refresh_db:
        cmd.append("--refresh-db")
    if live_quotes:
        cmd.extend(["--live-quotes", live_quotes])
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run strategy pipeline once or as a lightweight polling service.")
    p.add_argument("--mode", choices=["once", "loop"], default="once")
    p.add_argument("--interval-seconds", type=int, default=300)
    p.add_argument("--open", default="08:55")
    p.add_argument("--close", default="15:40")
    p.add_argument("--send-alerts", action="store_true")
    p.add_argument("--fast-alerts", action="store_true")
    p.add_argument("--refresh-data", action="store_true")
    p.add_argument("--refresh-macro", action="store_true")
    p.add_argument("--refresh-gold", action="store_true")
    p.add_argument("--refresh-db", action="store_true")
    p.add_argument("--live-quotes", default="")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    state_path = output_path("strategy_v1", "service_state.txt")
    state_path.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "once":
        _run_pipeline(
            send_alerts=args.send_alerts,
            fast_alerts=args.fast_alerts,
            refresh_data=args.refresh_data,
            refresh_macro=args.refresh_macro,
            refresh_gold=args.refresh_gold,
            refresh_db=args.refresh_db,
            live_quotes=args.live_quotes,
        )
        state_path.write_text(f"last_run={datetime.now().isoformat()}", encoding="utf-8")
        return

    while True:
        now = datetime.now()
        if _market_hours(now, args.open, args.close):
            _run_pipeline(
                send_alerts=args.send_alerts,
                fast_alerts=args.fast_alerts,
                refresh_data=args.refresh_data,
                refresh_macro=args.refresh_macro,
                refresh_gold=args.refresh_gold,
                refresh_db=args.refresh_db,
                live_quotes=args.live_quotes,
            )
            state_path.write_text(f"last_run={now.isoformat()}", encoding="utf-8")
        time.sleep(max(60, args.interval_seconds))


if __name__ == "__main__":
    main()
