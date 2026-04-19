from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from new_strategy.paths import strategy_output_path


ROOT = strategy_output_path()
BRIDGE_DIR = ROOT / "telegram_bridge"
MARKET_STATE_PATH = ROOT / "market_schedule_state.json"
BRIDGE_STATE_PATH = BRIDGE_DIR / "telegram_bridge_state.json"
FAST_SIGNAL_PATH = ROOT / "signal_daily_fast_latest.csv"
FAST_DECISION_PATH = ROOT / "decision_report_fast_latest.csv"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fmt_ts(text: str | None) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "-"
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return raw


def _fmt_mtime(path: Path) -> str:
    if not path.exists():
        return "-"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def _csv_dates(path: Path) -> str:
    if not path.exists():
        return "-"
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as exc:
        return f"ERR:{exc}"
    for col in ("date", "signal_date", "latest_signal_date"):
        if col in df.columns:
            vals = df[col].dropna().astype(str)
            if not vals.empty:
                uniq = sorted(vals.unique().tolist())
                return ", ".join(uniq[-3:])
    return "-"


def main() -> None:
    today = datetime.now().date().isoformat()
    market_state = _load_json(MARKET_STATE_PATH)
    bridge_state = _load_json(BRIDGE_STATE_PATH)
    scheduled = bridge_state.get("scheduled_briefs", {}) if isinstance(bridge_state, dict) else {}

    print(f"[today] {today}")
    print()
    print("[market schedule]")
    print(f"last_action={market_state.get('last_action', '-')}")
    print(f"last_run_at={_fmt_ts(market_state.get('last_run_at'))}")
    print(f"last_intraday_slot={market_state.get('last_intraday_slot', '-')}")
    print(f"first_intraday_date={market_state.get('first_intraday_date', '-')}")
    print(f"first_intraday_completed_at={_fmt_ts(market_state.get('first_intraday_completed_at'))}")
    print(f"last_error_action={market_state.get('last_error_action', '-') or '-'}")
    print(f"last_error_at={_fmt_ts(market_state.get('last_error_at'))}")
    print(f"last_error_message={market_state.get('last_error_message', '-') or '-'}")
    print()
    print("[telegram bridge]")
    print(f"last_loop_at={_fmt_ts(bridge_state.get('last_loop_at'))}")
    print(f"last_outgoing_at={_fmt_ts(bridge_state.get('last_outgoing_at'))}")
    print(f"preopen_1={scheduled.get(f'{today}:preopen_1', '-')}")
    print(f"regular_open_1={scheduled.get(f'{today}:regular_open_1', '-')}")
    print(f"postclose_summary={scheduled.get(f'{today}:postclose_summary', '-')}")
    print()
    print("[fast outputs]")
    print(f"signal_daily_fast_latest.csv mtime={_fmt_mtime(FAST_SIGNAL_PATH)} dates={_csv_dates(FAST_SIGNAL_PATH)}")
    print(f"decision_report_fast_latest.csv mtime={_fmt_mtime(FAST_DECISION_PATH)} dates={_csv_dates(FAST_DECISION_PATH)}")


if __name__ == "__main__":
    main()
