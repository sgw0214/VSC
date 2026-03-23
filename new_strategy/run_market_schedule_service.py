from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime

from new_strategy.paths import data_path, strategy_output_path


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


def _run_intraday_full_refresh_fast_alert() -> None:
    # Use a non-existent live quote path so fast mode uses the freshly rebuilt
    # full-universe price panel instead of an older subset live_quotes overlay.
    cmd = [
        sys.executable,
        "-m",
        "new_strategy.run_signal_pipeline",
        "--refresh-data",
        "--prefer-kiwoom-eod",
        "--send-alerts",
        "--fast-alerts",
        "--live-quotes",
        str(data_path("_disabled_live_quotes.csv")),
    ]
    _run_command(cmd)


def _run_eod_refresh_summary() -> None:
    cmd = [
        sys.executable,
        "-m",
        "new_strategy.run_signal_pipeline",
        "--refresh-data",
        "--prefer-kiwoom-eod",
        "--send-alerts",
    ]
    _run_command(cmd)


def _run_krx_reconcile() -> None:
    cmd = [
        sys.executable,
        "-m",
        "new_strategy.run_signal_pipeline",
        "--refresh-data",
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
    last_error_action: str = ""
    last_error_at: str = ""
    last_error_message: str = ""


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
    p = argparse.ArgumentParser(description="Market schedule service for 30-minute full-universe Kiwoom refresh and fast alerts.")
    p.add_argument("--poll-seconds", type=int, default=60)
    p.add_argument("--intraday-open", default="08:10")
    p.add_argument("--intraday-close", default="20:00")
    p.add_argument("--intraday-interval-minutes", type=int, default=30)
    # Deprecated compatibility arguments: kept so existing launch scripts do not break.
    p.add_argument("--preclose-time", default="15:20")
    p.add_argument("--eod-time", default="20:10")
    p.add_argument("--krx-reconcile-time", default="07:00")
    p.add_argument("--live-quotes", default=str(data_path("live_quotes.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    state_path = strategy_output_path("market_schedule_state.json")
    state = _load_state(state_path)
    intraday_open = _parse_hhmm(args.intraday_open)
    intraday_close = _parse_hhmm(args.intraday_close)
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

        if current >= krx_reconcile_time and state.last_krx_reconcile_date != today:
            action = "krx_reconcile"
            marker = today
        elif current >= eod_time and state.last_eod_date != today:
            action = "eod_refresh_summary"
            marker = today
        else:
            slot_key = _intraday_slot_key(now, intraday_open, intraday_close, args.intraday_interval_minutes)
            if slot_key and state.last_intraday_slot != slot_key:
                action = "intraday_full_refresh_fast_alert"
                marker = slot_key

        if action is None:
            time.sleep(max(30, args.poll_seconds))
            continue

        try:
            if action == "intraday_full_refresh_fast_alert":
                _run_intraday_full_refresh_fast_alert()
                state.last_intraday_slot = marker or ""
            elif action == "krx_reconcile":
                _run_krx_reconcile()
                state.last_krx_reconcile_date = marker or ""
            elif action == "eod_refresh_summary":
                _run_eod_refresh_summary()
                state.last_eod_date = marker or ""

            state.last_action = action
            state.last_run_at = datetime.now().isoformat()
            state.last_error_action = ""
            state.last_error_at = ""
            state.last_error_message = ""
        except Exception as exc:
            state.last_error_action = action
            state.last_error_at = datetime.now().isoformat()
            state.last_error_message = f"{type(exc).__name__}: {exc}"
            print(
                f"[scheduler-error] action={action} marker={marker or '-'} "
                f"error={type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            traceback.print_exc()
        _save_state(state_path, state)
        time.sleep(max(30, args.poll_seconds))


if __name__ == "__main__":
    main()
