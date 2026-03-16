from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from new_strategy.paths import data_path, output_path


def _parse_hhmm(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _weekday_now() -> datetime | None:
    now = datetime.now()
    if now.weekday() >= 5:
        return None
    return now


def _minutes_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def _run_command(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _run_live_quote_fetch() -> None:
    _run_command([sys.executable, "-m", "new_strategy.fetch_live_quotes_kiwoom_rest", "--once"])


def _run_fast_alert(live_quotes: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "new_strategy.run_signal_pipeline",
        "--fast-alerts",
        "--send-alerts",
        "--live-quotes",
        str(live_quotes),
    ]
    _run_command(cmd)


def _run_eod_refresh() -> None:
    cmd = [
        sys.executable,
        "-m",
        "new_strategy.run_signal_pipeline",
        "--refresh-data",
        "--refresh-macro",
        "--refresh-gold",
        "--prefer-kiwoom-eod",
        "--send-alerts",
        "--fast-alerts",
    ]
    _run_command(cmd)


def _run_krx_reconcile() -> None:
    cmd = [
        sys.executable,
        "-m",
        "new_strategy.run_signal_pipeline",
        "--refresh-data",
        "--prefer-kiwoom-eod",
        "--fast-alerts",
    ]
    _run_command(cmd)


@dataclass
class SchedulerState:
    last_intraday_slot: str = ""
    last_preclose_date: str = ""
    last_eod_date: str = ""
    last_krx_reconcile_date: str = ""
    last_action: str = ""
    last_run_at: str = ""


def _load_state(path: Path) -> SchedulerState:
    if not path.exists():
        return SchedulerState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return SchedulerState(**payload)
    except Exception:
        return SchedulerState()


def _save_state(path: Path, state: SchedulerState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")


def _intraday_slot_key(now: datetime, open_minutes: int, close_minutes: int, interval_minutes: int) -> str | None:
    current = _minutes_of_day(now)
    if current < open_minutes or current > close_minutes:
        return None
    offset = current - open_minutes
    slot_start = open_minutes + (offset // interval_minutes) * interval_minutes
    return f"{now:%Y-%m-%d} {slot_start // 60:02d}:{slot_start % 60:02d}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Market schedule service for intraday/live risk check and end-of-day refresh.")
    p.add_argument("--poll-seconds", type=int, default=60)
    p.add_argument("--intraday-open", default="08:00")
    p.add_argument("--intraday-close", default="20:00")
    p.add_argument("--intraday-interval-minutes", type=int, default=30)
    p.add_argument("--preclose-time", default="15:20")
    p.add_argument("--eod-time", default="16:10")
    p.add_argument("--krx-reconcile-time", default="21:00")
    p.add_argument("--live-quotes", default=str(data_path("live_quotes.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    state_path = output_path("strategy_v1", "market_schedule_state.json")
    state = _load_state(state_path)
    live_quotes = Path(args.live_quotes)
    intraday_open = _parse_hhmm(args.intraday_open)
    intraday_close = _parse_hhmm(args.intraday_close)
    preclose_time = _parse_hhmm(args.preclose_time)
    eod_time = _parse_hhmm(args.eod_time)
    krx_reconcile_time = _parse_hhmm(args.krx_reconcile_time)

    while True:
        now = _weekday_now()
        if now is None:
            time.sleep(max(30, args.poll_seconds))
            continue

        today = now.strftime("%Y-%m-%d")
        current = _minutes_of_day(now)
        action = None
        marker = None

        if current >= eod_time and state.last_eod_date != today:
            action = "eod_refresh"
            marker = today
        elif current >= krx_reconcile_time and state.last_krx_reconcile_date != today and state.last_eod_date == today:
            action = "krx_reconcile"
            marker = today
        elif current >= preclose_time and state.last_preclose_date != today:
            action = "preclose_risk"
            marker = today
        else:
            slot_key = _intraday_slot_key(now, intraday_open, intraday_close, args.intraday_interval_minutes)
            if slot_key and state.last_intraday_slot != slot_key:
                action = "intraday_fast_alert"
                marker = slot_key

        if action is None:
            time.sleep(max(30, args.poll_seconds))
            continue

        if action in {"intraday_fast_alert", "preclose_risk"}:
            _run_live_quote_fetch()
            _run_fast_alert(live_quotes)
            if action == "intraday_fast_alert":
                state.last_intraday_slot = marker or ""
            else:
                state.last_preclose_date = marker or ""
        elif action == "eod_refresh":
            _run_eod_refresh()
            state.last_eod_date = marker or ""
        elif action == "krx_reconcile":
            _run_krx_reconcile()
            state.last_krx_reconcile_date = marker or ""

        state.last_action = action
        state.last_run_at = datetime.now().isoformat()
        _save_state(state_path, state)
        time.sleep(max(30, args.poll_seconds))


if __name__ == "__main__":
    main()
