from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from new_strategy.paths import strategy_output_path


APP_DIR = strategy_output_path()
EXECUTION_SNAPSHOT_PATH = APP_DIR / "dashboard_operational_execution_snapshot.csv"
POSTCLOSE_SNAPSHOT_PATH = APP_DIR / "dashboard_operational_postclose_snapshot.csv"


def _load_dashboard_module():
    # This module is reused from both Streamlit and batch paths. When we import
    # the dashboard outside Streamlit runtime, cache warnings are just noise.
    for name in [
        "streamlit",
        "streamlit.runtime",
        "streamlit.runtime.caching",
        "streamlit.runtime.caching.cache_data_api",
        "streamlit.runtime.scriptrunner_utils.script_run_context",
    ]:
        logging.getLogger(name).setLevel(logging.ERROR)
    import new_strategy.streamlit_app as dashboard  # noqa: WPS433

    return dashboard


def build_dashboard_operational_snapshot(*, execution_window: bool) -> pd.DataFrame:
    dashboard = _load_dashboard_module()
    version_tokens = dashboard.build_version_tokens()
    payload = dashboard.build_strategy_report_payload(
        version_tokens["output"],
        version_tokens["price"],
        version_tokens["fundamental"],
        version_tokens["optimal_ma"],
        dashboard._file_stamp(dashboard.MANUAL_POSITIONS_PATH),
        execution_window,
    )
    signal_df = payload.get("signal_df", pd.DataFrame()).copy()
    if signal_df.empty:
        return signal_df
    if "code" in signal_df.columns:
        signal_df["code"] = signal_df["code"].astype(str).str.zfill(6)
    if "date" in signal_df.columns:
        signal_df["date"] = pd.to_datetime(signal_df["date"], errors="coerce")
    return signal_df


def write_dashboard_operational_snapshot(
    *,
    execution_window: bool,
    output_dir: Path | None = None,
) -> Path:
    target_dir = output_dir or APP_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    signal_df = build_dashboard_operational_snapshot(execution_window=execution_window)
    target_path = (
        target_dir / EXECUTION_SNAPSHOT_PATH.name
        if execution_window
        else target_dir / POSTCLOSE_SNAPSHOT_PATH.name
    )
    signal_df.to_csv(target_path, index=False, encoding="utf-8-sig")
    return target_path
