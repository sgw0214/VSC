from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from new_strategy.earnings_signal_engine import EarningsStrategyConfig
from new_strategy.paths import strategy_output_path
import new_strategy.run_signal_pipeline as signal_pipeline
from new_strategy.telegram_bridge_service import (
    _is_regular_open_slot_ready,
    _should_send_preopen_brief,
    _should_send_regular_open_brief,
    _should_skip_preopen_brief,
    _should_skip_regular_open_brief,
)
from new_strategy.telegram_bridge_tools import _numeric_series_or_na


def _assert(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)


def _build_min_signal_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-04-01"),
                "code": "999999",
                "name": "회귀테스트",
                "signal": "BUY",
                "strategy_id": "earnings_pti_v2",
                "conviction_score": 0.8,
                "risk_flag": "",
                "reason_1": "테스트",
                "reason_2": "",
                "reason_3": "",
                "intraday_action_guide": "",
                "next_day_action_guide": "",
                "alert_current_price": 177000.0,
            }
        ]
    )


def main() -> int:
    # Fixed-time window contract: preopen can never send after 09:00.
    now = datetime(2026, 3, 31, 20, 17, 0)
    first_done = datetime(2026, 3, 31, 20, 17, 0)
    _assert(
        "preopen_never_after_deadline",
        not _should_send_preopen_brief(
            now,
            first_intraday_date="2026-03-31",
            first_done_at=first_done,
            scheduled={},
        ),
    )
    _assert(
        "preopen_skips_after_deadline",
        _should_skip_preopen_brief(now, scheduled={}),
    )

    # Premarket should send only inside the time window and only after first intraday completion.
    now = datetime(2026, 3, 31, 8, 20, 0)
    first_done = datetime(2026, 3, 31, 8, 17, 0)
    _assert(
        "preopen_send_inside_window",
        _should_send_preopen_brief(
            now,
            first_intraday_date="2026-03-31",
            first_done_at=first_done,
            scheduled={},
        ),
    )

    # Regular-open should depend on second slot readiness but never send after deadline.
    now = datetime(2026, 3, 31, 9, 25, 0)
    slot = datetime(2026, 3, 31, 9, 10, 0)
    _assert("regular_slot_ready", _is_regular_open_slot_ready(now, slot))
    _assert(
        "regular_send_inside_window",
        _should_send_regular_open_brief(now, scheduled={}, last_intraday_slot=slot),
    )

    now = datetime(2026, 3, 31, 20, 17, 0)
    slot = datetime(2026, 3, 31, 20, 10, 0)
    _assert(
        "regular_never_after_deadline",
        not _should_send_regular_open_brief(now, scheduled={}, last_intraday_slot=slot),
    )
    _assert(
        "regular_skips_after_deadline",
        _should_skip_regular_open_brief(now, scheduled={}),
    )

    # Fast trigger renderer contract: missing columns must still yield Series, not scalar NaN.
    frame = pd.DataFrame({"code": ["005930"], "current_price": [70000]})
    series = _numeric_series_or_na(frame, "alert_current_price")
    _assert("missing_column_returns_series", isinstance(series, pd.Series))
    _assert("missing_column_series_length", len(series) == 1)
    _assert("existing_column_returns_series", isinstance(_numeric_series_or_na(frame, "current_price"), pd.Series))

    # Trigger contract: before 09:00, TRIGGER events must never be generated.
    signal_df = _build_min_signal_df()
    decision_df = pd.DataFrame()
    cfg = EarningsStrategyConfig()
    out_dir: Path = strategy_output_path()
    real_datetime = signal_pipeline.datetime

    class _PreOpenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return datetime(2026, 4, 1, 8, 20, 0)

    class _OpenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return datetime(2026, 4, 1, 9, 20, 0)

    try:
        signal_pipeline.datetime = _PreOpenDateTime
        pre_events = signal_pipeline._build_alert_events(signal_df, decision_df, cfg, out_dir)
        _assert(
            "trigger_blocked_before_0900",
            sum(1 for event in pre_events if str(event.event_type).upper() == "TRIGGER") == 0,
        )

        signal_pipeline.datetime = _OpenDateTime
        open_events = signal_pipeline._build_alert_events(signal_df, decision_df, cfg, out_dir)
        _assert(
            "trigger_allowed_after_0900",
            sum(1 for event in open_events if str(event.event_type).upper() == "TRIGGER") >= 1,
        )
    finally:
        signal_pipeline.datetime = real_datetime

    print("PASSED market-open regression checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
