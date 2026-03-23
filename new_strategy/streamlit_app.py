from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, time, timedelta, timezone
from dataclasses import asdict
from pathlib import Path
from typing import Any

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

APP_FILE = Path(__file__).resolve()
PROJECT_ROOT = APP_FILE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from new_strategy.earnings_signal_engine import EarningsStrategyConfig
from new_strategy.optimal_ma_overlay import (
    MA_SELECTION_PATH as OPTIMAL_MA_SELECTION_PATH,
    OVERLAY_SNAPSHOT_PATH as OPTIMAL_MA_SNAPSHOT_PATH,
    load_latest_optimal_ma_snapshot as _load_latest_optimal_ma_snapshot,
    optimal_ma_alignment,
    optimal_ma_soft_delta,
)
from new_strategy.optimal_ma_publish_contract import OPTIMAL_MA_ALL_SELECTION_PATH
from new_strategy.paths import data_path, output_path, strategy_output_path

APP_DIR = strategy_output_path()
UI_CONFIG_PATH = APP_DIR / "strategy_dashboard_config.json"
REFRESH_META_PATH = APP_DIR / "refresh_runtime_metadata.json"
FAST_ALERT_META_PATH = APP_DIR / "fast_alert_metadata.json"
PIPELINE_PROGRESS_PATH = APP_DIR / "dashboard_pipeline_progress.json"
PIPELINE_STDOUT_PATH = APP_DIR / "dashboard_pipeline_stdout.log"
PIPELINE_STDERR_PATH = APP_DIR / "dashboard_pipeline_stderr.log"
PIPELINE_RUNS_DIR = APP_DIR / "dashboard_pipeline_runs"
PIPELINE_HISTORY_PATH = APP_DIR / "dashboard_pipeline_history.csv"

PRICE_PANEL_PATH = data_path("price_panel.csv")
MACRO_DAILY_PATH = data_path("macro_daily.csv")
FUNDAMENTAL_PATH = data_path("fundamental_quarterly_multi.csv")
LIVE_QUOTES_PATH = data_path("live_quotes.csv")

SIGNAL_FAST_LATEST_PATH = APP_DIR / "signal_daily_fast_latest.csv"
SIGNAL_LATEST_PATH = APP_DIR / "signal_daily_latest.csv"
SIGNAL_DAILY_PATH = APP_DIR / "signal_daily.csv"
DECISION_FAST_LATEST_PATH = APP_DIR / "decision_report_fast_latest.csv"
DECISION_DAILY_PATH = APP_DIR / "decision_report_daily.csv"
HEALTH_PATH = APP_DIR / "data_health_summary.csv"
EVAL_PATH = APP_DIR / "strategy_eval.csv"
RESEARCH_PATH = APP_DIR / "research_condition_performance.csv"
RESEARCH_INDUSTRY_PATH = APP_DIR / "research_condition_performance_by_industry.csv"
RULE_TOP_PATH = APP_DIR / "research_rule_candidates_top.csv"
RULE_INDUSTRY_PATH = APP_DIR / "research_rule_candidates_by_industry.csv"
STRATEGY_META_PATH = APP_DIR / "strategy_metadata.json"
SCHEDULE_STATE_PATH = APP_DIR / "market_schedule_state.json"
ACCESS_GUIDE_MD_PATH = APP_DIR / "friend_access_guide.md"
ACCESS_GUIDE_HTML_PATH = APP_DIR / "friend_access_guide.html"
FAST_STATE_PATH = APP_DIR / "fast_position_state.csv"
V2_SIM_SUMMARY_PATH = output_path("v2_simulation_summary", "v2_simulation_master_summary.csv")
TAILSCALE_EXE_PATH = Path(r"C:\Program Files\Tailscale\tailscale.exe")
TRADE_LOG_PATH = APP_DIR / "trade_log.csv"
BRIDGE_DIR = APP_DIR / "telegram_bridge"
MANUAL_TRADES_PATH = BRIDGE_DIR / "manual_portfolio_trades.csv"
MANUAL_POSITIONS_PATH = BRIDGE_DIR / "manual_portfolio_positions.csv"
TELEGRAM_JOB_LOG_PATH = BRIDGE_DIR / "telegram_bridge_job_log.csv"

PIPELINE_HISTORY_COLUMNS = [
    "run_id",
    "started_at",
    "updated_at",
    "finished_at",
    "status",
    "percent",
    "stage",
    "detail",
    "duration_seconds",
    "pid",
    "description",
    "command",
    "stdout_path",
    "stderr_path",
]

CONFIG_SPECS: list[dict[str, Any]] = [
    {"group": "유니버스", "key": "min_adv20", "label": "최소 20일 평균 거래대금", "kind": "float", "step": 100000000.0, "help": "유동성이 너무 낮은 종목은 제외합니다."},
    {"group": "유니버스", "key": "recent_filing_days", "label": "최근 공시 유효일", "kind": "int", "step": 1, "help": "최근 공시를 몇 일 동안 유효한 정보로 볼지 정합니다."},
    {"group": "유니버스", "key": "watchlist_size", "label": "WATCH 후보 수", "kind": "int", "step": 1, "help": "관찰 종목으로 유지할 최대 개수입니다."},
    {"group": "포지션", "key": "max_positions", "label": "최대 보유 종목 수", "kind": "int", "step": 1, "help": "전략 시뮬레이션 기준 최대 동시 보유 수입니다."},
    {"group": "포지션", "key": "min_hold_days", "label": "최소 보유 일수", "kind": "int", "step": 1, "help": "진입 직후 바로 청산하지 않기 위한 최소 보유 일수입니다."},
    {"group": "포지션", "key": "max_holding_days", "label": "최대 보유 일수", "kind": "int", "step": 1, "help": "장기 정체 포지션을 강제 정리하는 기준입니다."},
    {"group": "리스크", "key": "fixed_stop_loss", "label": "고정 손절", "kind": "float", "step": 0.01, "help": "예: -0.10이면 -10% 손절입니다."},
    {"group": "리스크", "key": "neutral_target_ratio", "label": "중립장 목표 비중", "kind": "float", "step": 0.05, "help": "중립장에서 사용할 총 노출 비중입니다."},
    {"group": "리스크", "key": "riskoff_target_ratio", "label": "위험장 목표 비중", "kind": "float", "step": 0.05, "help": "위험장에서는 기본적으로 신규 매수를 줄입니다."},
    {"group": "리스크", "key": "riskoff_exposure_cutoff", "label": "위험장 차단 기준", "kind": "float", "step": 0.05, "help": "노출 비중이 이 값 이하이면 신규 매수를 차단합니다."},
    {"group": "타이밍", "key": "max_ret_5", "label": "5일 수익률 과열 상한", "kind": "float", "step": 0.01, "help": "단기 급등 종목 추격을 피하기 위한 상한입니다."},
    {"group": "타이밍", "key": "max_atr_ratio", "label": "ATR 비율 상한", "kind": "float", "step": 0.01, "help": "변동성 과열 종목을 걸러냅니다."},
    {"group": "타이밍", "key": "max_dist_ma_mid", "label": "중기 이평 이격 상한", "kind": "float", "step": 0.01, "help": "기존 중기 이평 대비 과열 종목을 제한합니다."},
    {"group": "타이밍", "key": "min_timing_score", "label": "최소 타이밍 점수", "kind": "float", "step": 0.01, "help": "기존 타이밍 점수의 최소 기준입니다."},
    {"group": "신호", "key": "buy_threshold", "label": "BUY 점수 기준", "kind": "float", "step": 0.01, "help": "이 점수 이상이면 BUY 후보로 봅니다."},
    {"group": "신호", "key": "watch_threshold", "label": "WATCH 점수 기준", "kind": "float", "step": 0.01, "help": "이 점수 이상이면 WATCH 후보로 봅니다."},
    {"group": "신호", "key": "sell_threshold", "label": "SELL 점수 기준", "kind": "float", "step": 0.01, "help": "이 점수 이하이면 SELL 후보로 봅니다."},
    {"group": "신호", "key": "pre_signal_threshold", "label": "BUY_WATCH 점수 기준", "kind": "float", "step": 0.01, "help": "WATCH 중에서도 점수가 높으면 BUY_WATCH로 표시합니다."},
    {"group": "연구", "key": "research_min_obs", "label": "연구 최소 표본 수", "kind": "int", "step": 1, "help": "조건부 성과 분석에서 필요한 최소 표본 수입니다."},
    {"group": "ML", "key": "ml_backend", "label": "ML 백엔드", "kind": "text", "help": "auto, none, lightgbm, xgboost, sklearn_rf 중 하나입니다."},
    {"group": "ML", "key": "ml_train_window_days", "label": "ML 학습 구간", "kind": "int", "step": 1, "help": "보조 모델이 학습에 사용하는 과거 일수입니다."},
    {"group": "ML", "key": "ml_horizon_days", "label": "ML 타깃 구간", "kind": "int", "step": 1, "help": "보조 모델이 보는 미래 수익률 구간입니다."},
]

SIGNAL_ORDER = {"BUY": 0, "BUY_WATCH": 1, "HOLD": 2, "SELL_WATCH": 3, "SELL": 4}
SIGNAL_LABELS_INTRADAY = {
    "BUY": "매수",
    "BUY_WATCH": "소액매수검토",
    "WATCH": "관심유지",
    "HOLD": "보유유지",
    "SELL_WATCH": "비중축소검토",
    "SELL": "매도",
}
SIGNAL_LABELS_POSTCLOSE = {
    "BUY": "익일매수",
    "BUY_WATCH": "익일관심유지",
    "WATCH": "익일관심유지",
    "HOLD": "익일보유",
    "SELL_WATCH": "익일비중축소검토",
    "SELL": "익일매도",
}
SHORT_SIGNAL_LABELS_INTRADAY = {
    "BUY": "매수",
    "BUY_WATCH": "관심",
    "WATCH": "관심",
    "HOLD": "보유",
    "SELL_WATCH": "축소검토",
    "SELL": "매도",
}
SHORT_SIGNAL_LABELS_POSTCLOSE = {
    "BUY": "익일매수",
    "BUY_WATCH": "익일관심",
    "WATCH": "익일관심",
    "HOLD": "익일보유",
    "SELL_WATCH": "익일축소검토",
    "SELL": "익일매도",
}
TERM_NOTES = [
    "PTI*: 공시일 기준으로 실제 시장이 알 수 있었던 재무 정보만 쓰는 방식입니다.",
    "QoQ*: 직전 분기 대비 변화입니다.",
    "TTM*: 최근 4개 분기 합계입니다.",
    "ATR*: 평균 진폭 기반 변동성 지표입니다.",
    "EOD*: 장 종료 후 확정 종가 기준 데이터입니다.",
]


def is_execution_window(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    current = now.time()
    return time(8, 0) <= current <= time(20, 0)


def signal_label(signal: Any, *, execution_window: bool | None = None) -> str:
    execution_window = is_execution_window() if execution_window is None else execution_window
    label_map = SIGNAL_LABELS_INTRADAY if execution_window else SIGNAL_LABELS_POSTCLOSE
    return label_map.get(str(signal).upper(), str(signal))


def short_signal_label(signal: Any, *, execution_window: bool | None = None) -> str:
    execution_window = is_execution_window() if execution_window is None else execution_window
    label_map = SHORT_SIGNAL_LABELS_INTRADAY if execution_window else SHORT_SIGNAL_LABELS_POSTCLOSE
    return label_map.get(str(signal).upper(), str(signal))


def market_state_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    return {
        "risk_on": "정상구간",
        "neutral": "주의구간",
        "risk_off": "방어구간",
    }.get(text, text or "unknown")


def operating_intensity_label(exposure: Any) -> str:
    value = _safe_float(exposure, 1.0)
    if value >= 0.95:
        return "100%"
    if value >= 0.55:
        return "70%"
    if value >= 0.25:
        return "40%"
    return f"{value:.0%}"


def decision_cell_class(label: str) -> str:
    text = str(label or "")
    if "매수" in text:
        return "buy"
    if "매도" in text:
        return "sell"
    if "보유" in text:
        return "hold"
    return "watch"


def prettify_risk_flag(value: Any) -> str:
    raw = str(value or "").strip()
    mapping = {
        "macro_risk_off": "매크로 위험장",
        "high_volatility": "고변동성",
        "earnings_exception": "실적 예외",
        "weekly_sell_watch": "주봉 매도경계",
        "monthly_overheat": "월봉 과열",
        "timing_break": "타이밍 훼손",
        "quality_drop": "품질 저하",
        "stop_loss": "손절 기준",
        "signal_missing": "전략신호 없음",
    }
    if not raw:
        return "-"
    parts = [mapping.get(part.strip(), part.strip().replace("_", " ")) for part in raw.split("|") if part.strip()]
    return " · ".join(parts) if parts else "-"


def _display_signal_count(counts: dict[str, int], signal: str) -> int:
    signal = str(signal or "").upper()
    if signal == "BUY_WATCH":
        return int(counts.get("BUY_WATCH", 0)) + int(counts.get("WATCH", 0))
    return int(counts.get(signal, 0))


def signal_distribution_text(counts: dict[str, int], *, execution_window: bool, short: bool = False) -> str:
    label_fn = short_signal_label if short else signal_label
    return (
        f"{label_fn('BUY', execution_window=execution_window)} {_display_signal_count(counts, 'BUY')} / "
        f"{label_fn('BUY_WATCH', execution_window=execution_window)} {_display_signal_count(counts, 'BUY_WATCH')} / "
        f"{label_fn('HOLD', execution_window=execution_window)} {_display_signal_count(counts, 'HOLD')} / "
        f"{label_fn('SELL_WATCH', execution_window=execution_window)} {_display_signal_count(counts, 'SELL_WATCH')} / "
        f"{label_fn('SELL', execution_window=execution_window)} {_display_signal_count(counts, 'SELL')}"
    )


def has_risk_flag(value: Any, target: str) -> bool:
    target_text = str(target or "").strip().lower()
    if not target_text:
        return False
    raw = "" if pd.isna(value) else str(value)
    parts = [part.strip().lower() for part in raw.split("|") if part.strip()]
    return target_text in parts


def format_v2_timing_summary(row: pd.Series | dict[str, Any], *, multiline: bool = False) -> str:
    month_window = pd.to_numeric(pd.Series([row.get("v2_month_window")]), errors="coerce").iloc[0]
    month_dist = pd.to_numeric(pd.Series([row.get("v2_month_period_dist")]), errors="coerce").iloc[0]
    week_window = pd.to_numeric(pd.Series([row.get("v2_week_window")]), errors="coerce").iloc[0]
    week_dist = pd.to_numeric(pd.Series([row.get("v2_week_period_dist")]), errors="coerce").iloc[0]
    month_ready = bool(row.get("v2_month_buy_ready", row.get("monthly_main_ok", False)))
    week_sell = bool(row.get("v2_week_sell_trigger", False))
    week_watch = bool(row.get("v2_week_sell_watch", False))

    parts: list[str] = []
    if pd.notna(month_window):
        month_state = "월봉 매수 준비" if month_ready else "월봉 매수 대기"
        month_suffix = f" · 최적 월이평 {int(float(month_window))} · 기준 이격 {_safe_float(month_dist):+.1%}" if pd.notna(month_dist) else f" · 최적 월이평 {int(float(month_window))}"
        parts.append(f"{month_state}{month_suffix}")
    if pd.notna(week_window):
        if week_sell:
            week_state = "주봉 매도 트리거"
        elif week_watch:
            week_state = "주봉 매도 경계"
        else:
            week_state = "주봉 정상"
        week_suffix = f" · 최적 주이평 {int(float(week_window))} · 기준 이격 {_safe_float(week_dist):+.1%}" if pd.notna(week_dist) else f" · 최적 주이평 {int(float(week_window))}"
        parts.append(f"{week_state}{week_suffix}")
    if not parts:
        return "-"
    return "\n".join(parts) if multiline else " / ".join(parts)


def format_v2_ma_axis_summary(row: pd.Series | dict[str, Any]) -> str:
    month_window = pd.to_numeric(pd.Series([row.get("v2_month_window")]), errors="coerce").iloc[0]
    month_dist = pd.to_numeric(pd.Series([row.get("v2_month_period_dist")]), errors="coerce").iloc[0]
    week_window = pd.to_numeric(pd.Series([row.get("v2_week_window")]), errors="coerce").iloc[0]
    week_dist = pd.to_numeric(pd.Series([row.get("v2_week_period_dist")]), errors="coerce").iloc[0]

    if bool(row.get("v2_month_buy_cross", False)):
        month_state = "신규 상향돌파"
    elif bool(row.get("v2_month_sell_cross", False)):
        month_state = "신규 하향돌파"
    elif bool(row.get("v2_month_above_maintain", False)) or (pd.notna(month_dist) and month_dist >= 0):
        month_state = "유지상방"
    elif pd.notna(month_dist) and month_dist < 0:
        month_state = "유지하방"
    else:
        month_state = "확인필요"

    if bool(row.get("v2_week_sell_trigger", False)):
        week_state = "매도트리거"
    elif bool(row.get("v2_week_sell_watch", False)):
        week_state = "매도경계"
    elif pd.notna(week_dist) and week_dist >= 0:
        week_state = "정상"
    elif pd.notna(week_dist) and week_dist < 0:
        week_state = "약세"
    else:
        week_state = "확인필요"

    parts: list[str] = []
    if pd.notna(month_window):
        suffix = f" ({_safe_float(month_dist):+.1%})" if pd.notna(month_dist) else ""
        parts.append(f"월{int(float(month_window))} {month_state}{suffix}")
    if pd.notna(week_window):
        suffix = f" ({_safe_float(week_dist):+.1%})" if pd.notna(week_dist) else ""
        parts.append(f"주{int(float(week_window))} {week_state}{suffix}")
    if parts:
        return "\n".join(parts)

    fallback_window = pd.to_numeric(pd.Series([row.get("optimal_ma_window")]), errors="coerce").iloc[0]
    fallback_timeframe = str(row.get("optimal_ma_timeframe_ko") or row.get("optimal_ma_timeframe") or "").strip()
    fallback_signal = str(row.get("optimal_ma_signal_ko") or "").strip()
    fallback_close = pd.to_numeric(pd.Series([row.get("latest_close")]), errors="coerce").iloc[0]
    fallback_line = pd.to_numeric(pd.Series([row.get("optimal_ma_line_price")]), errors="coerce").iloc[0]

    if pd.notna(fallback_window) and fallback_timeframe:
        timeframe_label = "월" if "월" in fallback_timeframe else "주" if "주" in fallback_timeframe else fallback_timeframe
        dist_text = ""
        if pd.notna(fallback_close) and pd.notna(fallback_line) and float(fallback_line) != 0:
            fallback_dist = float(fallback_close) / float(fallback_line) - 1.0
            dist_text = f" ({fallback_dist:+.1%})"
        signal_text = fallback_signal or "확인필요"
        return f"{timeframe_label}{int(float(fallback_window))} {signal_text}{dist_text}"

    return "-"


def format_price_axis_summary(row: pd.Series | dict[str, Any]) -> str:
    signal = str(row.get("display_signal") or row.get("signal") or "").upper()
    risk_value = row.get("risk_flag", row.get("리스크", ""))
    rules = [part.strip() for part in str(row.get("가격 규칙") or "").split(" / ") if part.strip()]

    if signal == "NO_SIGNAL":
        title = "신호없음"
        priority = "조건 충족 전 관찰"
    elif signal in {"BUY", "BUY_WATCH", "WATCH"}:
        title = "관찰구간"
        priority = next((part for part in rules if part.startswith("추격금지")), "")
        if has_risk_flag(risk_value, "monthly_overheat"):
            title = "과열주의"
        elif has_risk_flag(risk_value, "high_volatility"):
            title = "변동성주의"
        if not priority:
            priority = next((part for part in rules if part.startswith("관찰")), "")
    elif signal in {"HOLD", "SELL_WATCH"}:
        title = "방어관리"
        priority = next((part for part in rules if part.startswith("유효방어")), "")
        if has_risk_flag(risk_value, "weekly_sell_watch"):
            title = "방어경계"
        if not priority:
            priority = next((part for part in rules if part.startswith("원금보호")), "")
        if not priority:
            priority = next((part for part in rules if part.startswith("초기손절")), "")
    else:
        title = "정리우선"
        priority = next((part for part in rules if part.startswith("유효방어")), "")
        if not priority:
            priority = next((part for part in rules if part.startswith("초기손절")), "")

    extra_lines: list[str] = []
    industry_ret = pd.to_numeric(pd.Series([row.get("industry_period_return")]), errors="coerce").iloc[0]
    industry_volume = pd.to_numeric(pd.Series([row.get("industry_volume_avg")]), errors="coerce").iloc[0]
    industry_tf = str(row.get("industry_timeframe") or row.get("optimal_ma_timeframe") or "").strip().lower()
    industry_window = pd.to_numeric(pd.Series([row.get("industry_window") or row.get("optimal_ma_window")]), errors="coerce").iloc[0]
    tf_label = ""
    if pd.notna(industry_window):
        prefix = "월" if industry_tf == "monthly" else "주" if industry_tf == "weekly" else "일"
        tf_label = f"{prefix}{int(float(industry_window))}"
    if pd.notna(industry_ret):
        if tf_label:
            extra_lines.append(f"업종 수익률({tf_label}) {float(industry_ret):+.1%}")
        else:
            extra_lines.append(f"업종 수익률 {float(industry_ret):+.1%}")
    if pd.notna(industry_volume):
        extra_lines.append(f"업종 거래량 평 {float(industry_volume):,.0f}")

    parts = [title]
    if priority:
        parts.append(priority)
    parts.extend(extra_lines)
    return "\n".join(parts)


def format_financial_axis_summary(row: pd.Series | dict[str, Any]) -> str:
    op_margin = pd.to_numeric(pd.Series([row.get("op_margin_pti")]), errors="coerce").iloc[0]
    op_qoq = pd.to_numeric(pd.Series([row.get("op_income_qoq_pti")]), errors="coerce").iloc[0]
    op_ttm = pd.to_numeric(pd.Series([row.get("op_income_q_ttm")]), errors="coerce").iloc[0]
    basis_quarter = str(row.get("근거 기준 분기") or "-").strip()
    basis_date = str(row.get("기준 공시일") or "-").strip()

    if all(pd.isna(value) for value in [op_margin, op_qoq, op_ttm]):
        if basis_quarter != "-" or basis_date != "-":
            return f"{basis_quarter} · {basis_date}\n근거 부족"
        return "근거 부족"
    parts: list[str] = []
    if basis_quarter != "-" or basis_date != "-":
        parts.append(f"{basis_quarter} · {basis_date}")
    parts.append(f"영업이익률 {'-' if pd.isna(op_margin) else f'{_safe_float(op_margin):.1%}'}")
    parts.append(f"영업이익 QoQ {'-' if pd.isna(op_qoq) else _format_large_number(op_qoq)}")
    parts.append(f"최근4Q 영업 {'-' if pd.isna(op_ttm) else _format_large_number(op_ttm)}")
    return "\n".join(parts)


def format_macro_axis_summary(row: pd.Series | dict[str, Any]) -> str:
    regime = market_state_label(row.get("market_regime"))
    exposure = row.get("market_exposure")
    if regime in {"-", "", "unknown"} and pd.isna(pd.to_numeric(pd.Series([exposure]), errors="coerce").iloc[0]):
        return "-"
    intensity = operating_intensity_label(exposure)
    usdkrw = pd.to_numeric(pd.Series([row.get("usdkrw")]), errors="coerce").iloc[0]
    vix = pd.to_numeric(pd.Series([row.get("vix")]), errors="coerce").iloc[0]
    if regime == "정상구간":
        note = "표준 운용"
    elif regime == "주의구간":
        note = "선별 운용"
    else:
        note = "보수 운용"
    macro_parts: list[str] = []
    if pd.notna(usdkrw):
        macro_parts.append(f"환율 {usdkrw:,.0f}")
    if pd.notna(vix):
        macro_parts.append(f"VIX {vix:.1f}")
    macro_line = " · ".join(macro_parts)
    if macro_line:
        return f"{regime} · {intensity}\n{macro_line}\n{note}"
    return f"{regime} · {intensity}\n{note}"


@st.cache_data(show_spinner=False)
def load_latest_industry_return_by_timeframe_window(_price_token: Any, timeframe: str, window: int) -> pd.DataFrame:
    if not PRICE_PANEL_PATH.exists() or int(window) <= 0:
        return pd.DataFrame(columns=["industry", "industry_return"])
    df = pd.read_csv(PRICE_PANEL_PATH, usecols=["date", "code", "industry", "close"], dtype={"code": str}, low_memory=False)
    if df.empty:
        return pd.DataFrame(columns=["industry", "industry_return"])
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["code", "date"])

    tf = str(timeframe or "").lower()
    if tf == "weekly":
        df["bucket"] = df["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
        base = (
            df.groupby(["code", "industry", "bucket"], as_index=False)
            .agg({"close": "last"})
            .sort_values(["code", "bucket"])
        )
        base["industry_return"] = base.groupby("code", sort=False)["close"].transform(lambda s: s / s.shift(int(window)) - 1.0)
        latest = base.groupby("code", as_index=False).tail(1)
    elif tf == "monthly":
        df["bucket"] = df["date"].dt.to_period("M").dt.end_time.dt.normalize()
        base = (
            df.groupby(["code", "industry", "bucket"], as_index=False)
            .agg({"close": "last"})
            .sort_values(["code", "bucket"])
        )
        base["industry_return"] = base.groupby("code", sort=False)["close"].transform(lambda s: s / s.shift(int(window)) - 1.0)
        latest = base.groupby("code", as_index=False).tail(1)
    else:
        base = df.copy()
        base["industry_return"] = base.groupby("code", sort=False)["close"].transform(lambda s: s / s.shift(int(window)) - 1.0)
        latest = base.groupby("code", as_index=False).tail(1)

    latest = latest.dropna(subset=["industry_return"])
    if latest.empty:
        return pd.DataFrame(columns=["industry", "industry_return"])
    return latest.groupby("industry", as_index=False)["industry_return"].mean()


def _latest_fundamental_quarterly(fundamental_df: pd.DataFrame) -> pd.DataFrame:
    if fundamental_df.empty:
        return fundamental_df
    out = fundamental_df.copy()
    out["공시일"] = pd.to_datetime(out["공시일"], errors="coerce")
    return out.dropna(subset=["공시일"]).sort_values("공시일").reset_index(drop=True)


def _compute_qoq_from_quarters(series: pd.Series) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 2:
        return float("nan")
    return float(clean.iloc[-1] - clean.iloc[-2])


def _compute_qoq_accel_from_quarters(series: pd.Series) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 3:
        return float("nan")
    current_qoq = float(clean.iloc[-1] - clean.iloc[-2])
    prev_qoq = float(clean.iloc[-2] - clean.iloc[-3])
    return current_qoq - prev_qoq


def build_financial_blocks(row: pd.Series | dict[str, Any], fundamental_df: pd.DataFrame) -> list[dict[str, str]]:
    latest_quarters = _latest_fundamental_quarterly(fundamental_df).tail(4).copy()
    latest_quarter = latest_quarters.tail(1)

    op_margin = pd.to_numeric(pd.Series([row.get("op_margin_pti")]), errors="coerce").iloc[0]
    net_margin = pd.to_numeric(pd.Series([row.get("net_margin_pti")]), errors="coerce").iloc[0]
    op_qoq = pd.to_numeric(pd.Series([row.get("op_income_qoq_pti")]), errors="coerce").iloc[0]
    net_qoq = pd.to_numeric(pd.Series([row.get("net_income_qoq_pti")]), errors="coerce").iloc[0]
    op_accel = pd.to_numeric(pd.Series([row.get("op_income_qoq_accel")]), errors="coerce").iloc[0]
    net_accel = pd.to_numeric(pd.Series([row.get("net_income_qoq_accel")]), errors="coerce").iloc[0]
    op_ttm = pd.to_numeric(pd.Series([row.get("op_income_q_ttm")]), errors="coerce").iloc[0]
    net_ttm = pd.to_numeric(pd.Series([row.get("net_income_q_ttm")]), errors="coerce").iloc[0]
    op_vol = pd.to_numeric(pd.Series([row.get("op_income_q_vol_4q")]), errors="coerce").iloc[0]
    net_vol = pd.to_numeric(pd.Series([row.get("net_income_q_vol_4q")]), errors="coerce").iloc[0]
    gap_ratio = pd.to_numeric(pd.Series([row.get("net_op_gap_ratio")]), errors="coerce").iloc[0]

    if not latest_quarter.empty:
        latest_revenue_q = pd.to_numeric(latest_quarter["분기매출액"], errors="coerce").iloc[0] if "분기매출액" in latest_quarter.columns else float("nan")
        latest_op_q = pd.to_numeric(latest_quarter["분기영업이익"], errors="coerce").iloc[0] if "분기영업이익" in latest_quarter.columns else float("nan")
        latest_net_q = pd.to_numeric(latest_quarter["분기당기순이익"], errors="coerce").iloc[0] if "분기당기순이익" in latest_quarter.columns else float("nan")
        latest_op_margin_q = pd.to_numeric(latest_quarter["분기영업이익률"], errors="coerce").iloc[0] if "분기영업이익률" in latest_quarter.columns else float("nan")
    else:
        latest_revenue_q = latest_op_q = latest_net_q = latest_op_margin_q = float("nan")

    if pd.isna(op_margin):
        op_margin = latest_op_margin_q
    if pd.isna(op_margin) and pd.notna(latest_revenue_q) and latest_revenue_q != 0 and pd.notna(latest_op_q):
        op_margin = float(latest_op_q) / float(latest_revenue_q)
    if pd.isna(net_margin) and pd.notna(latest_revenue_q) and latest_revenue_q != 0 and pd.notna(latest_net_q):
        net_margin = float(latest_net_q) / float(latest_revenue_q)

    if pd.isna(op_qoq) and "분기영업이익" in latest_quarters.columns:
        op_qoq = _compute_qoq_from_quarters(latest_quarters["분기영업이익"])
    if pd.isna(net_qoq) and "분기당기순이익" in latest_quarters.columns:
        net_qoq = _compute_qoq_from_quarters(latest_quarters["분기당기순이익"])

    if pd.isna(op_accel) and "분기영업이익" in latest_quarters.columns:
        op_accel = _compute_qoq_accel_from_quarters(latest_quarters["분기영업이익"])
    if pd.isna(net_accel) and "분기당기순이익" in latest_quarters.columns:
        net_accel = _compute_qoq_accel_from_quarters(latest_quarters["분기당기순이익"])

    if pd.isna(op_ttm) and "분기영업이익" in latest_quarters.columns:
        op_ttm = float(pd.to_numeric(latest_quarters["분기영업이익"], errors="coerce").sum(min_count=1))
    if pd.isna(net_ttm) and "분기당기순이익" in latest_quarters.columns:
        net_ttm = float(pd.to_numeric(latest_quarters["분기당기순이익"], errors="coerce").sum(min_count=1))

    if pd.isna(op_vol) and "분기영업이익" in latest_quarters.columns:
        op_vol = float(pd.to_numeric(latest_quarters["분기영업이익"], errors="coerce").std())
    if pd.isna(net_vol) and "분기당기순이익" in latest_quarters.columns:
        net_vol = float(pd.to_numeric(latest_quarters["분기당기순이익"], errors="coerce").std())

    gap_amount = float("nan")
    if pd.notna(latest_net_q) and pd.notna(latest_op_q):
        gap_amount = abs(float(latest_net_q) - float(latest_op_q))
    if pd.isna(gap_ratio) and pd.notna(latest_revenue_q) and latest_revenue_q != 0 and pd.notna(gap_amount):
        gap_ratio = float(gap_amount) / abs(float(latest_revenue_q))

    def pct_text(value: Any) -> str:
        return "-" if pd.isna(value) else f"{float(value):.1%}"

    def amt_text(value: Any) -> str:
        return "-" if pd.isna(value) else _format_large_number(value)

    profitability_note = ""
    if pd.isna(op_margin) and pd.isna(net_margin):
        profitability_note = "원천 매출 데이터 공란"

    stability_gap = pct_text(gap_ratio) if pd.notna(gap_ratio) else amt_text(gap_amount)

    return [
        {
            "title": "수익성",
            "body": f"영업이익률 {pct_text(op_margin)}\n순이익률 {pct_text(net_margin)}",
            "note": profitability_note,
        },
        {
            "title": "성장성",
            "body": (
                f"영업 QoQ {amt_text(op_qoq)}\n"
                f"순익 QoQ {amt_text(net_qoq)}\n"
                f"가속도 영업 {amt_text(op_accel)} / 순익 {amt_text(net_accel)}"
            ),
            "note": "",
        },
        {
            "title": "지속성",
            "body": f"최근4Q 영업 {amt_text(op_ttm)}\n최근4Q 순익 {amt_text(net_ttm)}",
            "note": "",
        },
        {
            "title": "안정성",
            "body": (
                f"영업 변동성 {amt_text(op_vol)}\n"
                f"순익 변동성 {amt_text(net_vol)}\n"
                f"순익-영업 괴리 {stability_gap}"
            ),
            "note": "",
        },
    ]


def compact_execution_guide(row: pd.Series | dict[str, Any], *, execution_window: bool) -> str:
    signal = str(row.get("display_signal") or row.get("signal") or "").upper()
    if execution_window:
        guide_map = {
            "BUY": "시초 확인 후 분할매수",
            "BUY_WATCH": "관심 유지 · 강하면 소액",
            "WATCH": "관심 유지",
            "HOLD": "보유 유지 · 방어선 점검",
            "SELL_WATCH": "비중축소 검토",
            "SELL": "매도 우선",
            "NO_SIGNAL": "신호 없음 · 조건 대기",
        }
    else:
        guide_map = {
            "BUY": "익일 눌림 확인 후 진입",
            "BUY_WATCH": "익일 관심 유지",
            "WATCH": "익일 관심 유지",
            "HOLD": "익일보유 · 방어선 점검",
            "SELL_WATCH": "익일 비중축소 검토",
            "SELL": "익일 매도 우선",
            "NO_SIGNAL": "신호 없음 · 조건 대기",
        }
    return guide_map.get(signal, "신호 재확인")


def format_table_text(value: Any, *, break_paren: bool = False, slash_to_break: bool = False) -> str:
    text = html.escape(str(value or ""))
    if slash_to_break:
        text = text.replace(" / ", "<br>")
    if break_paren:
        text = text.replace(" (", "<br>(")
    return text.replace("\n", "<br>")


def default_action_guide(signal: Any, *, execution_window: bool) -> str:
    signal = str(signal).upper()
    if execution_window:
        guide_map = {
            "BUY": "추격보다 가격 안정 구간에서 분할 매수를 우선합니다.",
            "BUY_WATCH": "관심 유지가 기본입니다. 장중 강도와 거래대금이 좋으면 소액매수까지 검토합니다.",
            "WATCH": "관심 유지가 기본입니다. 아직은 주문보다 초반 흐름 확인이 우선입니다.",
            "HOLD": "보유 유지가 기본입니다. 방어선 이탈 시 비중축소 또는 매도로 전환합니다.",
            "SELL_WATCH": "비중축소 검토가 우선입니다. 약세가 이어지면 절반정리 또는 매도로 강화합니다.",
            "SELL": "실행 가능한 매도 신호입니다. 반등 대기보다 정리를 우선합니다.",
            "NO_SIGNAL": "최신 전략 신호가 없어 조건 충족 전까지 관찰만 유지합니다.",
        }
    else:
        guide_map = {
            "BUY": "익일 시초 5~15분 대기 후 가격 안정 또는 첫 눌림 확인 뒤 분할 진입합니다.",
            "BUY_WATCH": "익일 관심 유지가 기본입니다. 시초 강도가 좋으면 소액매수를 검토하고, 아니면 관찰 유지로 둡니다.",
            "WATCH": "익일 관심 유지가 기본입니다. 주문보다 장초반 흐름 확인이 우선입니다.",
            "HOLD": "익일 보유 유지가 기본입니다. 시초 약세가 크면 비중축소, 방어선 이탈이면 매도로 전환합니다.",
            "SELL_WATCH": "익일 비중축소 검토가 우선입니다. 장초반 약세면 절반정리 또는 축소를 먼저 봅니다.",
            "SELL": "익일 장 초반 유동성 구간에서 매도를 우선합니다. 약세가 크면 지체 없이 정리합니다.",
            "NO_SIGNAL": "최신 전략 신호가 없어 다음 계산 시점까지 관찰만 유지합니다.",
        }
    return guide_map.get(signal, "장 시작 후 신호를 다시 확인합니다.")


def resolve_action_guide(row: pd.Series, *, execution_window: bool) -> str:
    key = "intraday_action_guide" if execution_window else "next_day_action_guide"
    value = str(row.get(key) or "").strip()
    if value:
        return value
    display_signal = str(row.get("display_signal") or row.get("signal") or "")
    return default_action_guide(display_signal, execution_window=execution_window)


@st.cache_data(show_spinner=False)
def load_fast_position_state(_output_token: Any) -> pd.DataFrame:
    df = _read_csv(FAST_STATE_PATH)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def _parse_stop_pct(value: Any) -> float | None:
    text = str(value or "").strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text) / 100.0
    except Exception:
        return None


def _non_nan_float(value: Any) -> float | None:
    num = _safe_float(value, float("nan"))
    return None if pd.isna(num) else float(num)


def compute_risk_levels(
    row: pd.Series | dict[str, Any],
    *,
    current_price: float | None,
    entry_price: float | None = None,
) -> dict[str, float | None]:
    stop_pct = _parse_stop_pct(row.get("stop_rule"))
    month_10_ma = _non_nan_float(row.get("month_10_ma"))
    week_10_ma = _non_nan_float(row.get("week_10_ma"))
    day_20_ma = _non_nan_float(row.get("ma_day_20"))

    initial_stop = None
    if entry_price is not None and stop_pct is not None:
        initial_stop = entry_price * (1.0 + stop_pct)

    breakeven_guard = None
    if entry_price is not None and current_price is not None and current_price >= entry_price * 1.08:
        breakeven_guard = entry_price

    effective_candidates = [v for v in [initial_stop, breakeven_guard] if v is not None]
    effective_guard = max(effective_candidates) if effective_candidates else None

    return {
        "initial_stop": initial_stop,
        "breakeven_guard": breakeven_guard,
        "month_10_ma": month_10_ma,
        "week_10_ma": week_10_ma,
        "day_20_ma": day_20_ma,
        "effective_guard": effective_guard,
    }


def build_price_execution_guide(
    row: pd.Series,
    *,
    current_price: float | None,
    current_basis: str,
    execution_window: bool,
    position_row: pd.Series | None = None,
) -> str:
    signal = str(row.get("display_signal") or row.get("signal") or "").upper()
    base_price = current_price if current_price is not None and pd.notna(current_price) else _safe_float(row.get("close"), float("nan"))
    if pd.isna(base_price):
        return resolve_action_guide(row, execution_window=execution_window)

    entry_price = None
    if position_row is not None and not position_row.empty:
        if pd.notna(position_row.get("avg_price")):
            entry_price = float(position_row.get("avg_price"))
        elif pd.notna(position_row.get("entry_price")):
            entry_price = float(position_row.get("entry_price"))
    levels = compute_risk_levels(row, current_price=float(base_price), entry_price=entry_price)
    parts = [resolve_action_guide(row, execution_window=execution_window), f"기준가 {base_price:,.0f}원({current_basis})"]

    if signal in {"BUY", "BUY_WATCH"}:
        watch_low = base_price * 0.99
        watch_high = base_price * 1.01
        no_chase = base_price * 1.02
        parts.append(f"관찰 구간 {watch_low:,.0f}~{watch_high:,.0f}원")
        parts.append(f"추격 금지 상단 {no_chase:,.0f}원")
        if levels["initial_stop"] is None:
            stop_pct = _parse_stop_pct(row.get("stop_rule"))
            if stop_pct is not None:
                parts.append(f"진입 후 초기 손절가 {base_price * (1.0 + stop_pct):,.0f}원")
        parts.append("익절 고정 목표가는 없고 추세 유지 여부로 재평가합니다.")
    elif signal in {"HOLD", "SELL", "SELL_WATCH"}:
        if entry_price is not None:
            parts.append(f"진입가 {entry_price:,.0f}원")
        if levels["initial_stop"] is not None:
            parts.append(f"초기 손절가 {levels['initial_stop']:,.0f}원")
        if levels["breakeven_guard"] is not None:
            parts.append(f"원금 보호선 {levels['breakeven_guard']:,.0f}원")
        if levels["effective_guard"] is not None:
            parts.append(f"현재 유효 방어선 {levels['effective_guard']:,.0f}원")
        parts.append("가격 방어는 초기 손절 → 원금 보호 순으로 관리합니다.")

    return " / ".join(parts)



def run_text_command(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=10)
        return (completed.stdout or completed.stderr or "").strip()
    except Exception:
        return ""


def _python_process_running(*patterns: str) -> bool:
    checks = " -and ".join([f"$_.CommandLine -like '*{pattern}*'" for pattern in patterns if pattern])
    if not checks:
        return False
    cmd = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine "
        f"-and ({checks}) }} | "
        "Select-Object -First 1 ProcessId"
    )
    return bool(run_text_command(["powershell", "-NoProfile", "-Command", cmd]))


def load_tailscale_status() -> dict[str, Any]:
    result: dict[str, Any] = {
        "installed": False,
        "logged_in": False,
        "backend_state": "-",
        "hostname": "-",
        "dns_name": "-",
        "ipv4": "-",
        "ipv6": "-",
        "magic_dns": "-",
        "login_url": "-",
    }
    exe = str(TAILSCALE_EXE_PATH) if TAILSCALE_EXE_PATH.exists() else "tailscale"
    status_text = run_text_command([exe, "status", "--json"])
    if not status_text:
        login_line = run_text_command([exe, "status"])
        if "Log in at:" in login_line:
            result["installed"] = True
            result["login_url"] = login_line.split("Log in at:", 1)[1].strip()
        return result
    result["installed"] = True
    try:
        payload = json.loads(status_text)
    except json.JSONDecodeError:
        return result
    result["backend_state"] = payload.get("BackendState", "-")
    result["logged_in"] = payload.get("BackendState") == "Running"
    result["magic_dns"] = payload.get("MagicDNSSuffix", "-")
    self_info = payload.get("Self", {}) or {}
    ips = self_info.get("TailscaleIPs", []) or payload.get("TailscaleIPs", [])
    if ips:
        result["ipv4"] = next((ip for ip in ips if ":" not in ip), "-")
        result["ipv6"] = next((ip for ip in ips if ":" in ip), "-")
    result["hostname"] = self_info.get("HostName", "-")
    dns_name = self_info.get("DNSName", "-")
    result["dns_name"] = dns_name[:-1] if isinstance(dns_name, str) and dns_name.endswith(".") else dns_name
    return result


def build_access_guide_documents(ts: dict[str, Any]) -> dict[str, str]:
    ip_url = f"http://{ts['ipv4']}:8501" if ts.get("ipv4") and ts.get("ipv4") != "-" else "-"
    dns_url = f"http://{ts['dns_name']}:8501" if ts.get("dns_name") and ts.get("dns_name") != "-" else "-"
    lines = [
        "# 접속 안내",
        "",
        "## 1. 휴대폰에 Tailscale 설치",
        "- Android (Google Play): https://play.google.com/store/apps/details?id=com.tailscale.ipn",
        "- iPhone/iPad (App Store): https://apps.apple.com/app/tailscale/id1470499037",
        "- Windows/Mac/Linux: https://tailscale.com/download",
        "",
        "## 2. Tailscale 로그인",
        "- Tailscale 앱을 열고 로그인합니다.",
        "- 공유를 받을 이메일 계정으로 로그인해야 합니다.",
        "",
        "## 3. 접속 주소",
        f"- Tailscale IP 주소: {ip_url}",
        f"- MagicDNS 주소: {dns_url}",
        "",
        "## 4. 접속이 안 될 때 확인할 것",
        "- Tailscale 앱이 켜져 있는지 확인합니다.",
        "- Tailscale 로그인 상태인지 확인합니다.",
        "- 공유 승인이 완료됐는지 확인합니다.",
        "- 위 두 주소 중 하나를 다시 열어봅니다.",
    ]
    ACCESS_GUIDE_MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    html_body = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>접속 안내</title>
  <style>
    body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 840px; margin: 40px auto; padding: 0 20px; line-height: 1.7; color: #1f2937; }}
    h1, h2 {{ color: #111827; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 16px; padding: 20px; margin: 16px 0; background: #f9fafb; }}
    code {{ background: #eef2ff; padding: 2px 6px; border-radius: 6px; }}
    a {{ color: #1d4ed8; text-decoration: none; }}
  </style>
</head>
<body>
  <h1>접속 안내</h1>
  <div class="card">
    <h2>1. 휴대폰에 Tailscale 설치</h2>
    <ul>
      <li>Android (Google Play): <a href="https://play.google.com/store/apps/details?id=com.tailscale.ipn">설치 링크</a></li>
      <li>iPhone/iPad (App Store): <a href="https://apps.apple.com/app/tailscale/id1470499037">설치 링크</a></li>
      <li>Windows/Mac/Linux: <a href="https://tailscale.com/download">https://tailscale.com/download</a></li>
    </ul>
  </div>
  <div class="card">
    <h2>2. Tailscale 로그인</h2>
    <ul>
      <li>Tailscale 앱을 열고 로그인합니다.</li>
      <li>공유를 받을 이메일 계정으로 로그인해야 합니다.</li>
    </ul>
  </div>
  <div class="card">
    <h2>3. 접속 주소</h2>
    <ul>
      <li>Tailscale IP 주소: <code>{html.escape(ip_url)}</code></li>
      <li>MagicDNS 주소: <code>{html.escape(dns_url)}</code></li>
    </ul>
  </div>
  <div class="card">
    <h2>4. 접속이 안 될 때 확인할 것</h2>
    <ul>
      <li>Tailscale 앱이 켜져 있는지 확인합니다.</li>
      <li>Tailscale 로그인 상태인지 확인합니다.</li>
      <li>공유 승인이 완료됐는지 확인합니다.</li>
      <li>위 두 주소 중 하나를 다시 열어봅니다.</li>
    </ul>
  </div>
</body>
</html>
"""
    ACCESS_GUIDE_HTML_PATH.write_text(html_body, encoding="utf-8")
    return {"markdown_path": str(ACCESS_GUIDE_MD_PATH), "html_path": str(ACCESS_GUIDE_HTML_PATH), "ip_url": ip_url, "dns_url": dns_url}

try:
    from zoneinfo import ZoneInfo  # type: ignore

    SEOUL_TZ = ZoneInfo("Asia/Seoul")
except Exception:
    SEOUL_TZ = timezone(timedelta(hours=9))
TARGET_LABELS = {
    "fwd_ret_20d": "공시후 20일 수익률",
    "fwd_ret_60d": "공시후 60일 수익률",
    "fwd_ret_90d": "공시후 90일 수익률",
    "period_ret": "분기 수익률",
}
FAMILY_LABELS = {
    "freshness": "공시 신선도",
    "stability_rank": "실적 안정성",
    "combo": "복합 조건",
    "profitability": "수익성",
    "timing": "타이밍",
    "quality": "품질",
    "risk": "리스크",
    "growth": "성장성",
    "durability": "지속성",
    "macro": "매크로",
    "profitability_rank": "수익성 순위",
    "growth_rank": "성장성 순위",
    "durability_rank": "지속성 순위",
}
CONDITION_LABELS = {
    "core_candidate": "코어 후보",
    "fresh_filing_30d": "최근 30일 공시",
    "fresh_filing_60d": "최근 60일 공시",
    "op_income_positive": "영업이익 흑자",
    "net_income_positive": "순이익 흑자",
    "op_margin_positive": "영업이익률 양수",
    "quality_gate_ok": "품질 게이트 통과",
    "timing_ok": "타이밍 게이트 통과",
    "qoq_positive_combo": "영업·순이익 QoQ 동시 개선",
    "ttm_positive_combo": "최근 4Q 영업·순이익 합계 양수",
    "net_margin_positive": "순이익률 양수",
    "op_income_qoq_positive": "영업이익 QoQ 증가",
    "net_income_qoq_positive": "순이익 QoQ 증가",
    "op_income_qoq_accel_positive": "영업이익 QoQ 가속",
    "net_income_qoq_accel_positive": "순이익 QoQ 가속",
    "op_income_ttm_positive": "최근 4Q 영업이익 양수",
    "net_income_ttm_positive": "최근 4Q 순이익 양수",
    "low_gap_ratio": "순이익·영업이익 괴리 낮음",
    "macro_gate_ok": "매크로 게이트 통과",
    "risk_on_neutral": "중립 이상 노출 환경",
    "op_margin_top30": "영업이익률 상위 30%",
    "net_margin_top30": "순이익률 상위 30%",
    "op_income_qoq_top30": "영업이익 QoQ 상위 30%",
    "net_income_qoq_top30": "순이익 QoQ 상위 30%",
    "op_income_ttm_top30": "최근 4Q 영업이익 상위 30%",
    "net_income_ttm_top30": "최근 4Q 순이익 상위 30%",
    "op_income_vol_low30": "영업이익 변동성 하위 30%",
    "net_income_vol_low30": "순이익 변동성 하위 30%",
    "profit_quality_combo": "수익성·품질 복합",
    "growth_combo": "성장성 복합",
    "quality_growth_combo": "품질·성장 복합",
    "fresh_profit_combo": "신선도·수익성 복합",
}
RULE_EXPR_LABELS = {
    "days_since_filing": "공시 경과일",
    "op_margin_pti": "영업이익률(PTI)",
    "net_margin_pti": "순이익률(PTI)",
    "op_income_q_vol_4q": "최근 4분기 영업이익 변동성",
    "net_income_q_vol_4q": "최근 4분기 순이익 변동성",
    "revenue_q_ttm": "최근 4분기 매출 합계",
    "op_income_q_ttm": "최근 4분기 영업이익 합계",
    "net_income_q_ttm": "최근 4분기 당기순이익 합계",
    "period_kospi_ret": "분기 KOSPI 수익률",
    "gold_kr_close": "국내 금 가격",
    "vix": "VIX",
    "usdkrw": "USD/KRW",
    "us10y": "미국 10년 금리",
    "kr10y": "한국 10년 금리",
}


def inject_base_css() -> None:
    st.markdown(
        """
<style>
.block-container {padding-top: 0.85rem; padding-bottom: 1.25rem;}
[data-testid="stAppViewBlockContainer"] {padding-top: 0.85rem;}
[data-testid="stSidebar"] [data-testid="stMetric"] {
    min-height: 92px;
    padding: 8px 10px;
}
[data-testid="stMetric"] {
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 10px 14px;
    min-height: 108px;
}
[data-testid="stMetricLabel"] {font-size: 0.95rem !important;}
[data-testid="stMetricValue"] {
    font-size: 1.42rem !important;
    line-height: 1.18 !important;
    white-space: normal !important;
    word-break: keep-all !important;
}
.ns-card {
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 10px 12px;
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    min-height: 96px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    gap: 4px;
}
.ns-card-label {
    font-size: 0.83rem;
    color: #475569;
    margin-bottom: 0;
    font-weight: 600;
}
.ns-card-value {
    font-size: 0.98rem;
    line-height: 1.22;
    font-weight: 700;
    color: #111827;
    white-space: normal;
    word-break: keep-all;
    overflow-wrap: anywhere;
}
.ns-card-caption {
    font-size: 0.76rem;
    line-height: 1.22;
    color: #475569;
    margin-top: 0;
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
}
.ns-decision-item {
    font-size: 0.93rem;
    line-height: 1.2;
    font-weight: 500;
    color: #64748b;
}
.ns-decision-item.active {
    font-weight: 700;
    color: #111827;
}
.ns-decision-item.inactive {
    font-weight: 500;
    color: #94a3b8;
}
.ns-mini-card {
    border: 1px solid #dbe3f0;
    border-radius: 14px;
    padding: 10px 12px;
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    min-height: 0;
}
.ns-mini-card.price {
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}
.ns-mini-label {
    font-size: 0.78rem;
    color: #64748b;
    font-weight: 700;
    margin-bottom: 4px;
}
.ns-mini-value {
    font-size: 1.05rem;
    line-height: 1.18;
    font-weight: 800;
    color: #0f172a;
    word-break: keep-all;
}
.ns-mini-caption {
    font-size: 0.76rem;
    line-height: 1.28;
    color: #64748b;
    margin-top: 4px;
}
.ns-axis-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 0.15rem;
}
.ns-axis-card {
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 8px 10px;
    background: #ffffff;
    min-height: 0;
}
.ns-axis-title {
    font-size: 0.88rem;
    line-height: 1.1;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 5px;
}
.ns-axis-line {
    font-size: 0.82rem;
    line-height: 1.22;
    color: #0f172a;
    margin: 0;
}
.ns-axis-line + .ns-axis-line {
    margin-top: 3px;
}
.ns-axis-line.subtle {
    color: #64748b;
}
.ns-guide-card {
    border: 1px solid #dbe3f0;
    border-radius: 12px;
    padding: 9px 10px;
    background: linear-gradient(180deg, #fffdf5 0%, #fff7ed 100%);
    margin-top: 0.1rem;
}
.ns-guide-title {
    font-size: 0.82rem;
    line-height: 1.1;
    font-weight: 800;
    color: #9a3412;
    margin-bottom: 4px;
}
.ns-guide-line {
    font-size: 0.82rem;
    line-height: 1.28;
    color: #7c2d12;
    margin: 0;
}
.ns-guide-line + .ns-guide-line {
    margin-top: 3px;
}
.ns-status-card {
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 10px 12px;
    margin: 0.35rem 0 0.15rem 0;
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
}
.ns-status-card.idle {
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
}
.ns-status-card.running {
    background: linear-gradient(180deg, #effcf6 0%, #dcfce7 100%);
    border-color: #bbf7d0;
}
.ns-status-card.failed {
    background: linear-gradient(180deg, #fff7ed 0%, #ffedd5 100%);
    border-color: #fdba74;
}
.ns-status-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 6px;
}
.ns-status-label {
    font-size: 0.77rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #64748b;
}
.ns-status-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    border: 1px solid #cbd5e1;
    color: #334155;
    background: #ffffff;
}
.ns-status-pill.running {
    color: #166534;
    border-color: #86efac;
    background: #f0fdf4;
}
.ns-status-pill.failed {
    color: #9a3412;
    border-color: #fdba74;
    background: #fff7ed;
}
.ns-status-action {
    font-size: 1rem;
    line-height: 1.25;
    font-weight: 800;
    color: #0f172a;
    margin: 0;
    word-break: keep-all;
}
.ns-status-caption {
    margin-top: 4px;
    font-size: 0.78rem;
    line-height: 1.35;
    color: #475569;
    word-break: keep-all;
}
.ns-badge {
    display:inline-block;
    padding:6px 10px;
    border-radius:999px;
    background:#eff6ff;
    color:#1d4ed8;
    border:1px solid #bfdbfe;
    font-size:0.9rem;
    margin-right:8px;
}
.ns-subtle {
    color:#475569;
    font-size:0.95rem;
}
.ns-page-hero {
    margin: 0.10rem 0 0.75rem 0;
}
.ns-page-kicker {
    display: inline-block;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 0.28rem;
}
.ns-page-title {
    font-size: clamp(2rem, 3.6vw, 3.15rem);
    line-height: 1.12;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: #0f172a;
    margin: 0;
    word-break: keep-all;
    padding-top: 0.06em;
    overflow: visible;
}
.ns-page-subtitle {
    margin-top: 0.34rem;
    color: #475569;
    font-size: 0.98rem;
    line-height: 1.45;
}
[data-testid="stHeadingWithActionElements"] h1,
[data-testid="stHeadingWithActionElements"] h2,
[data-testid="stHeadingWithActionElements"] h3 {
    line-height: 1.16 !important;
    padding-top: 0.06em;
    overflow: visible;
}
.ns-section-divider {
    border-bottom: 1px solid #dbe3f0;
    margin: 0.55rem 0 0.70rem 0;
}
.ns-section-label {
    font-size: 0.80rem;
    font-weight: 700;
    color: #64748b;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    margin: 0.10rem 0 0.15rem 0;
}
.ns-tight-divider {
    border-bottom: 1px solid #e5e7eb;
    margin: 0.40rem 0 0.55rem 0;
}
[data-testid="stSidebar"] .ns-sidebar-title {
    font-size: 0.98rem;
    font-weight: 800;
    line-height: 1.2;
    color: #0f172a;
    margin: 0.18rem 0 0.34rem 0;
}
[data-testid="stSidebar"] .ns-sidebar-section-title {
    font-size: 0.78rem;
    font-weight: 700;
    line-height: 1.2;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: #64748b;
    margin: 0.62rem 0 0.22rem 0;
}
[data-testid="stSidebar"] .ns-sidebar-divider {
    border-bottom: 1px solid #dbe3f0;
    margin: 0.34rem 0 0.46rem 0;
}
[data-testid="stSidebar"] [data-testid="stRadio"] {
    margin: 0.04rem 0 0.42rem 0;
}
[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 0.12rem;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] ul {
    margin: 0.02rem 0 0.14rem 0.90rem;
    padding-left: 0.1rem;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li {
    margin: 0.10rem 0;
}
[data-testid="stSidebar"] .stButton {
    margin: 0.18rem 0 0 0;
}
[data-testid="stSidebar"] .stCaptionContainer,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    margin-top: 0.20rem;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    margin: 0.10rem 0;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
    margin: 0.18rem 0 0.22rem 0;
}
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] {
    padding-top: 0.06rem;
}
[data-testid="stSidebar"] [data-testid="stExpander"] details summary {
    padding-top: 0.10rem;
    padding-bottom: 0.10rem;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {
    gap: 0.10rem;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_live_clock(key: str, *, compact: bool = False) -> None:
    height = 74 if compact else 82
    padding = "10px 12px" if compact else "12px 16px"
    font_size = "0.98rem" if compact else "1.05rem"
    components.html(
        f"""
<div style="border:1px solid #e5e7eb;border-radius:14px;padding:{padding};background:linear-gradient(180deg,#f8fafc 0%,#eef2ff 100%);">
  <div style="font-size:0.82rem;color:#475569;margin-bottom:4px;">대한민국 표준시 실시간 시계</div>
  <div id="{key}" style="font-weight:700;font-size:{font_size};color:#111827;">로딩 중...</div>
</div>
<script>
const el = document.getElementById("{key}");
function tick_{key.replace('-', '_')}() {{
  const now = new Date();
  const fmt = new Intl.DateTimeFormat("ko-KR", {{
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }});
  el.textContent = fmt.format(now);
}}
tick_{key.replace('-', '_')}();
setInterval(tick_{key.replace('-', '_')}, 1000);
</script>
        """,
        height=height,
    )


def render_page_heading(title: str, *, kicker: str | None = None, subtitle: str | None = None) -> None:
    kicker_html = f"<div class='ns-page-kicker'>{html.escape(kicker)}</div>" if kicker else ""
    subtitle_html = f"<div class='ns-page-subtitle'>{html.escape(subtitle)}</div>" if subtitle else ""
    st.markdown(
        (
            "<div class='ns-page-hero'>"
            f"{kicker_html}"
            f"<h1 class='ns-page-title'>{html.escape(title)}</h1>"
            f"{subtitle_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _file_mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


def _file_stamp(path: Path) -> tuple[int, int]:
    if not path.exists():
        return (0, 0)
    stat = path.stat()
    return (int(stat.st_mtime_ns), int(stat.st_size))


def build_version_tokens() -> dict[str, Any]:
    return {
        "output": (
            _file_mtime(SIGNAL_FAST_LATEST_PATH),
            _file_mtime(SIGNAL_LATEST_PATH),
            _file_mtime(DECISION_FAST_LATEST_PATH),
            _file_mtime(DECISION_DAILY_PATH),
            _file_mtime(HEALTH_PATH),
            _file_mtime(EVAL_PATH),
            _file_mtime(RESEARCH_PATH),
            _file_mtime(RESEARCH_INDUSTRY_PATH),
            _file_mtime(RULE_TOP_PATH),
            _file_mtime(RULE_INDUSTRY_PATH),
            _file_mtime(V2_SIM_SUMMARY_PATH),
            _file_mtime(STRATEGY_META_PATH),
            _file_mtime(REFRESH_META_PATH),
            _file_mtime(FAST_ALERT_META_PATH),
            _file_mtime(SCHEDULE_STATE_PATH),
            _file_mtime(LIVE_QUOTES_PATH),
            _file_mtime(MANUAL_POSITIONS_PATH),
            _file_mtime(MANUAL_TRADES_PATH),
        ),
        "macro": _file_mtime(MACRO_DAILY_PATH),
        "fundamental": _file_mtime(FUNDAMENTAL_PATH),
        "price": _file_mtime(PRICE_PANEL_PATH),
        "optimal_ma": (
            _file_mtime(PRICE_PANEL_PATH),
            _file_mtime(OPTIMAL_MA_SELECTION_PATH),
            _file_mtime(OPTIMAL_MA_ALL_SELECTION_PATH),
            _file_mtime(OPTIMAL_MA_SNAPSHOT_PATH),
        ),
    }


@st.cache_data(show_spinner=False)
def load_latest_data_dates(_price_meta_token: Any, _feature_meta_token: Any, _macro_token: Any, _fundamental_token: Any) -> dict[str, str]:
    result = {"price_latest": "-", "feature_latest": "-", "macro_latest": "-", "fundamental_latest": "-"}
    price_meta = data_path("price_panel_meta.json")
    if price_meta.exists():
        try:
            payload = json.loads(price_meta.read_text(encoding="utf-8"))
            result["price_latest"] = str(payload.get("bounds", {}).get("date_max") or "-")
        except Exception:
            pass
    if result["price_latest"] == "-" and PRICE_PANEL_PATH.exists():
        try:
            price = pd.read_csv(PRICE_PANEL_PATH, usecols=["date"], low_memory=False)
            price_dates = pd.to_datetime(price["date"], errors="coerce").dropna()
            if not price_dates.empty:
                result["price_latest"] = str(price_dates.max().date())
        except Exception:
            pass
    feature_meta = data_path("feature_daily_meta.json")
    if feature_meta.exists():
        try:
            payload = json.loads(feature_meta.read_text(encoding="utf-8"))
            result["feature_latest"] = str(payload.get("bounds", {}).get("date_max") or "-")
        except Exception:
            pass
    feature_csv = data_path("feature_daily.csv")
    if result["feature_latest"] == "-" and feature_csv.exists():
        try:
            feat = pd.read_csv(feature_csv, usecols=["date"], low_memory=False)
            feat_dates = pd.to_datetime(feat["date"], errors="coerce").dropna()
            if not feat_dates.empty:
                result["feature_latest"] = str(feat_dates.max().date())
        except Exception:
            pass
    if MACRO_DAILY_PATH.exists():
        try:
            macro = pd.read_csv(MACRO_DAILY_PATH, usecols=["date"], low_memory=False)
            macro_dates = pd.to_datetime(macro["date"], errors="coerce").dropna()
            if not macro_dates.empty:
                result["macro_latest"] = str(macro_dates.max().date())
        except Exception:
            pass
    if FUNDAMENTAL_PATH.exists():
        try:
            fund = pd.read_csv(FUNDAMENTAL_PATH, usecols=["공시일"], low_memory=False)
            fund_dates = pd.to_datetime(fund["공시일"], errors="coerce").dropna()
            if not fund_dates.empty:
                result["fundamental_latest"] = str(fund_dates.max().date())
        except Exception:
            pass
    return result


def runtime_latest_dates(data: dict[str, Any]) -> dict[str, str]:
    refresh_meta = data.get("refresh_meta", {}) or {}
    fallback = load_latest_data_dates(
        _file_stamp(data_path("price_panel_meta.json")),
        _file_stamp(data_path("feature_daily_meta.json")),
        data["version_tokens"]["macro"],
        data["version_tokens"]["fundamental"],
    )
    price_latest = (
        refresh_meta.get("price_date_max")
        or refresh_meta.get("latest_price_date")
        or refresh_meta.get("price_panel", {}).get("price_bounds", {}).get("date_max")
        or fallback.get("price_latest", "-")
    )
    feature_latest = (
        refresh_meta.get("feature_date_max")
        or refresh_meta.get("feature", {}).get("feature_bounds", {}).get("date_max")
        or fallback.get("feature_latest", "-")
    )
    macro_latest = (
        refresh_meta.get("macro", {}).get("macro_bounds", {}).get("date_max")
        or fallback.get("macro_latest", "-")
    )
    fundamental_latest = fallback.get("fundamental_latest", "-")
    return {
        "price_latest": str(price_latest or "-"),
        "feature_latest": str(feature_latest or "-"),
        "macro_latest": str(macro_latest or "-"),
        "fundamental_latest": str(fundamental_latest or "-"),
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return default if pd.isna(value) else float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return default if pd.isna(value) else int(float(value))
    except Exception:
        return default


def _format_large_number(value: Any) -> str:
    number = _safe_float(value, float("nan"))
    if pd.isna(number):
        return "-"
    abs_number = abs(number)
    if abs_number >= 1_0000_0000_0000:
        return f"{number / 1_0000_0000_0000:.2f}조"
    if abs_number >= 1_0000_0000:
        return f"{number / 1_0000_0000:.1f}억"
    return f"{number:,.0f}"


def _clip_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _optimal_ma_alignment_text(signal: Any, optimal_ma_ok: Any) -> str:
    return optimal_ma_alignment(signal, optimal_ma_ok)


def _optimal_ma_delta_text(delta: float) -> str:
    if abs(delta) < 1e-12:
        return "0.000"
    return f"{delta:+.3f}"


def _optimal_ma_compact_text(row: pd.Series) -> str:
    timeframe = str(row.get("optimal_ma_timeframe_ko") or "-")
    window = _safe_int(row.get("optimal_ma_window"), 0)
    alignment = str(row.get("optimal_ma_alignment") or "없음")
    line_price = _format_large_number(row.get("optimal_ma_line_price"))
    if timeframe == "-" or window <= 0:
        return "없음"
    return f"{timeframe}{window}<br>{alignment}<br>{line_price}원"


def _optimal_ma_detail_text(row: pd.Series) -> str:
    timeframe = str(row.get("optimal_ma_timeframe_ko") or "-")
    action_mode = str(row.get("optimal_ma_action_mode_ko") or "-")
    window = _safe_int(row.get("optimal_ma_window"), 0)
    alignment = str(row.get("optimal_ma_alignment") or "없음")
    delta = _optimal_ma_delta_text(_safe_float(row.get("optimal_ma_soft_delta"), 0.0))
    line_price = _format_large_number(row.get("optimal_ma_line_price"))
    basis_label = str(row.get("optimal_ma_basis_label") or "-")
    basis_price = _format_large_number(row.get("optimal_ma_basis_price"))
    rule_text = str(row.get("optimal_ma_rule_text") or "없음")
    if timeframe == "-" or window <= 0:
        return "없음"
    return (
        f"{timeframe} {window}이평 · {action_mode}<br>"
        f"상태 {alignment} ({delta})<br>"
        f"판정가 {basis_label} {basis_price}원<br>"
        f"기준선 {line_price}원<br>"
        f"{html.escape(rule_text)}"
    )


def _quarter_label(year: Any, reprt_code: Any) -> str:
    mapping = {"11013": "1Q", "11012": "2Q", "11014": "3Q", "11011": "4Q"}
    return f"{year}-{mapping.get(str(reprt_code), str(reprt_code))}"


def _translate_target(value: Any) -> str:
    text = str(value)
    return TARGET_LABELS.get(text, text)


def _translate_family(value: Any) -> str:
    text = str(value)
    return FAMILY_LABELS.get(text, text)


def _translate_condition(value: Any) -> str:
    text = str(value)
    return CONDITION_LABELS.get(text, text)


def _translate_rule_expr(expr: Any) -> str:
    text = str(expr)
    for src, dst in RULE_EXPR_LABELS.items():
        text = text.replace(src, dst)
    text = text.replace(" and ", " 그리고 ")
    text = text.replace(" or ", " 또는 ")
    text = text.replace("daily p30", "일별 30백분위")
    text = text.replace("daily p70", "일별 70백분위")
    text = text.replace("daily p50", "일별 50백분위")
    return text


def prettify_rule_candidates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "target" in out.columns:
        out["target"] = out["target"].map(_translate_target)
    if "condition_family" in out.columns:
        out["condition_family"] = out["condition_family"].map(_translate_family)
    if "condition" in out.columns:
        out["condition"] = out["condition"].map(_translate_condition)
    if "rule_expr" in out.columns:
        out["rule_expr"] = out["rule_expr"].map(_translate_rule_expr)
    rename_map = {
        "group": "업종",
        "condition_family": "조건군",
        "condition": "조건ID",
        "rule_expr": "규칙식",
        "target": "평가구간",
        "selected_obs": "충족표본수",
        "rejected_obs": "비충족표본수",
        "selected_mean": "충족평균수익률",
        "rejected_mean": "비충족평균수익률",
        "mean_diff": "평균수익률차이",
        "selected_win_rate": "충족승률",
        "rejected_win_rate": "비충족승률",
        "win_rate_diff": "승률차이",
        "support": "충족비중",
        "score": "우선점수",
    }
    return out.rename(columns=rename_map)


def prettify_condition_perf(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "target" in out.columns:
        out["target"] = out["target"].map(_translate_target)
    if "condition" in out.columns:
        out["condition"] = out["condition"].map(_translate_condition)
    rename_map = {
        "group": "업종",
        "condition": "조건ID",
        "target": "평가구간",
        "selected_obs": "충족표본수",
        "rejected_obs": "비충족표본수",
        "selected_mean": "충족평균수익률",
        "rejected_mean": "비충족평균수익률",
        "mean_diff": "평균수익률차이",
        "selected_win_rate": "충족승률",
        "rejected_win_rate": "비충족승률",
        "win_rate_diff": "승률차이",
    }
    return out.rename(columns=rename_map)


def prettify_v2_sim_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    family_map = {
        "month_end_vs_weekly_early_cap": "월말 vs 주말선집행(월1회)",
        "monthly_buy_weekly_sell": "월봉매수 / 주봉매도",
        "week_close_lead": "주기준(주종가) 선행매수·선행매도",
        "week_daily_lead": "주기준(매일종가) 선행매수·선행매도",
    }
    out["experiment_family"] = out["experiment_family"].map(lambda x: family_map.get(str(x), str(x)))
    rename_map = {
        "experiment_family": "실험군",
        "variant": "변수조합",
        "stock_count": "종목수",
        "avg_total_return": "평균누적수익률",
        "median_total_return": "중앙누적수익률",
        "avg_annualized_return": "평균연환산수익률",
        "avg_max_drawdown": "평균MDD",
        "avg_trade_count": "평균거래횟수",
    }
    return out.rename(columns=rename_map)


@st.cache_data(show_spinner=False)
def load_output_data(_version_token: Any) -> dict[str, Any]:
    def latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "date" not in df.columns:
            return df
        dates = pd.to_datetime(df["date"], errors="coerce")
        if dates.dropna().empty:
            return df
        latest_date = dates.max()
        return df[dates == latest_date].copy().reset_index(drop=True)

    signal_fast = _read_csv(SIGNAL_FAST_LATEST_PATH)
    signal_latest_file = _read_csv(SIGNAL_LATEST_PATH)
    signal_full_history = _read_csv(SIGNAL_DAILY_PATH)
    signal_full = latest_snapshot(signal_full_history)
    decision_fast = _read_csv(DECISION_FAST_LATEST_PATH)
    decision_full = latest_snapshot(_read_csv(DECISION_DAILY_PATH))
    return {
        "signals": signal_full if not signal_full.empty else (signal_latest_file if not signal_latest_file.empty else signal_fast),
        "signals_fast": signal_fast,
        "decision": decision_full.tail(1) if not decision_full.empty else decision_fast,
        "decision_fast": decision_fast,
        "health": _read_csv(HEALTH_PATH),
        "eval": _read_csv(EVAL_PATH),
        "research": _read_csv(RESEARCH_PATH),
        "research_industry": _read_csv(RESEARCH_INDUSTRY_PATH),
        "rule_top": _read_csv(RULE_TOP_PATH),
        "rule_industry": _read_csv(RULE_INDUSTRY_PATH),
        "v2_sim": _read_csv(V2_SIM_SUMMARY_PATH),
        "meta": _read_json(STRATEGY_META_PATH),
        "refresh_meta": _read_json(REFRESH_META_PATH),
        "fast_meta": _read_json(FAST_ALERT_META_PATH),
        "schedule_state": _read_json(SCHEDULE_STATE_PATH),
        "live_quotes": _read_csv(LIVE_QUOTES_PATH),
    }


@st.cache_data(show_spinner=False)
def load_signal_timing_audit(_output_token: Any, _price_token: Any) -> pd.DataFrame:
    if not SIGNAL_DAILY_PATH.exists() or not PRICE_PANEL_PATH.exists():
        return pd.DataFrame()
    signal_df = _read_csv(SIGNAL_DAILY_PATH)
    if signal_df.empty:
        return pd.DataFrame()
    signal_df = signal_df[signal_df["signal"].isin(["BUY", "SELL"])].copy()
    if signal_df.empty:
        return pd.DataFrame()
    signal_df["code"] = signal_df["code"].astype(str).str.zfill(6)
    signal_df["date"] = pd.to_datetime(signal_df["date"], errors="coerce")
    signal_df = signal_df.dropna(subset=["date"])

    price_df = pd.read_csv(PRICE_PANEL_PATH, usecols=["date", "code", "close"], dtype={"code": str}, low_memory=False)
    price_df["code"] = price_df["code"].astype(str).str.zfill(6)
    price_df["date"] = pd.to_datetime(price_df["date"], errors="coerce")
    price_df = price_df.dropna(subset=["date"]).sort_values(["code", "date"])
    grp = price_df.groupby("code", sort=False)
    price_df["close_0d"] = price_df["close"]
    price_df["close_1d"] = grp["close"].shift(-1)
    price_df["close_7d"] = grp["close"].shift(-7)

    merged = signal_df.merge(price_df[["date", "code", "close_0d", "close_1d", "close_7d"]], on=["date", "code"], how="left")
    rows: list[dict[str, Any]] = []
    for signal in ["BUY", "SELL"]:
        subset = merged[merged["signal"] == signal].copy()
        if subset.empty:
            continue
        for horizon, col in [("당일종가", "close_0d"), ("1일후", "close_1d"), ("7일후", "close_7d")]:
            valid = subset.dropna(subset=["close_0d", col]).copy()
            if valid.empty:
                continue
            ret = valid[col] / valid["close_0d"] - 1.0
            if signal == "BUY":
                hit = ret > 0
            else:
                hit = ret < 0
            rows.append(
                {
                    "신호": "매수" if signal == "BUY" else "매도",
                    "평가시점": horizon,
                    "표본수": int(len(valid)),
                    "평균수익률": float(ret.mean()),
                    "중앙값수익률": float(ret.median()),
                    "적중률": float(hit.mean()),
                    "해석": "매수 후 상승" if signal == "BUY" else "매도 후 하락",
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    signal_order = {"매수": 0, "매도": 1}
    horizon_order = {"당일종가": 0, "1일후": 1, "7일후": 2}
    out["_signal_order"] = out["신호"].map(signal_order).fillna(99)
    out["_horizon_order"] = out["평가시점"].map(horizon_order).fillna(99)
    return out.sort_values(["_signal_order", "_horizon_order"]).drop(columns=["_signal_order", "_horizon_order"]).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_feature_latest_snapshot(_output_token: Any) -> pd.DataFrame:
    path = APP_DIR / "feature_latest_snapshot.csv"
    feature_path = data_path("feature_daily.pkl")
    if not path.exists():
        return pd.DataFrame()
    if feature_path.exists() and path.stat().st_mtime < feature_path.stat().st_mtime:
        try:
            df = pd.read_pickle(feature_path)
            if df.empty:
                return df
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date"]).sort_values(["code", "date"])
            latest = df.groupby("code", as_index=False).tail(1).copy()
            latest["code"] = latest["code"].astype(str).str.zfill(6)
            latest.to_pickle(path)
            return latest
        except Exception:
            return pd.DataFrame()
    try:
        df = pd.read_pickle(path)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


@st.cache_data(show_spinner=False)
def load_price_latest_snapshot(_price_token: Any) -> pd.DataFrame:
    snapshot_path = APP_DIR / "price_panel_latest_snapshot.csv"
    if snapshot_path.exists() and (not PRICE_PANEL_PATH.exists() or snapshot_path.stat().st_mtime >= PRICE_PANEL_PATH.stat().st_mtime):
        df = pd.read_csv(snapshot_path, dtype={"code": str}, low_memory=False)
        if df.empty:
            return df
        df["code"] = df["code"].astype(str).str.zfill(6)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    if not PRICE_PANEL_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(PRICE_PANEL_PATH, usecols=["date", "code", "name", "close", "volume", "market_cap", "industry"], dtype={"code": str}, low_memory=False)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["code", "date"])
    latest = df.groupby("code", as_index=False).tail(1).copy()
    try:
        latest.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
    except Exception:
        pass
    return latest


@st.cache_data(show_spinner=False)
def load_manual_positions_snapshot(_output_token: Any) -> pd.DataFrame:
    if not MANUAL_POSITIONS_PATH.exists():
        return pd.DataFrame(columns=["chat_id", "code", "name", "quantity", "avg_price"])
    df = pd.read_csv(MANUAL_POSITIONS_PATH, dtype={"chat_id": str, "code": str}, low_memory=False)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.upper()
    df["code"] = df["code"].where(~df["code"].str.fullmatch(r"\d+"), df["code"].str.zfill(6))
    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0.0)
    if "avg_price" in df.columns:
        df["avg_price"] = pd.to_numeric(df["avg_price"], errors="coerce")
    df = df[~df["chat_id"].astype(str).str.contains("_test", na=False)].copy()
    df = df[df["quantity"] > 0].copy()
    return df.sort_values(["code", "chat_id"]).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_optimal_ma_latest_snapshot(_optimal_ma_token: Any) -> pd.DataFrame:
    df = _load_latest_optimal_ma_snapshot()
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


@st.cache_data(show_spinner=False)
def load_optimal_ma_chart_selection(_optimal_ma_token: Any) -> pd.DataFrame:
    if not OPTIMAL_MA_ALL_SELECTION_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(OPTIMAL_MA_ALL_SELECTION_PATH, dtype={"code": str}, low_memory=False)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["ma_timeframe"] = df["ma_timeframe"].astype(str).str.lower()
    return df


def format_quarter_label(fiscal_year: Any, reprt_code: Any) -> str:
    if pd.isna(fiscal_year) or pd.isna(reprt_code):
        return "-"
    quarter_map = {"11013": "1Q", "11012": "2Q", "11014": "3Q", "11011": "4Q"}
    try:
        year_text = str(int(float(fiscal_year)))
    except Exception:
        year_text = str(fiscal_year)
    return f"{year_text}-{quarter_map.get(str(reprt_code), str(reprt_code))}"


def next_business_day(date_value: Any) -> str:
    dt = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(dt):
        return "-"
    current = dt
    while True:
        current = current + pd.Timedelta(days=1)
        if current.weekday() < 5:
            return str(current.date())


def format_eod_basis(date_value: Any) -> str:
    dt = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(dt):
        return "-"
    return f"{dt.date()}T16:00:00 종가"


def build_service_status(data: dict[str, Any]) -> list[str]:
    streamlit_on = _python_process_running("streamlit run", "streamlit_app.py")
    bridge_on = _python_process_running("new_strategy.telegram_bridge_service")
    schedule_on = _python_process_running("new_strategy.run_market_schedule_service")
    return [
        f"- 스트림릿: {'ON' if streamlit_on else 'OFF'}",
        f"- 텔레그램 브리지: {'ON' if bridge_on else 'OFF'}",
        f"- 시장 스케줄: {'ON' if schedule_on else 'OFF'}",
    ]


def build_compact_price_guide(
    row: pd.Series,
    *,
    latest_price: pd.DataFrame,
    manual_positions: pd.DataFrame,
    fast_state: pd.DataFrame,
) -> tuple[str, str]:
    code = str(row.get("code", "")).zfill(6)
    q = latest_price[latest_price["code"].astype(str).str.zfill(6) == code]
    if q.empty:
        return "-", "-"
    qrow = q.iloc[-1]
    basis_price = _safe_float(qrow.get("close"), float("nan"))
    if pd.isna(basis_price):
        return "-", "-"
    basis = format_eod_basis(qrow.get("date"))

    basis_text = f"{basis_price:,.0f}원"
    signal = str(row.get("display_signal") or row.get("signal") or "").upper()
    pos = manual_positions[manual_positions["code"].astype(str).str.zfill(6) == code] if not manual_positions.empty else pd.DataFrame()
    if pos.empty and not fast_state.empty:
        pos = fast_state[fast_state["code"].astype(str).str.zfill(6) == code]
    entry_price = None
    if not pos.empty:
        if "avg_price" in pos.columns and pd.notna(pos.iloc[-1].get("avg_price")):
            entry_price = float(pos.iloc[-1]["avg_price"])
        elif pd.notna(pos.iloc[-1].get("entry_price")):
            entry_price = float(pos.iloc[-1]["entry_price"])
    levels = compute_risk_levels(row, current_price=float(basis_price), entry_price=entry_price)

    if signal in {"BUY", "BUY_WATCH"}:
        parts = [
            f"관찰 {basis_price * 0.99:,.0f}~{basis_price * 1.01:,.0f}원",
            f"추격금지 {basis_price * 1.02:,.0f}원",
        ]
        if levels["initial_stop"] is not None:
            parts.append(f"초기손절 {levels['initial_stop']:,.0f}원")
        return basis_text, " / ".join(parts)

    parts = []
    if entry_price is not None:
        parts.append(f"진입 {entry_price:,.0f}원")
    if levels["initial_stop"] is not None:
        parts.append(f"초기손절 {levels['initial_stop']:,.0f}원")
    if levels["breakeven_guard"] is not None:
        parts.append(f"원금보호 {levels['breakeven_guard']:,.0f}원")
    if levels["effective_guard"] is not None:
        parts.append(f"유효방어 {levels['effective_guard']:,.0f}원")
    if not parts:
        parts.append("고정 가격 규칙 없음")
    return basis_text, " / ".join(parts)


def decision_price_header(view_df: pd.DataFrame) -> str:
    if view_df.empty or "가격 기준" not in view_df.columns:
        return "전일종가"
    values = [str(value).strip() for value in view_df["가격 기준"].astype(str).tolist() if str(value).strip() and str(value).strip() != "-"]
    if not values:
        return "전일종가"
    if all("(" not in value and ")" not in value for value in values):
        return "전일종가"
    basis_match = None
    for value in values:
        if "(" in value and ")" in value:
            inner = value.split("(", 1)[1].split(")", 1)[0].strip()
            if basis_match is None:
                basis_match = inner
            elif basis_match != inner:
                basis_match = None
                break
    if not basis_match:
        return "전일종가"
    if "T" in basis_match:
        basis_match = basis_match.replace("-", ".")
    return f"종가({basis_match})"


def render_decision_summary_table(view_df: pd.DataFrame) -> None:
    if view_df.empty:
        st.info("표시할 의사결정 종목이 없습니다.")
        return

    def plain_text(value: Any, *, break_paren: bool = False, slash_to_break: bool = False) -> str:
        text = str(value or "")
        if slash_to_break:
            text = text.replace(" / ", "\n")
        if break_paren:
            text = text.replace(" (", "\n(")
        return text

    def badge_html(label: str) -> str:
        palette = {
            "buy": ("#ecfdf5", "#065f46"),
            "sell": ("#fff1f2", "#9f1239"),
            "hold": ("#eff6ff", "#1d4ed8"),
            "watch": ("#fffbeb", "#92400e"),
        }
        bg, fg = palette.get(decision_cell_class(label), ("#f8fafc", "#334155"))
        return (
            f"<div style='background:{bg};color:{fg};font-weight:800;"
            "padding:0.38rem 0.36rem;border-radius:10px;text-align:center;"
            "line-height:1.12;border:1px solid #e5e7eb;white-space:normal;word-break:keep-all;font-size:0.82rem;"
            "display:flex;align-items:center;justify-content:center;min-height:58px;height:100%;'>"
            f"{html.escape(str(label))}</div>"
        )

    def compact_axis_block(value: Any, *, emphasize_first: bool = True) -> str:
        raw = str(value or "").replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
        parts = [part.strip() for part in raw.splitlines() if part.strip()]
        if not parts:
            return "-"
        first = html.escape(parts[0])
        if emphasize_first:
            first = f"<strong>{first}</strong>"
        if len(parts) == 1:
            return first
        rest = "<br>".join(html.escape(part) for part in parts[1:])
        return f"{first}<br><span class='ns-subtle-cell'>{rest}</span>"

    def compact_basis_block(row: pd.Series) -> str:
        close_val = pd.to_numeric(pd.Series([row.get("latest_close")]), errors="coerce").iloc[0]
        volume_val = pd.to_numeric(pd.Series([row.get("latest_volume")]), errors="coerce").iloc[0]
        close_text = "-" if pd.isna(close_val) else f"{float(close_val):,.0f}원"
        volume_text = "-" if pd.isna(volume_val) else f"{float(volume_val):,.0f}"
        return (
            "<div class='ns-basis-cell'>"
            f"<strong>종가 {html.escape(close_text)}</strong><br>"
            f"<span class='ns-subtle-cell'>거래량 {html.escape(volume_text)}</span>"
            "</div>"
        )

    headers = ["의사결정", "종목", "근거 기준", "최적 MA", "주가 위치", "재무", "매크로", "리스크", "실행 가이드"]
    col_widths = ["8%", "15%", "8%", "16%", "12%", "13%", "9%", "8%", "11%"]

    row_html_parts: list[str] = []
    estimated_height = 72
    for _, row in view_df.iterrows():
        decision_html = badge_html(str(row["의사결정"]))
        stock_html = (
            f"<span class='ns-stock-code'>{html.escape(str(row['종목코드']))}</span><br>"
            f"<span class='ns-stock-name'>{html.escape(str(row['종목명']))}</span><br>"
            f"<span class='ns-subtle-cell'>{html.escape(str(row['업종']))}</span>"
        )
        basis_html = compact_basis_block(row)
        optimal_ma_html = compact_axis_block(row["최적 MA"])
        price_axis_html = compact_axis_block(row["주가 위치"])
        financial_html = compact_axis_block(row["재무"])
        macro_html = compact_axis_block(row["매크로"])
        risk_html = compact_axis_block(prettify_risk_flag(row["리스크"]).replace(" · ", "\n"), emphasize_first=False)
        guide_html = compact_axis_block(row["실행 가이드"], emphasize_first=False)
        cells = [decision_html, stock_html, basis_html, optimal_ma_html, price_axis_html, financial_html, macro_html, risk_html, guide_html]
        row_html_parts.append(
            "<tr>"
            + f"<td class='decision-cell'>{cells[0]}</td>"
            + f"<td class='stock-cell'>{cells[1]}</td>"
            + "".join(f"<td>{cell}</td>" for cell in cells[2:])
            + "</tr>"
        )
        line_counts = [max(1, str(cell).count("<br>") + 1) for cell in cells[1:]]
        estimated_height += max(70, max(line_counts) * 18 + 22)

    table_html = f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        body {{
          margin: 0;
          font-family: 'Malgun Gothic', sans-serif;
          color: #0f172a;
          background: white;
        }}
        .ns-table-wrap {{
          margin: 0;
          padding: 0;
        }}
        table.ns-decision-table {{
          width: 100%;
          border-collapse: collapse;
          table-layout: fixed;
        }}
        table.ns-decision-table colgroup col:nth-child(1) {{ width: {col_widths[0]}; }}
        table.ns-decision-table colgroup col:nth-child(2) {{ width: {col_widths[1]}; }}
        table.ns-decision-table colgroup col:nth-child(3) {{ width: {col_widths[2]}; }}
        table.ns-decision-table colgroup col:nth-child(4) {{ width: {col_widths[3]}; }}
        table.ns-decision-table colgroup col:nth-child(5) {{ width: {col_widths[4]}; }}
        table.ns-decision-table colgroup col:nth-child(6) {{ width: {col_widths[5]}; }}
        table.ns-decision-table colgroup col:nth-child(7) {{ width: {col_widths[6]}; }}
        table.ns-decision-table colgroup col:nth-child(8) {{ width: {col_widths[7]}; }}
        table.ns-decision-table colgroup col:nth-child(9) {{ width: {col_widths[8]}; }}
        table.ns-decision-table thead th {{
          text-align: left;
          font-size: 14px;
          font-weight: 800;
          color: #0f172a;
          padding: 0 8px 8px 8px;
          border-bottom: 1px solid #dbe3f0;
          position: sticky;
          top: 0;
          z-index: 3;
          background: #ffffff;
          box-shadow: inset 0 -1px 0 #dbe3f0;
        }}
        table.ns-decision-table tbody td {{
          vertical-align: top;
          padding: 8px 8px;
          font-size: 13px;
          line-height: 1.34;
          word-break: keep-all;
          border-bottom: 1px solid #e5e7eb;
        }}
        table.ns-decision-table tbody td.decision-cell {{
          padding-top: 8px;
          padding-bottom: 8px;
        }}
        table.ns-decision-table tbody td:first-child {{
          padding-top: 8px;
        }}
        table.ns-decision-table tbody tr:last-child td {{
          border-bottom: 1px solid #e5e7eb;
        }}
        table.ns-decision-table thead th:nth-child(3),
        table.ns-decision-table thead th:nth-child(4),
        table.ns-decision-table thead th:nth-child(5) {{
          padding-right: 6px;
        }}
        table.ns-decision-table tbody td:nth-child(3),
        table.ns-decision-table tbody td:nth-child(4),
        table.ns-decision-table tbody td:nth-child(5) {{
          font-size: 12.5px;
          padding-left: 6px;
          padding-right: 6px;
        }}
        table.ns-decision-table tbody td:nth-child(7),
        table.ns-decision-table tbody td:nth-child(9) {{
          line-height: 1.4;
        }}
        .ns-subtle-cell {{
          color: #64748b;
          font-size: 11.5px;
        }}
        .stock-cell {{
          word-break: normal !important;
          overflow-wrap: anywhere;
          hyphens: auto;
        }}
        .ns-basis-cell,
        .ns-ma-cell {{
          line-height: 1.28;
        }}
        .ns-price-cell {{
          white-space: nowrap;
          line-height: 1.2;
        }}
        .ns-ma-ok {{
          color: #065f46;
          font-size: 12px;
          font-weight: 700;
        }}
        .ns-ma-warn {{
          color: #b45309;
          font-size: 12px;
          font-weight: 700;
        }}
        .ns-stock-code {{
          display: inline-block;
          font-size: 13px;
          font-weight: 700;
          color: #0f172a;
          margin-bottom: 2px;
        }}
        .ns-stock-name {{
          display: inline-block;
          font-size: 16px;
          line-height: 1.16;
          font-weight: 800;
          color: #111827;
          letter-spacing: -0.02em;
          word-break: keep-all;
          overflow-wrap: anywhere;
        }}
      </style>
    </head>
    <body>
      <div class="ns-table-wrap">
        <table class="ns-decision-table">
          <colgroup>
            <col><col><col><col><col><col><col><col><col>
          </colgroup>
          <thead>
            <tr>{"".join(f"<th>{html.escape(header)}</th>" for header in headers)}</tr>
          </thead>
          <tbody>
            {"".join(row_html_parts)}
          </tbody>
        </table>
      </div>
    </body>
    </html>
    """
    components.html(table_html, height=estimated_height, scrolling=True)


def build_audit_comment(signal_text: str, horizon: str, mean_return: float, hit_rate: float) -> str:
    if horizon == "당일종가" and abs(mean_return) < 1e-9:
        return "당일종가 기준은 신호일 종가를 다시 비교한 값이라 방향성 해석력이 거의 없습니다."
    if signal_text == "매수":
        if hit_rate < 0.5 and mean_return > 0:
            return "적중률은 50% 미만이지만 평균수익률은 플러스입니다. 일부 큰 상승 사례가 평균을 끌어올렸고, 다수 종목의 방향성은 일관되지 않았습니다."
        if hit_rate < 0.5 and mean_return <= 0:
            return "적중률과 평균수익률이 모두 약합니다. 매수 후 단기 방향성이 일관되지 않았습니다."
        if hit_rate >= 0.5 and mean_return <= 0:
            return "상승 종목 수는 절반 이상이지만 평균수익률은 약합니다. 상승 폭이 작거나 일부 큰 하락 종목이 평균을 눌렀습니다."
        return "적중률과 평균수익률이 모두 양호합니다."
    if hit_rate < 0.5 and mean_return < 0:
        return "적중률은 50% 미만이지만 평균 변화율은 음수입니다. 일부 큰 하락 회피 사례가 평균을 개선했지만, 전반적 일관성은 약했습니다."
    if hit_rate < 0.5 and mean_return >= 0:
        return "적중률과 평균 변화율이 모두 약합니다. 매도 후 추가 하락이 일관되지 않았습니다."
    if hit_rate >= 0.5 and mean_return >= 0:
        return "하락 종목 비중은 절반 이상이지만 평균 변화율은 약합니다. 하락 폭보다 반등 폭이 큰 종목이 섞였습니다."
    return "적중률과 평균 변화율이 모두 양호합니다."


def classify_trade_outcome(action: str, row: pd.Series) -> str:
    if action == "매수":
        if pd.notna(row.get("7일후수익률")) and float(row["7일후수익률"]) >= 0.05:
            return "익절 우세"
        if pd.notna(row.get("당일종가수익률")) and float(row["당일종가수익률"]) <= -0.03:
            return "손절 우세"
        return "중립"
    if pd.notna(row.get("7일후수익률")) and float(row["7일후수익률"]) <= -0.05:
        return "매도 적중"
    if pd.notna(row.get("당일종가수익률")) and float(row["당일종가수익률"]) >= 0.03:
        return "매도 아쉬움"
    return "중립"


@st.cache_data(show_spinner=False)
def load_execution_timing_audit(_output_token: Any, _price_token: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not TRADE_LOG_PATH.exists() or not PRICE_PANEL_PATH.exists():
        return pd.DataFrame(), pd.DataFrame()
    trades = pd.read_csv(TRADE_LOG_PATH, dtype={"code": str}, low_memory=False)
    if trades.empty:
        return pd.DataFrame(), pd.DataFrame()
    prices = pd.read_csv(PRICE_PANEL_PATH, usecols=["date", "code", "close"], dtype={"code": str}, low_memory=False)
    prices["code"] = prices["code"].astype(str).str.zfill(6)
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    prices = prices.dropna(subset=["date"]).sort_values(["code", "date"])
    grp = prices.groupby("code", sort=False)
    prices["close_0d"] = prices["close"]
    prices["close_1d"] = grp["close"].shift(-1)
    prices["close_7d"] = grp["close"].shift(-7)

    trades["code"] = trades["code"].astype(str).str.zfill(6)
    buy_df = trades.dropna(subset=["entry_date", "entry_price"]).copy()
    buy_df["기준"] = "매수"
    buy_df["기준일"] = pd.to_datetime(buy_df["entry_date"], errors="coerce")
    buy_df["체결가"] = pd.to_numeric(buy_df["entry_price"], errors="coerce")
    sell_df = trades.dropna(subset=["exit_date", "exit_price"]).copy()
    sell_df["기준"] = "매도"
    sell_df["기준일"] = pd.to_datetime(sell_df["exit_date"], errors="coerce")
    sell_df["체결가"] = pd.to_numeric(sell_df["exit_price"], errors="coerce")
    base = pd.concat([buy_df, sell_df], ignore_index=True)
    base = base.dropna(subset=["기준일", "체결가"])
    merged = base.merge(prices[["date", "code", "close_0d", "close_1d", "close_7d"]], left_on=["기준일", "code"], right_on=["date", "code"], how="left")

    summary_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    for action in ["매수", "매도"]:
        subset = merged[merged["기준"] == action].copy()
        if subset.empty:
            continue
        for horizon, col in [("당일종가", "close_0d"), ("1일후", "close_1d"), ("7일후", "close_7d")]:
            valid = subset.dropna(subset=["체결가", col]).copy()
            if valid.empty:
                continue
            ret = valid[col] / valid["체결가"] - 1.0
            hit = ret > 0 if action == "매수" else ret < 0
            mean_ret = float(ret.mean())
            hit_rate = float(hit.mean())
            summary_rows.append(
                {
                    "기준": action,
                    "평가시점": horizon,
                    "표본수": int(len(valid)),
                    "평균수익률": mean_ret,
                    "중앙값수익률": float(ret.median()),
                    "적중률": hit_rate,
                    "의견": build_audit_comment(action, horizon, mean_ret, hit_rate),
                }
            )

        sample = subset.dropna(subset=["체결가", "close_0d"]).copy().head(50)
        for _, row in sample.iterrows():
            ret_0d = (float(row["close_0d"]) / float(row["체결가"]) - 1.0) if pd.notna(row.get("close_0d")) else float("nan")
            ret_1d = (float(row["close_1d"]) / float(row["체결가"]) - 1.0) if pd.notna(row.get("close_1d")) else float("nan")
            ret_7d = (float(row["close_7d"]) / float(row["체결가"]) - 1.0) if pd.notna(row.get("close_7d")) else float("nan")
            detail_rows.append(
                {
                    "기준": action,
                    "종목코드": row["code"],
                    "종목명": row.get("name", ""),
                    "기준일": str(pd.to_datetime(row["기준일"]).date()),
                    "체결가": float(row["체결가"]),
                    "당일종가수익률": ret_0d,
                    "1일후수익률": ret_1d,
                    "7일후수익률": ret_7d,
                    "청산사유": row.get("exit_reason", "") if action == "매도" else row.get("status", ""),
                }
            )

    summary = pd.DataFrame(summary_rows)
    if not summary.empty:
        action_order = {"매수": 0, "매도": 1}
        horizon_order = {"당일종가": 0, "1일후": 1, "7일후": 2}
        summary["_a"] = summary["기준"].map(action_order).fillna(99)
        summary["_h"] = summary["평가시점"].map(horizon_order).fillna(99)
        summary = summary.sort_values(["_a", "_h"]).drop(columns=["_a", "_h"]).reset_index(drop=True)
    detail = pd.DataFrame(detail_rows)
    return summary, detail


@st.cache_data(show_spinner=False)
def load_manual_trade_audit(
    _price_token: Any,
    _manual_trades_token: Any,
    _manual_positions_token: Any,
    chat_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not MANUAL_TRADES_PATH.exists() or not PRICE_PANEL_PATH.exists():
        return pd.DataFrame(), pd.DataFrame()
    trades = pd.read_csv(MANUAL_TRADES_PATH, dtype={"code": str, "chat_id": str}, low_memory=False)
    if trades.empty:
        return pd.DataFrame(), pd.DataFrame()
    if chat_id:
        trades = trades[trades["chat_id"].astype(str) == str(chat_id)].copy()
    if trades.empty:
        return pd.DataFrame(), pd.DataFrame()

    prices = pd.read_csv(PRICE_PANEL_PATH, usecols=["date", "code", "close"], dtype={"code": str}, low_memory=False)
    prices["code"] = prices["code"].astype(str).str.zfill(6)
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    prices = prices.dropna(subset=["date"]).sort_values(["code", "date"])
    grp = prices.groupby("code", sort=False)
    prices["close_0d"] = prices["close"]
    prices["close_1d"] = grp["close"].shift(-1)
    prices["close_7d"] = grp["close"].shift(-7)

    trades["code"] = trades["code"].astype(str).str.zfill(6)
    trades["created_at"] = pd.to_datetime(trades["created_at"], errors="coerce")
    trades = trades.dropna(subset=["created_at"]).copy()
    trades = trades.sort_values("created_at", ascending=False).reset_index(drop=True)
    trades["기준일"] = trades["created_at"].dt.normalize()
    trades["기준"] = trades["side"].astype(str).str.upper().map({"BUY": "매수", "SELL": "매도"}).fillna("기타")
    trades["체결가"] = pd.to_numeric(trades["price"], errors="coerce")
    trades["수량"] = pd.to_numeric(trades["quantity"], errors="coerce")
    trades = trades.dropna(subset=["체결가"])
    if trades.empty:
        return pd.DataFrame(), pd.DataFrame()

    merged = trades.merge(
        prices[["date", "code", "close_0d", "close_1d", "close_7d"]],
        left_on=["기준일", "code"],
        right_on=["date", "code"],
        how="left",
    )

    held_codes: set[str] = set()
    if MANUAL_POSITIONS_PATH.exists():
        pos = pd.read_csv(MANUAL_POSITIONS_PATH, dtype={"code": str, "chat_id": str}, low_memory=False)
        if not pos.empty:
            pos = pos[pos["chat_id"].astype(str) == str(chat_id)].copy()
            pos["quantity"] = pd.to_numeric(pos.get("quantity"), errors="coerce").fillna(0.0)
            pos["code"] = pos["code"].astype(str).str.zfill(6)
            held_codes = set(pos.loc[pos["quantity"] > 0, "code"].tolist())

    summary_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    for action in ["매수", "매도"]:
        subset = merged[merged["기준"] == action].copy()
        if subset.empty:
            continue
        for horizon, col in [("당일종가", "close_0d"), ("1일후", "close_1d"), ("7일후", "close_7d")]:
            valid = subset.dropna(subset=["체결가", col]).copy()
            if valid.empty:
                continue
            ret = valid[col] / valid["체결가"] - 1.0
            hit = ret > 0 if action == "매수" else ret < 0
            mean_ret = float(ret.mean())
            hit_rate = float(hit.mean())
            summary_rows.append(
                {
                    "기준": action,
                    "평가시점": horizon,
                    "표본수": int(len(valid)),
                    "평균수익률": mean_ret,
                    "중앙값수익률": float(ret.median()),
                    "적중률": hit_rate,
                    "의견": build_audit_comment(action, horizon, mean_ret, hit_rate),
                }
            )

        for _, row in subset.head(100).iterrows():
            ret_0d = (float(row["close_0d"]) / float(row["체결가"]) - 1.0) if pd.notna(row.get("close_0d")) else float("nan")
            ret_1d = (float(row["close_1d"]) / float(row["체결가"]) - 1.0) if pd.notna(row.get("close_1d")) else float("nan")
            ret_7d = (float(row["close_7d"]) / float(row["체결가"]) - 1.0) if pd.notna(row.get("close_7d")) else float("nan")
            detail_rows.append(
                {
                    "기준": action,
                    "종목코드": row["code"],
                    "종목명": row.get("name", ""),
                    "체결시각": str(row.get("created_at", ""))[:19],
                    "수량": float(row.get("수량", 0.0)),
                    "체결가": float(row["체결가"]),
                    "당일종가수익률": ret_0d,
                    "1일후수익률": ret_1d,
                    "7일후수익률": ret_7d,
                    "현재보유": "예" if row["code"] in held_codes else "아니오",
                }
            )

    summary = pd.DataFrame(summary_rows)
    if not summary.empty:
        action_order = {"매수": 0, "매도": 1}
        horizon_order = {"당일종가": 0, "1일후": 1, "7일후": 2}
        summary["_a"] = summary["기준"].map(action_order).fillna(99)
        summary["_h"] = summary["평가시점"].map(horizon_order).fillna(99)
        summary = summary.sort_values(["_a", "_h"]).drop(columns=["_a", "_h"]).reset_index(drop=True)
    detail = pd.DataFrame(detail_rows)
    if not detail.empty:
        detail["판정"] = detail.apply(lambda r: classify_trade_outcome(str(r.get("기준", "")), r), axis=1)
    return summary, detail


@st.cache_data(show_spinner=False)
def load_macro(_version_token: Any) -> pd.DataFrame:
    df = _read_csv(MACRO_DAILY_PATH)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_fundamental(code: str, _version_token: Any) -> pd.DataFrame:
    df = _read_csv(FUNDAMENTAL_PATH)
    if df.empty:
        return df
    df["종목코드"] = df["종목코드"].astype(str).str.zfill(6)
    df = df[df["종목코드"] == code].copy()
    if df.empty:
        return df
    df["공시일"] = pd.to_datetime(df["공시일"], errors="coerce")
    df["분기"] = df.apply(lambda row: _quarter_label(row["사업연도"], row["보고서코드"]), axis=1)
    order = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}
    df["_q"] = df["보고서코드"].astype(str).map(order).fillna(9)
    return df.sort_values(["사업연도", "_q"]).drop(columns="_q").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_decision_financial_summary(_fundamental_token: Any, codes: tuple[str, ...]) -> pd.DataFrame:
    if not FUNDAMENTAL_PATH.exists() or not codes:
        return pd.DataFrame(columns=["code", "decision_op_margin", "decision_op_qoq", "decision_op_ttm"])
    df = pd.read_csv(FUNDAMENTAL_PATH, dtype={"종목코드": str}, low_memory=False)
    if df.empty:
        return pd.DataFrame(columns=["code", "decision_op_margin", "decision_op_qoq", "decision_op_ttm"])
    df["종목코드"] = df["종목코드"].astype(str).str.zfill(6)
    df = df[df["종목코드"].isin(list(codes))].copy()
    if df.empty:
        return pd.DataFrame(columns=["code", "decision_op_margin", "decision_op_qoq", "decision_op_ttm"])

    order = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}
    df["공시일"] = pd.to_datetime(df["공시일"], errors="coerce")
    df["_q"] = df["보고서코드"].astype(str).map(order).fillna(9)
    df = df.dropna(subset=["공시일"]).sort_values(["종목코드", "사업연도", "_q"])

    rows: list[dict[str, Any]] = []
    for code, sub in df.groupby("종목코드", sort=False):
        latest = sub.tail(4).copy()
        if latest.empty:
            continue
        op_q = pd.to_numeric(latest["분기영업이익"], errors="coerce")
        revenue_q = pd.to_numeric(latest["분기매출액"], errors="coerce")
        op_margin_q = pd.to_numeric(latest["분기영업이익률"], errors="coerce")

        latest_op_margin = op_margin_q.iloc[-1] if not op_margin_q.empty else float("nan")
        latest_revenue = revenue_q.iloc[-1] if not revenue_q.empty else float("nan")
        latest_op = op_q.iloc[-1] if not op_q.empty else float("nan")
        if pd.isna(latest_op_margin) and pd.notna(latest_revenue) and latest_revenue != 0 and pd.notna(latest_op):
            latest_op_margin = float(latest_op) / float(latest_revenue)

        latest_op_qoq = float("nan")
        op_clean = op_q.dropna()
        if len(op_clean) >= 2:
            latest_op_qoq = float(op_clean.iloc[-1] - op_clean.iloc[-2])

        latest_op_ttm = float(op_q.sum(min_count=1)) if not op_q.dropna().empty else float("nan")
        rows.append(
            {
                "code": code,
                "decision_op_margin": latest_op_margin,
                "decision_op_qoq": latest_op_qoq,
                "decision_op_ttm": latest_op_ttm,
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def load_price_history(code: str, _version_token: Any) -> pd.DataFrame:
    if not PRICE_PANEL_PATH.exists():
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    cols = ["code", "name", "date", "open", "high", "low", "close", "volume", "trading_value", "market_cap", "industry"]
    for chunk in pd.read_csv(PRICE_PANEL_PATH, usecols=cols, chunksize=250000, dtype={"code": str}, low_memory=False):
        chunk["code"] = chunk["code"].astype(str).str.zfill(6)
        part = chunk[chunk["code"] == code]
        if not part.empty:
            frames.append(part)
    if not frames:
        return pd.DataFrame(columns=cols)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def load_default_config(meta: dict[str, Any]) -> dict[str, Any]:
    cfg = asdict(EarningsStrategyConfig())
    cfg.update(meta.get("config", {}))
    cfg.update(_read_json(UI_CONFIG_PATH))
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    UI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    UI_CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def build_pipeline_cmd(
    cfg: dict[str, Any],
    *,
    send_alerts: bool = False,
    refresh_data: bool = False,
    refresh_macro: bool = False,
    refresh_gold: bool = False,
    fast_alerts: bool = False,
    prefer_kiwoom_eod: bool = False,
    job_feedback_label: str = "",
) -> list[str]:
    cmd = [sys.executable, "-m", "new_strategy.run_signal_pipeline"]
    for spec in CONFIG_SPECS:
        cmd.extend([f"--{spec['key'].replace('_', '-')}", str(cfg[spec["key"]])])
    if send_alerts:
        cmd.append("--send-alerts")
    if refresh_data:
        cmd.append("--refresh-data")
    if refresh_macro:
        cmd.append("--refresh-macro")
    if refresh_gold:
        cmd.append("--refresh-gold")
    if prefer_kiwoom_eod:
        cmd.append("--prefer-kiwoom-eod")
    if fast_alerts:
        cmd.append("--fast-alerts")
    if str(job_feedback_label).strip():
        cmd.extend(["--job-feedback-label", str(job_feedback_label).strip()])
    return cmd


def is_pid_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def read_pipeline_progress() -> dict[str, Any]:
    payload = _read_json(PIPELINE_PROGRESS_PATH)
    if not payload:
        return {}
    pid = _safe_int(payload.get("pid"), 0)
    status = str(payload.get("status", ""))
    if status == "running" and pid and not is_pid_running(pid):
        payload["status"] = "unknown"
    return payload


def _pipeline_run_id() -> str:
    return f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"


def _pipeline_history_df() -> pd.DataFrame:
    if not PIPELINE_HISTORY_PATH.exists():
        return pd.DataFrame(columns=PIPELINE_HISTORY_COLUMNS)
    try:
        df = pd.read_csv(PIPELINE_HISTORY_PATH, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=PIPELINE_HISTORY_COLUMNS)
    for col in PIPELINE_HISTORY_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[PIPELINE_HISTORY_COLUMNS].copy()


def _normalize_legacy_output_path_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("\\output\\strategy_v1\\", "\\output\\strategy_v2\\")


def _write_pipeline_history(df: pd.DataFrame) -> None:
    PIPELINE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for col in PIPELINE_HISTORY_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out[PIPELINE_HISTORY_COLUMNS].to_csv(PIPELINE_HISTORY_PATH, index=False, encoding="utf-8-sig")


def _upsert_pipeline_history(record: dict[str, Any]) -> None:
    run_id = str(record.get("run_id") or "").strip()
    if not run_id:
        return
    df = _pipeline_history_df()
    normalized = {col: str(record.get(col, "") or "") for col in PIPELINE_HISTORY_COLUMNS}
    for key in ["stdout_path", "stderr_path"]:
        normalized[key] = _normalize_legacy_output_path_text(normalized.get(key, ""))
    mask = df["run_id"].astype(str) == run_id
    if mask.any():
        for col, value in normalized.items():
            df.loc[mask, col] = value
    else:
        df = pd.concat([pd.DataFrame([normalized]), df], ignore_index=True)
    if "started_at" in df.columns:
        df = df.sort_values("started_at", ascending=False, kind="stable").reset_index(drop=True)
    _write_pipeline_history(df)


def sync_pipeline_history(progress: dict[str, Any] | None = None) -> None:
    payload = progress or read_pipeline_progress()
    if not payload:
        return
    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        return
    _upsert_pipeline_history(
        {
            "run_id": run_id,
            "started_at": payload.get("started_at", ""),
            "updated_at": payload.get("updated_at", ""),
            "finished_at": payload.get("finished_at", ""),
            "status": payload.get("status", ""),
            "percent": payload.get("percent", ""),
            "stage": payload.get("stage", ""),
            "detail": payload.get("detail", ""),
            "duration_seconds": payload.get("duration_seconds", ""),
            "pid": payload.get("pid", ""),
            "description": payload.get("description", ""),
            "command": payload.get("command", ""),
            "stdout_path": payload.get("stdout_path", ""),
            "stderr_path": payload.get("stderr_path", ""),
        }
    )


def _pipeline_output_paths(progress: dict[str, Any] | None = None) -> tuple[Path, Path]:
    payload = progress or read_pipeline_progress()
    raw_stdout_text = str(payload.get("stdout_path") or "").strip() if payload else ""
    raw_stderr_text = str(payload.get("stderr_path") or "").strip() if payload else ""
    stdout_text = _normalize_legacy_output_path_text(raw_stdout_text)
    stderr_text = _normalize_legacy_output_path_text(raw_stderr_text)
    stdout_path = Path(stdout_text) if stdout_text else PIPELINE_STDOUT_PATH
    stderr_path = Path(stderr_text) if stderr_text else PIPELINE_STDERR_PATH
    if raw_stdout_text and not stdout_path.exists():
        raw_stdout_path = Path(raw_stdout_text)
        if raw_stdout_path.exists():
            stdout_path = raw_stdout_path
    if raw_stderr_text and not stderr_path.exists():
        raw_stderr_path = Path(raw_stderr_text)
        if raw_stderr_path.exists():
            stderr_path = raw_stderr_path
    return stdout_path, stderr_path


def launch_pipeline_job(cfg: dict[str, Any], description: str, **kwargs: Any) -> bool:
    progress = read_pipeline_progress()
    if progress and str(progress.get("status")) == "running" and is_pid_running(_safe_int(progress.get("pid"), 0)):
        set_flash("이미 실행 중인 작업이 있습니다. 진행률을 먼저 확인하세요.", level="warning")
        return False
    cmd = build_pipeline_cmd(cfg, **kwargs)
    run_id = _pipeline_run_id()
    PIPELINE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = PIPELINE_RUNS_DIR / f"{run_id}.stdout.log"
    stderr_path = PIPELINE_RUNS_DIR / f"{run_id}.stderr.log"
    command_text = subprocess.list2cmdline(cmd)
    cmd.extend(["--progress-file", str(PIPELINE_PROGRESS_PATH)])
    progress_payload = {
        "run_id": run_id,
        "pid": 0,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": "",
        "status": "starting",
        "percent": 0,
        "stage": "대기",
        "detail": description,
        "duration_seconds": 0,
        "description": description,
        "command": command_text,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    PIPELINE_PROGRESS_PATH.write_text(json.dumps(progress_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _upsert_pipeline_history(progress_payload)
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
        subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    set_flash(f"{description} 작업을 백그라운드에서 시작했습니다.", level="success")
    return True


def run_pipeline(cfg: dict[str, Any], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(build_pipeline_cmd(cfg, **kwargs), check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")


def classify_signal(row: pd.Series, cfg: dict[str, Any]) -> str:
    signal = str(row.get("signal", "")).upper()
    risk_flag = "" if pd.isna(row.get("risk_flag")) else str(row.get("risk_flag")).strip()
    if signal in {"BUY", "BUY_WATCH"}:
        return signal
    if signal in {"SELL", "SELL_WATCH"}:
        return signal
    if signal == "WATCH":
        return "BUY_WATCH"
    if signal == "HOLD" and has_risk_flag(risk_flag, "weekly_sell_watch"):
        return "SELL_WATCH"
    return "HOLD"


def prepare_signal_display(signal_df: pd.DataFrame, cfg: dict[str, Any], real_holding_codes: set[str] | None = None) -> pd.DataFrame:
    if signal_df.empty:
        return signal_df
    execution_window = is_execution_window()
    df = signal_df.copy()
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["display_signal"] = df.apply(lambda row: classify_signal(row, cfg), axis=1)
    real_holding_codes = set(real_holding_codes or set())
    df["is_real_holding"] = df["code"].isin(real_holding_codes)
    if real_holding_codes:
        df = df[df["is_real_holding"] | df["display_signal"].isin(["BUY", "BUY_WATCH"])].copy()
    else:
        df = df[df["display_signal"].isin(["BUY", "BUY_WATCH"])].copy()
    df["display_signal_ko"] = df["display_signal"].map(lambda x: signal_label(x, execution_window=execution_window))
    df["active_execution_guide"] = df.apply(lambda row: resolve_action_guide(row, execution_window=execution_window), axis=1)
    df["signal_rank"] = df["display_signal"].map(SIGNAL_ORDER).fillna(99)
    return df.sort_values(["is_real_holding", "signal_rank", "code"], ascending=[False, True, True]).reset_index(drop=True)


def append_manual_holding_placeholders(
    signal_df: pd.DataFrame,
    *,
    real_holding_codes: set[str],
    manual_positions: pd.DataFrame,
    latest_price: pd.DataFrame,
    decision_df: pd.DataFrame,
) -> pd.DataFrame:
    if not real_holding_codes:
        return signal_df

    base = signal_df.copy()
    existing_codes = set()
    if not base.empty and "code" in base.columns:
        existing_codes = set(base["code"].astype(str).str.zfill(6))
    missing_codes = sorted(set(real_holding_codes) - existing_codes)
    if not missing_codes:
        return base

    latest_date = pd.NaT
    if not base.empty and "date" in base.columns:
        latest_date = pd.to_datetime(base["date"], errors="coerce").max()
    if pd.isna(latest_date) and not decision_df.empty and "date" in decision_df.columns:
        latest_date = pd.to_datetime(decision_df["date"], errors="coerce").max()

    manual_lookup = manual_positions.copy() if not manual_positions.empty else pd.DataFrame()
    if not manual_lookup.empty:
        manual_lookup["code"] = manual_lookup["code"].astype(str).str.zfill(6)
    price_lookup = latest_price.copy() if not latest_price.empty else pd.DataFrame()
    if not price_lookup.empty:
        price_lookup["code"] = price_lookup["code"].astype(str).str.zfill(6)

    rows: list[dict[str, Any]] = []
    for code in missing_codes:
        manual_row = manual_lookup[manual_lookup["code"] == code].tail(1) if not manual_lookup.empty else pd.DataFrame()
        price_row = price_lookup[price_lookup["code"] == code].tail(1) if not price_lookup.empty else pd.DataFrame()
        name = "-"
        industry = "-"
        close = np.nan
        if not manual_row.empty:
            name = str(manual_row.iloc[-1].get("name") or name)
        if not price_row.empty:
            if name == "-" and str(price_row.iloc[-1].get("name") or "").strip():
                name = str(price_row.iloc[-1].get("name"))
            industry = str(price_row.iloc[-1].get("industry") or industry)
            close = pd.to_numeric(pd.Series([price_row.iloc[-1].get("close")]), errors="coerce").iloc[0]
        rows.append(
            {
                "date": latest_date,
                "code": code,
                "name": name,
                "industry": industry,
                "signal": "HOLD",
                "strategy_id": "earnings_pti_v2",
                "conviction_score": 0.30,
                "holding_horizon": "보유 점검",
                "reason_1": "실보유 종목",
                "reason_2": "전략 신호 없음",
                "reason_3": "수동 보유 현황 기준으로 표시",
                "risk_flag": "signal_missing",
                "close": close,
            }
        )

    extra = pd.DataFrame(rows)
    if base.empty:
        return extra
    return pd.concat([base, extra], ignore_index=True, sort=False)


def select_v2_decision_signals(
    signal_df: pd.DataFrame,
    signal_fast_df: pd.DataFrame,
    real_holding_codes: set[str] | None = None,
) -> pd.DataFrame:
    real_holding_codes = set(real_holding_codes or set())
    fast = signal_fast_df.copy() if not signal_fast_df.empty else pd.DataFrame()
    full = signal_df.copy() if not signal_df.empty else pd.DataFrame()

    if not fast.empty:
        fast["code"] = fast["code"].astype(str).str.zfill(6)
        frames = [fast]
        if real_holding_codes and not full.empty:
            full["code"] = full["code"].astype(str).str.zfill(6)
            carry = full[full["code"].isin(real_holding_codes) & ~full["code"].isin(set(fast["code"]))].copy()
            if not carry.empty:
                frames.append(carry)
        out = pd.concat(frames, ignore_index=True, sort=False)
        if "date" in out.columns:
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
            out = out.sort_values(["date", "code"], ascending=[False, True], kind="stable")
        return out.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)

    if not full.empty:
        full["code"] = full["code"].astype(str).str.zfill(6)
    return full


def merge_latest_signal_sources(signal_df: pd.DataFrame, signal_fast_df: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not signal_fast_df.empty:
        fast = signal_fast_df.copy()
        fast["code"] = fast["code"].astype(str).str.zfill(6)
        fast["_source_rank"] = 0
        frames.append(fast)
    if not signal_df.empty:
        full = signal_df.copy()
        full["code"] = full["code"].astype(str).str.zfill(6)
        full["_source_rank"] = 1
        frames.append(full)
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True, sort=False)
    if "date" in merged.columns:
        merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
        merged = merged.sort_values(["date", "_source_rank", "code"], ascending=[False, True, True], kind="stable")
    else:
        merged = merged.sort_values(["_source_rank", "code"], ascending=[True, True], kind="stable")
    merged = merged.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    return merged.drop(columns=["_source_rank"], errors="ignore")


def attach_live_quote(price_df: pd.DataFrame, code: str, live_quotes: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if live_quotes.empty:
        return price_df, {}
    live = live_quotes.copy()
    live["code"] = live["code"].astype(str).str.zfill(6)
    live = live[live["code"] == code]
    if live.empty:
        return price_df, {}
    live["date"] = pd.to_datetime(live["date"], errors="coerce")
    row = live.sort_values(["date", "quote_time"]).iloc[-1]
    overlay = pd.DataFrame([{
        "code": code,
        "name": row.get("name"),
        "date": pd.to_datetime(row.get("date")),
        "open": _safe_float(row.get("open")),
        "high": _safe_float(row.get("high")),
        "low": _safe_float(row.get("low")),
        "close": _safe_float(row.get("close")),
        "volume": _safe_float(row.get("volume")),
        "trading_value": _safe_float(row.get("trading_value")),
        "market_cap": float("nan"),
        "industry": None,
    }])
    if price_df.empty:
        return overlay, row.to_dict()
    last_date = price_df["date"].max()
    overlay_date = overlay["date"].iloc[0]
    if overlay_date > last_date:
        price_df = pd.concat([price_df, overlay], ignore_index=True)
    elif overlay_date == last_date:
        mask = price_df["date"] == last_date
        for col in ["open", "high", "low", "close", "volume", "trading_value"]:
            price_df.loc[mask, col] = overlay.iloc[0][col]
    return price_df.sort_values("date").reset_index(drop=True), row.to_dict()


def enrich_signal_display(signal_df: pd.DataFrame, data: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    if signal_df.empty:
        return signal_df.copy(), {
            "feature_latest": pd.DataFrame(),
            "latest_price": pd.DataFrame(),
            "fast_state": pd.DataFrame(),
            "manual_positions": pd.DataFrame(),
            "optimal_ma_latest": pd.DataFrame(),
        }

    out = signal_df.copy()
    feature_latest = load_feature_latest_snapshot(data["version_tokens"]["output"])
    latest_price = load_price_latest_snapshot(data["version_tokens"]["price"])
    fast_state = load_fast_position_state(data["version_tokens"]["output"])
    manual_positions = load_manual_positions_snapshot(data["version_tokens"]["output"])
    optimal_ma_latest = load_optimal_ma_latest_snapshot(data["version_tokens"]["optimal_ma"])

    if not feature_latest.empty:
        feature_info = feature_latest.copy()
        required_feature_cols = [
            "code",
            "industry",
            "fiscal_year_pti",
            "reprt_code_pti",
            "filing_date_pti",
            "op_margin_pti",
            "net_margin_pti",
            "op_income_qoq_pti",
            "net_income_qoq_pti",
            "op_income_qoq_accel",
            "net_income_qoq_accel",
            "op_income_q_ttm",
            "net_income_q_ttm",
            "op_income_q_vol_4q",
            "net_income_q_vol_4q",
            "net_op_gap_ratio",
        ]
        for col in required_feature_cols:
            if col not in feature_info.columns:
                feature_info[col] = np.nan
        feature_info = feature_info[required_feature_cols].copy()
        feature_info["근거 기준 분기"] = feature_info.apply(
            lambda row: format_quarter_label(row.get("fiscal_year_pti"), row.get("reprt_code_pti")),
            axis=1,
        )
        feature_info["기준 공시일"] = pd.to_datetime(
            feature_info["filing_date_pti"], errors="coerce"
        ).dt.date.astype("string").fillna("-")
        out = out.merge(
            feature_info[
                [
                    "code",
                    "industry",
                    "근거 기준 분기",
                    "기준 공시일",
                    "op_margin_pti",
                    "net_margin_pti",
                    "op_income_qoq_pti",
                    "net_income_qoq_pti",
                    "op_income_qoq_accel",
                    "net_income_qoq_accel",
                    "op_income_q_ttm",
                    "net_income_q_ttm",
                    "op_income_q_vol_4q",
                    "net_income_q_vol_4q",
                    "net_op_gap_ratio",
                ]
            ],
            on="code",
            how="left",
            suffixes=("", "_feat"),
        )
        if "industry_feat" in out.columns:
            out["industry"] = out["industry"].fillna(out["industry_feat"])
            out = out.drop(columns=["industry_feat"])

    if not latest_price.empty:
        price_info = latest_price.copy()
        required_price_cols = ["code", "close", "date", "market_cap", "volume", "industry"]
        for col in required_price_cols:
            if col not in price_info.columns:
                price_info[col] = np.nan
        price_info = price_info[required_price_cols].copy().rename(
            columns={
                "close": "latest_close",
                "date": "latest_price_date",
                "market_cap": "latest_market_cap",
                "volume": "latest_volume",
                "industry": "latest_industry",
            }
        )
        out = out.merge(price_info, on="code", how="left", suffixes=("", "_price"))
        for base_col in ["latest_close", "latest_price_date", "latest_market_cap", "latest_volume"]:
            price_col = f"{base_col}_price"
            if price_col in out.columns:
                if base_col not in out.columns:
                    out[base_col] = np.nan
                out[base_col] = out[base_col].combine_first(out[price_col])
                out = out.drop(columns=[price_col])
        if "latest_industry" in out.columns:
            out["industry"] = out["industry"].fillna(out["latest_industry"])
            out = out.drop(columns=["latest_industry"])

    if not optimal_ma_latest.empty:
        out = out.merge(
            optimal_ma_latest[
                [
                    "code",
                    "optimal_ma_timeframe",
                    "optimal_ma_timeframe_ko",
                    "optimal_ma_action_mode",
                    "optimal_ma_action_mode_ko",
                    "optimal_ma_window",
                    "optimal_ma_ok",
                    "optimal_ma_signal_ko",
                    "optimal_ma_basis_label",
                    "optimal_ma_basis_price",
                    "optimal_ma_basis_date",
                    "optimal_ma_line_price",
                    "optimal_ma_rule_text",
                    "optimal_ma_excess_return",
                    "optimal_ma_win_rate",
                ]
            ],
            on="code",
            how="left",
        )

    out["optimal_ma_alignment"] = out.apply(
        lambda row: _optimal_ma_alignment_text(row.get("display_signal"), row.get("optimal_ma_ok")),
        axis=1,
    )
    out["최적 MA"] = out.apply(_optimal_ma_compact_text, axis=1)
    out["최적 MA 상세"] = out.apply(_optimal_ma_detail_text, axis=1)
    out["V2 타이밍"] = out.apply(lambda row: format_v2_timing_summary(row), axis=1)

    price_guides = out.apply(
        lambda row: build_compact_price_guide(
            row,
            latest_price=latest_price,
            manual_positions=manual_positions,
            fast_state=fast_state,
        ),
        axis=1,
    )
    out["가격 기준"] = [x[0] for x in price_guides]
    out["가격 규칙"] = [x[1] for x in price_guides]
    out["리스크"] = out["risk_flag"].map(prettify_risk_flag).fillna("-") if "risk_flag" in out.columns else "-"

    return out, {
        "feature_latest": feature_latest,
        "latest_price": latest_price,
        "fast_state": fast_state,
        "manual_positions": manual_positions,
        "optimal_ma_latest": optimal_ma_latest,
    }


def finalize_signal_axes(
    signal_df: pd.DataFrame,
    *,
    data: dict[str, Any],
    context: dict[str, Any],
    decision_df: pd.DataFrame,
) -> pd.DataFrame:
    if signal_df.empty:
        return signal_df.copy()

    out = signal_df.copy()
    last_decision = decision_df.sort_values("date").iloc[-1] if not decision_df.empty else None
    market_regime = str(last_decision.get("market_regime", "unknown")) if last_decision is not None else "unknown"
    market_exposure = _safe_float(last_decision.get("exposure"), float("nan")) if last_decision is not None else float("nan")
    execution_window = is_execution_window()

    out["market_regime"] = market_regime
    out["market_exposure"] = market_exposure
    fin_summary = load_decision_financial_summary(
        data["version_tokens"]["fundamental"],
        tuple(sorted(out["code"].astype(str).str.zfill(6).unique().tolist())),
    )
    if not fin_summary.empty:
        out = out.merge(fin_summary, on="code", how="left")
        for src, dst in [
            ("decision_op_margin", "op_margin_pti"),
            ("decision_op_qoq", "op_income_qoq_pti"),
            ("decision_op_ttm", "op_income_q_ttm"),
        ]:
            if dst not in out.columns:
                out[dst] = np.nan
            out[dst] = out[dst].combine_first(out[src])

    out["industry_volume_avg"] = float("nan")
    latest_price_snapshot = context.get("latest_price", pd.DataFrame())
    if not latest_price_snapshot.empty and "volume" in latest_price_snapshot.columns:
        latest_price_snapshot = latest_price_snapshot.copy()
        latest_price_snapshot["industry"] = latest_price_snapshot["industry"].astype(str)
        latest_price_snapshot["volume"] = pd.to_numeric(latest_price_snapshot["volume"], errors="coerce")
        volume_map = latest_price_snapshot.groupby("industry")["volume"].mean()
        out["industry_volume_avg"] = out["industry"].astype(str).map(volume_map)

    out["industry_period_return"] = float("nan")
    out["industry_timeframe"] = out.get("optimal_ma_timeframe", pd.Series(index=out.index)).fillna("monthly")
    out["industry_window"] = pd.to_numeric(
        out.get("optimal_ma_window", pd.Series(index=out.index)),
        errors="coerce",
    )
    valid_combos = (
        out[["industry_timeframe", "industry_window"]]
        .dropna()
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    for timeframe, window in valid_combos:
        window_int = int(float(window))
        industry_ret_df = load_latest_industry_return_by_timeframe_window(data["version_tokens"]["price"], str(timeframe), window_int)
        if industry_ret_df.empty:
            continue
        ret_map = industry_ret_df.set_index("industry")["industry_return"]
        mask = (
            out["industry_timeframe"].astype(str).str.lower() == str(timeframe).lower()
        ) & (out["industry_window"].fillna(-1).astype(int) == window_int)
        out.loc[mask, "industry_period_return"] = out.loc[mask, "industry"].astype(str).map(ret_map)

    out["최적 MA 축"] = out.apply(lambda row: format_v2_ma_axis_summary(row), axis=1)
    out["주가 위치 축"] = out.apply(lambda row: format_price_axis_summary(row), axis=1)
    out["재무 축"] = out.apply(lambda row: format_financial_axis_summary(row), axis=1)
    out["매크로 축"] = out.apply(lambda row: format_macro_axis_summary(row), axis=1)
    out["실행 요약"] = out.apply(lambda row: compact_execution_guide(row, execution_window=execution_window), axis=1)
    return out


def resample_ohlcv(df: pd.DataFrame, timeframe: str, optimal_row: pd.Series | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    frame = df.set_index("date").sort_index()
    optimal_timeframe = ""
    optimal_window = 0
    window = 0
    label = "없음"
    color = "#9ca3af"
    if optimal_row is not None:
        raw_timeframe = str(
            optimal_row.get("ma_timeframe")
            or optimal_row.get("optimal_ma_timeframe")
            or optimal_row.get("optimal_ma_timeframe_ko")
            or ""
        ).strip()
        raw_window = optimal_row.get("ma_window")
        if pd.isna(raw_window):
            raw_window = optimal_row.get("optimal_ma_window")
        optimal_window = _safe_int(raw_window, 0)
        timeframe_map = {
            "daily": "일봉",
            "weekly": "주봉",
            "monthly": "월봉",
            "일봉": "일봉",
            "주봉": "주봉",
            "월봉": "월봉",
        }
        optimal_timeframe = timeframe_map.get(raw_timeframe.lower(), raw_timeframe)
    if timeframe == "일봉":
        out = frame.reset_index()
        if optimal_timeframe == "일봉" and optimal_window > 0:
            window = optimal_window
            label = f"일봉 {window}이평(최적)"
            color = "#f59e0b"
    elif timeframe == "주봉":
        out = (
            frame.resample("W-FRI")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "trading_value": "sum"})
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        if optimal_timeframe == "주봉" and optimal_window > 0:
            window = optimal_window
            label = f"주봉 {window}이평(최적)"
            color = "#16a34a"
    else:
        grouped = frame.groupby(frame.index.to_period("M"))
        out = (
            grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "trading_value": "sum"})
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        out["date"] = out["date"].dt.to_timestamp(how="end").dt.normalize()
        if optimal_timeframe == "월봉" and optimal_window > 0:
            window = optimal_window
            label = f"월봉 {window}이평(최적)"
            color = "#7c3aed"
    out["date"] = pd.to_datetime(out["date"])
    if window > 0:
        min_periods = max(1, min(window, max(5, int(window * 0.6))))
        out["ma_overlay"] = out["close"].rolling(window, min_periods=min_periods).mean()
    else:
        out["ma_overlay"] = np.nan
    out["ma_label"] = label
    out["ma_color"] = color
    return out


def build_weekly_monthly_gap_series(price_df: pd.DataFrame, monthly_optimal_row: pd.Series | None) -> pd.DataFrame:
    if price_df.empty:
        return pd.DataFrame()
    window = 0
    if monthly_optimal_row is not None:
        raw_window = monthly_optimal_row.get("ma_window")
        if pd.isna(raw_window):
            raw_window = monthly_optimal_row.get("optimal_ma_window")
        window = _safe_int(raw_window, 0)
    if window <= 0:
        return pd.DataFrame()

    daily = price_df[["date", "close"]].copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
    daily = daily.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    if daily.empty:
        return pd.DataFrame()

    month_end = daily.copy()
    month_end["month_key"] = month_end["date"].dt.to_period("M")
    month_end = (
        month_end.groupby("month_key", as_index=False)
        .agg(date=("date", "max"), close=("close", "last"))
        .sort_values("date")
        .reset_index(drop=True)
    )
    if month_end.empty:
        return pd.DataFrame()
    min_periods = max(1, min(window, max(5, int(window * 0.6))))
    month_end["monthly_ma"] = month_end["close"].rolling(window, min_periods=min_periods).mean()

    weekly = daily.copy()
    weekly["week_key"] = weekly["date"].dt.to_period("W-FRI")
    weekly = (
        weekly.groupby("week_key", as_index=False)
        .agg(date=("date", "max"), close=("close", "last"))
        .sort_values("date")
        .reset_index(drop=True)
    )
    if weekly.empty:
        return pd.DataFrame()

    out = pd.merge_asof(
        weekly.sort_values("date"),
        month_end[["date", "monthly_ma"]].sort_values("date"),
        on="date",
        direction="backward",
    )
    out = out.dropna(subset=["monthly_ma"]).copy()
    if out.empty:
        return out
    out["gap_pct"] = out["close"] / out["monthly_ma"] - 1.0
    out["window"] = window
    out["is_latest"] = False
    out.loc[out.index[-1], "is_latest"] = True
    return out


def build_monthly_gap_series(price_df: pd.DataFrame, monthly_optimal_row: pd.Series | None) -> pd.DataFrame:
    if price_df.empty:
        return pd.DataFrame()
    window = 0
    if monthly_optimal_row is not None:
        raw_window = monthly_optimal_row.get("ma_window")
        if pd.isna(raw_window):
            raw_window = monthly_optimal_row.get("optimal_ma_window")
        window = _safe_int(raw_window, 0)
    if window <= 0:
        return pd.DataFrame()

    daily = price_df[["date", "close"]].copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
    daily = daily.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    if daily.empty:
        return pd.DataFrame()

    month_end = daily.copy()
    month_end["month_key"] = month_end["date"].dt.to_period("M")
    month_end = (
        month_end.groupby("month_key", as_index=False)
        .agg(date=("date", "max"), close=("close", "last"))
        .sort_values("date")
        .reset_index(drop=True)
    )
    if month_end.empty:
        return pd.DataFrame()
    min_periods = max(1, min(window, max(5, int(window * 0.6))))
    month_end["monthly_ma"] = month_end["close"].rolling(window, min_periods=min_periods).mean()
    out = month_end.dropna(subset=["monthly_ma"]).copy()
    if out.empty:
        return out
    out["gap_pct"] = out["close"] / out["monthly_ma"] - 1.0
    out["window"] = window
    out["is_latest"] = False
    out.loc[out.index[-1], "is_latest"] = True
    return out


def date_axis_for_chart(df: pd.DataFrame) -> alt.Axis:
    if df.empty or "date" not in df.columns:
        return alt.Axis(format="%Y-%m")
    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    if dates.empty:
        return alt.Axis(format="%Y-%m")
    span_days = max(1, int((dates.max() - dates.min()).days))
    if span_days >= 540:
        fmt = "%Y-%m"
    else:
        fmt = "%Y-%m-%d"
    return alt.Axis(format=fmt, labelOverlap=True)


def _date_scale_for_chart(x_domain: tuple[pd.Timestamp, pd.Timestamp] | None = None) -> alt.Scale | None:
    if not x_domain:
        return None
    start, end = x_domain
    if pd.isna(start) or pd.isna(end):
        return None
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    return alt.Scale(
        domain=[
            alt.DateTime(
                year=int(start_ts.year),
                month=int(start_ts.month),
                date=int(start_ts.day),
                hours=int(start_ts.hour),
                minutes=int(start_ts.minute),
                seconds=int(start_ts.second),
            ),
            alt.DateTime(
                year=int(end_ts.year),
                month=int(end_ts.month),
                date=int(end_ts.day),
                hours=int(end_ts.hour),
                minutes=int(end_ts.minute),
                seconds=int(end_ts.second),
            ),
        ]
    )


def candlestick_chart(df: pd.DataFrame, title: str, x_domain: tuple[pd.Timestamp, pd.Timestamp] | None = None) -> alt.Chart:
    if df.empty:
        return alt.Chart(pd.DataFrame({"date": [], "close": []})).mark_line()
    chart_df = df.copy()
    chart_df["상승"] = chart_df["close"] >= chart_df["open"]
    x_kwargs: dict[str, Any] = {"title": "날짜", "axis": date_axis_for_chart(chart_df)}
    scale = _date_scale_for_chart(x_domain)
    if scale is not None:
        x_kwargs["scale"] = scale
    base = alt.Chart(chart_df).encode(
        x=alt.X("date:T", **x_kwargs),
        tooltip=[
            alt.Tooltip("date:T", title="날짜"),
            alt.Tooltip("open:Q", title="시가", format=",.0f"),
            alt.Tooltip("high:Q", title="고가", format=",.0f"),
            alt.Tooltip("low:Q", title="저가", format=",.0f"),
            alt.Tooltip("close:Q", title="종가", format=",.0f"),
            alt.Tooltip("volume:Q", title="거래량", format=",.0f"),
        ],
    )
    color = alt.condition("datum.상승", alt.value("#d9534f"), alt.value("#337ab7"))
    wick = base.mark_rule().encode(y=alt.Y("low:Q", title="가격"), y2="high:Q", color=color)
    body = base.mark_bar(size=8).encode(y="open:Q", y2="close:Q", color=color)
    layers = wick + body
    if "ma_overlay" in chart_df.columns and not chart_df["ma_overlay"].dropna().empty:
        ma_color = chart_df["ma_color"].dropna().iloc[0] if "ma_color" in chart_df.columns and not chart_df["ma_color"].dropna().empty else "#f59e0b"
        ma_label = chart_df["ma_label"].dropna().iloc[0] if "ma_label" in chart_df.columns and not chart_df["ma_label"].dropna().empty else "이평선"
        ma_line = alt.Chart(chart_df).mark_line(color=ma_color, strokeWidth=2.0).encode(
            x=alt.X("date:T", **x_kwargs),
            y=alt.Y("ma_overlay:Q", title="가격"),
            tooltip=[
                alt.Tooltip("date:T", title="날짜"),
                alt.Tooltip("ma_overlay:Q", title=ma_label, format=",.0f"),
            ],
        )
        layers = layers + ma_line
    return layers.properties(height=380, title=title)


def latest_ma_snapshot(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {}
    daily = resample_ohlcv(df, "일봉")
    weekly = resample_ohlcv(df, "주봉")
    monthly = resample_ohlcv(df, "월봉")
    last_close = _safe_float(daily.iloc[-1]["close"], float("nan")) if not daily.empty else float("nan")
    return {
        "daily_close": last_close,
        "daily_ma20": _safe_float(daily.iloc[-1]["ma_overlay"], float("nan")) if not daily.empty else float("nan"),
        "weekly_ma10": _safe_float(weekly.iloc[-1]["ma_overlay"], float("nan")) if not weekly.empty else float("nan"),
        "monthly_ma10": _safe_float(monthly.iloc[-1]["ma_overlay"], float("nan")) if not monthly.empty else float("nan"),
    }


def line_chart(
    df: pd.DataFrame,
    column: str,
    title: str,
    color: str,
    x_domain: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    *,
    zero_baseline: bool = True,
) -> alt.Chart:
    chart_df = df[["date", column]].dropna().rename(columns={column: "value"})
    x_kwargs: dict[str, Any] = {"title": "날짜", "axis": date_axis_for_chart(chart_df)}
    scale = _date_scale_for_chart(x_domain)
    if scale is not None:
        x_kwargs["scale"] = scale
    return alt.Chart(chart_df).mark_line(color=color).encode(
        x=alt.X("date:T", **x_kwargs),
        y=alt.Y("value:Q", title=title, scale=alt.Scale(zero=zero_baseline, nice=True)),
        tooltip=[alt.Tooltip("date:T", title="날짜"), alt.Tooltip("value:Q", title=title, format=",.2f")],
    ).properties(height=180)


def percent_line_chart(df: pd.DataFrame, column: str, title: str, color: str, x_domain: tuple[pd.Timestamp, pd.Timestamp] | None = None) -> alt.Chart:
    chart_df = df[["date", column]].dropna().rename(columns={column: "value"})
    if chart_df.empty:
        return alt.Chart(pd.DataFrame({"date": [], "value": []})).mark_line()
    x_kwargs: dict[str, Any] = {"title": "날짜", "axis": date_axis_for_chart(chart_df)}
    scale = _date_scale_for_chart(x_domain)
    if scale is not None:
        x_kwargs["scale"] = scale
    base = alt.Chart(chart_df).encode(
        x=alt.X("date:T", **x_kwargs),
        y=alt.Y("value:Q", title=title, axis=alt.Axis(format=".0%")),
        tooltip=[alt.Tooltip("date:T", title="날짜"), alt.Tooltip("value:Q", title=title, format=".2%")],
    )
    zero = alt.Chart(pd.DataFrame({"value": [0.0]})).mark_rule(color="#cbd5e1", strokeDash=[4, 4]).encode(y="value:Q")
    line = base.mark_line(color=color, strokeWidth=2.0)
    latest = base.transform_filter("datum.is_latest === true").mark_point(color=color, filled=True, size=90)
    return (zero + line + latest).properties(height=190)


def render_table(df: pd.DataFrame, height: int | None = None) -> None:
    def style_signal_cell(value: Any) -> str:
        text = str(value or "")
        if "매수" in text:
            return "background-color: #ecfdf5; color: #065f46; font-weight: 700;"
        if "매도" in text:
            return "background-color: #fff1f2; color: #9f1239; font-weight: 700;"
        if "보유" in text:
            return "background-color: #eff6ff; color: #1d4ed8; font-weight: 700;"
        if "관심" in text or "경고" in text:
            return "background-color: #fffbeb; color: #92400e; font-weight: 700;"
        return ""

    if df.empty:
        st.dataframe(df, hide_index=True, use_container_width=True, height=height)
        return
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d").fillna("-")

    percent_tokens = ["수익률", "승률", "적중률", "비중", "비율", "변동률", "이익률", "ROE"]
    integer_tokens = [
        "수량",
        "체결가",
        "평단",
        "현재가",
        "진입가",
        "평가금액",
        "평가손익",
        "표본수",
        "행 수",
        "종목 수",
        "보유일수",
        "충족표본수",
        "비충족표본수",
        "매출",
        "영업이익",
        "당기순이익",
        "순이익",
        "자산총계",
        "자본총계",
        "부채총계",
        "거래량",
        "시가총액",
    ]
    for col in out.columns:
        if not pd.api.types.is_numeric_dtype(out[col]):
            continue
        label = str(col)
        if any(token in label for token in percent_tokens):
            out[col] = out[col].map(lambda x: "-" if pd.isna(x) else f"{float(x) * 100:.2f}%")
        elif any(token in label for token in integer_tokens):
            out[col] = out[col].map(lambda x: "-" if pd.isna(x) else f"{int(round(float(x))):,}")
        elif label.endswith("점수") or label in {"확신점수", "우선점수"}:
            out[col] = out[col].map(lambda x: "-" if pd.isna(x) else f"{float(x):.3f}")
    styled = out.style.applymap(style_signal_cell)
    st.dataframe(styled, hide_index=True, use_container_width=True, height=height)


def set_flash(message: str, level: str = "success") -> None:
    st.session_state["flash_message"] = {"message": message, "level": level}


def show_flash() -> None:
    if "flash_message" in st.session_state:
        payload = st.session_state.pop("flash_message")
        if isinstance(payload, str):
            st.success(payload)
            return
        level = str(payload.get("level", "success"))
        message = str(payload.get("message", ""))
        if level == "error":
            st.error(message)
        elif level == "warning":
            st.warning(message)
        else:
            st.success(message)


def show_last_command_output() -> None:
    output = st.session_state.get("last_command_output")
    progress = read_pipeline_progress()
    sync_pipeline_history(progress)
    stdout_path, stderr_path = _pipeline_output_paths(progress)
    if not output and stderr_path.exists():
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace").strip() if stdout_path.exists() else ""
        output = (stdout + "\n" + stderr).strip()
    if output:
        with st.expander("최근 실행 로그", expanded=False):
            st.code(output)
    render_pipeline_history()


def render_pipeline_history(limit: int = 10) -> None:
    progress = read_pipeline_progress()
    sync_pipeline_history(progress)
    history = _pipeline_history_df()
    if history.empty:
        return
    show = history.head(limit).copy()
    show = show.rename(
        columns={
            "started_at": "시작",
            "finished_at": "종료",
            "status": "상태",
            "description": "작업",
            "duration_seconds": "소요(초)",
            "stage": "단계",
            "detail": "상세",
        }
    )
    for col in ["run_id", "updated_at", "percent", "pid", "command", "stdout_path", "stderr_path"]:
        if col in show.columns:
            show = show.drop(columns=[col])
    with st.expander("최근 실행 이력", expanded=False):
        st.dataframe(show, hide_index=True, use_container_width=True, height=min(380, 40 + len(show) * 35))


def _format_status_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        dt = datetime.fromisoformat(text)
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return text


def _telegram_job_action_label(action: str) -> str:
    mapping = {
        "run_refresh_data": "증분최신화",
        "run_refresh_incremental": "증분최신화",
        "run_refresh_full": "전체증분최신화",
        "run_refresh_full_incremental": "전체증분최신화",
        "run_fast_alert": "fast alert",
        "run_streamlit_on": "스트림릿 시작",
        "run_streamlit_off": "스트림릿 종료",
        "run_bridge_off": "브리지 종료",
    }
    return mapping.get(str(action or "").strip(), str(action or "").strip() or "Run")


def _process_running_pattern(pattern: str) -> bool:
    return _python_process_running(pattern)


def _read_active_telegram_job() -> dict[str, Any]:
    if not TELEGRAM_JOB_LOG_PATH.exists():
        return {}
    try:
        df = pd.read_csv(TELEGRAM_JOB_LOG_PATH, dtype=str).fillna("")
    except Exception:
        return {}
    if df.empty or "job_id" not in df.columns or "status" not in df.columns:
        return {}
    if "created_at" in df.columns:
        df["created_at_dt"] = pd.to_datetime(df["created_at"], errors="coerce")
        df = df.sort_values(["created_at_dt", "job_id"], ascending=[True, True], kind="stable")
    latest = df.groupby("job_id", as_index=False).tail(1).copy()
    latest["status"] = latest["status"].astype(str).str.strip().str.lower()
    active = latest[latest["status"] == "started"].copy()
    if active.empty:
        return {}
    if not _process_running_pattern("new_strategy.run_signal_pipeline"):
        return {}
    if "created_at_dt" in active.columns:
        active = active.sort_values(["created_at_dt", "job_id"], ascending=[False, False], kind="stable")
    row = active.iloc[0]
    return {
        "status": "running",
        "source": "telegram",
        "action": _telegram_job_action_label(str(row.get("action", ""))),
        "detail": str(row.get("summary", "")).strip(),
        "updated_at": str(row.get("created_at", "")).strip(),
    }


def _pipeline_action_label(progress: dict[str, Any]) -> str:
    command = str(progress.get("command", ""))
    description = str(progress.get("description", "")).strip()
    has_refresh_data = "--refresh-data" in command
    has_refresh_macro = "--refresh-macro" in command
    has_refresh_gold = "--refresh-gold" in command
    has_fast = "--fast-alerts" in command
    if has_refresh_data and not has_refresh_macro and not has_refresh_gold:
        return "증분최신화"
    if has_refresh_data and has_refresh_macro and has_refresh_gold and has_fast:
        return "전체증분최신화"
    if has_refresh_data and has_refresh_macro and has_refresh_gold:
        return "전체재계산"
    if has_fast:
        return "fast alert"
    if "전체 재계산" in description:
        return "전체재계산"
    return description or "Run"


def _build_pipeline_status_card(progress: dict[str, Any]) -> str:
    sync_pipeline_history(progress)
    if not progress:
        return (
            "<div class='ns-status-card idle'>"
            "<div class='ns-status-head'><div class='ns-status-label'>Status</div>"
            "<div class='ns-status-pill'>Run</div></div>"
            "<div class='ns-status-action'>Run</div>"
            "<div class='ns-status-caption'>대기 중</div></div>"
        )
    status = str(progress.get("status", "")).strip().lower()
    stage = str(progress.get("stage", "")).strip()
    detail = str(progress.get("detail", "")).strip()
    action = html.escape(_pipeline_action_label(progress))
    updated_at = _format_status_timestamp(progress.get("updated_at"))
    finished_at = _format_status_timestamp(progress.get("finished_at"))
    duration_seconds = _safe_int(progress.get("duration_seconds"), 0)
    duration_text = f"{duration_seconds // 60}분 {duration_seconds % 60}초" if duration_seconds > 0 else ""

    if status in {"starting", "running"}:
        captions = [f"백그라운드 실행 중 · {updated_at}"]
        if stage and stage != "-":
            captions.append(stage)
        return (
            "<div class='ns-status-card running'>"
            "<div class='ns-status-head'><div class='ns-status-label'>Status</div>"
            "<div class='ns-status-pill running'>Running</div></div>"
            f"<div class='ns-status-action'>{action}</div>"
            f"<div class='ns-status-caption'>{html.escape(' · '.join(captions))}</div>"
            "</div>"
        )
    if status == "failed":
        captions = []
        if detail:
            captions.append(detail)
        if stage and stage != detail:
            captions.append(stage)
        if updated_at != "-":
            captions.append(f"업데이트 {updated_at}")
        return (
            "<div class='ns-status-card failed'>"
            "<div class='ns-status-head'><div class='ns-status-label'>Status</div>"
            "<div class='ns-status-pill failed'>Failed</div></div>"
            f"<div class='ns-status-action'>{action}</div>"
            f"<div class='ns-status-caption'>{html.escape(' · '.join(captions) or '최근 실행이 실패했습니다')}</div>"
            "</div>"
        )
    captions = []
    if finished_at != "-":
        captions.append(f"마지막 완료 {finished_at}")
    if duration_text:
        captions.append(f"소요 {duration_text}")
    return (
        "<div class='ns-status-card idle'>"
        "<div class='ns-status-head'><div class='ns-status-label'>Status</div>"
        "<div class='ns-status-pill'>Run</div></div>"
        "<div class='ns-status-action'>Run</div>"
        f"<div class='ns-status-caption'>{html.escape(' · '.join(captions) or '대기 중')}</div>"
        "</div>"
    )


def render_pipeline_progress() -> None:
    st.markdown(_build_pipeline_status_card(read_pipeline_progress()), unsafe_allow_html=True)


def render_operation_panel(data: dict[str, Any]) -> None:
    cfg = load_default_config(data["meta"])
    strategy_id = str(cfg.get("strategy_id", "earnings_pti_v2"))
    trend_mode = str(cfg.get("trend_mode", "optimal_ma_v2"))
    monthly_buy = _safe_float(cfg.get("monthly_buy_threshold"), 0.0)
    weekly_sell = _safe_float(cfg.get("weekly_sell_threshold"), -0.05)
    last_decision = data["decision"].sort_values("date").iloc[-1] if not data["decision"].empty else None
    regime = market_state_label(str(last_decision.get("market_regime", "unknown"))) if last_decision is not None else "-"
    exposure = _safe_float(last_decision.get("exposure"), float("nan")) if last_decision is not None else float("nan")
    target_positions = _safe_int(last_decision.get("target_positions"), 0) if last_decision is not None else 0
    latest_signal_date = str(pd.to_datetime(data["signals_fast"]["date"], errors="coerce").max().date()) if not data["signals_fast"].empty else "-"

    st.subheader("전략보드")
    cols = st.columns(3)
    with cols[0]:
        st.markdown("**전략 기준**")
        st.markdown(
            "\n".join(
                [
                    f"- 기본안: `월봉매수 / 주봉매도 / buy_{monthly_buy:.0%}__sell_{weekly_sell:.0%}`",
                    f"- strategy_id: `{strategy_id}`",
                    f"- trend_mode: `{trend_mode}`",
                    f"- fast 최신일: `{latest_signal_date}`",
                ]
            )
        )
    with cols[1]:
        st.markdown("**운영 스케줄**")
        st.markdown(
            "\n".join(
                [
                    "- `07:00` KRX 보조 데이터 갱신",
                    "- `08:20~08:25` 프리장 1차 메시지 (`08:10` 슬롯 기준)",
                    "- `09:20~09:25` 본장 2차 메시지 (`09:10` 슬롯 기준)",
                    "- `08:10`부터 30분마다 전종목 Kiwoom 갱신 + fast 변화 알림",
                    "- `20:10` 장후 EOD 수집 + 마감 요약",
                ]
            )
        )
    with cols[2]:
        st.markdown("**현재 운용 상태**")
        st.markdown(
            "\n".join(
                [
                    f"- 시장 상태: `{regime}`",
                    f"- 운용강도: `{exposure:.2f}`" if not pd.isna(exposure) else "- 운용강도: `-`",
                    f"- 목표 보유 수: `{target_positions}`개",
                    f"- 최근 작업: `{data['schedule_state'].get('last_action', '-')}`",
                ]
            )
        )
    st.markdown("**최종 의사결정 매핑**")
    mapping_cols = st.columns(5)
    mapping_specs = [
        ("BUY", ["미보유", "월봉 신규 상향돌파", "주봉 정상", "재무 통과", "주가 위치 양호"]),
        ("BUY_WATCH", ["미보유", "월봉 유지상방 또는 신규 상향돌파", "주봉 경계 또는 가격 부담", "추가 확인 후 진입"]),
        ("HOLD", ["보유", "월봉 유지상방", "주봉 정상", "기본 보유 유지"]),
        ("SELL_WATCH", ["보유", "월봉은 유지상방", "주봉 매도경계", "비중축소 우선 검토"]),
        ("SELL", ["보유", "주봉 매도트리거 또는 월봉 하향 전환", "손절/재무 훼손 포함", "청산 우선"]),
    ]
    for col, (title, lines) in zip(mapping_cols, mapping_specs):
        with col:
            st.markdown(f"**{signal_label(title)}**")
            st.markdown("\n".join([f"- {line}" for line in lines]))


def render_operations_page(data: dict[str, Any]) -> None:
    render_page_heading("전략보드", kicker="Operations", subtitle="V2 전략 기준, 운영 스케줄, 현재 운용 상태를 확인합니다.")
    render_operation_panel(data)
    st.markdown("<div class='ns-section-divider'></div>", unsafe_allow_html=True)
    with st.expander("V2 전략 정리", expanded=True):
        render_strategy_logic(load_default_config(data["meta"]))
        render_term_notes()
    with st.expander("데이터 최신 상태", expanded=False):
        runtime_health = build_runtime_health_table(data)
        render_table(runtime_health)
        left, right = st.columns(2)
        with left:
            st.markdown("#### 최신화 메타데이터")
            st.json(data["refresh_meta"] or {})
        with right:
            st.markdown("#### fast alert 메타데이터")
            st.json(data["fast_meta"] or {})
    show_last_command_output()


def build_inventory(data: dict[str, Any]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    latest_dates = runtime_latest_dates(data)
    price_meta = _read_json(data_path("price_panel_meta.json")).get("bounds", {})
    feature_meta = _read_json(data_path("feature_daily_meta.json")).get("bounds", {})
    health = data["health"]
    health_map = {str(row.get("dataset", "")): row for _, row in health.iterrows()} if not health.empty else {}
    records.extend(
        [
            {
                "데이터셋": "주가 통합 패널",
                "행 수": _safe_int(price_meta.get("rows")),
                "시작일": price_meta.get("date_min", "-"),
                "최신일": latest_dates["price_latest"],
                "종목 수": _safe_int(price_meta.get("codes")),
                "설명": "일별 가격, 거래대금, 시가총액 기준 원천 패널",
            },
            {
                "데이터셋": "전략 입력셋",
                "행 수": _safe_int(feature_meta.get("rows")),
                "시작일": feature_meta.get("date_min", "-"),
                "최신일": latest_dates["feature_latest"],
                "종목 수": _safe_int(feature_meta.get("codes")),
                "설명": "주가 + 재무 + 매크로를 결합한 의사결정 입력셋",
            },
            {
                "데이터셋": "매크로",
                "행 수": _safe_int(health_map.get("macro_daily", {}).get("rows")),
                "시작일": health_map.get("macro_daily", {}).get("date_min", "-"),
                "최신일": latest_dates["macro_latest"],
                "종목 수": 0,
                "설명": "KOSPI, VIX, 환율, 금리, 금 가격 등 공통 매크로",
            },
            {
                "데이터셋": "재무",
                "행 수": _safe_int(health_map.get("fundamental_quarterly_multi", {}).get("rows")),
                "시작일": health_map.get("fundamental_quarterly_multi", {}).get("date_min", "-"),
                "최신일": latest_dates["fundamental_latest"],
                "종목 수": _safe_int(health_map.get("fundamental_quarterly_multi", {}).get("codes")),
                "설명": "공시일 기준 분기 재무 데이터",
            },
            {
                "데이터셋": "통합 DB",
                "행 수": _safe_int(health_map.get("market_data_db", {}).get("fact_price_daily")),
                "시작일": health_map.get("market_data_db", {}).get("price_date_max", "-"),
                "최신일": health_map.get("market_data_db", {}).get("fund_date_max", "-"),
                "종목 수": _safe_int(health_map.get("market_data_db", {}).get("dim_symbol")),
                "설명": "가격, 매크로, 재무를 적재한 SQLite 저장소",
            },
        ]
    )
    live_quotes = data["live_quotes"]
    if not live_quotes.empty:
        live_quotes["date"] = pd.to_datetime(live_quotes["date"], errors="coerce")
        records.append(
            {
                "데이터셋": "live_quotes 잔존 파일",
                "행 수": len(live_quotes),
                "시작일": str(live_quotes["date"].min().date()),
                "최신일": str(live_quotes["date"].max().date()),
                "종목 수": live_quotes["code"].astype(str).str.zfill(6).nunique(),
                "설명": "예전/옵션성 현재가 캐시. 현재 기본 fast 기준은 08:10부터 30분 전종목 갱신",
            }
        )
    signals = data["signals"]
    if not signals.empty:
        signals["date"] = pd.to_datetime(signals["date"], errors="coerce")
        records.append(
            {
                "데이터셋": "최신 전략 신호",
                "행 수": len(signals),
                "시작일": str(signals["date"].min().date()),
                "최신일": str(signals["date"].max().date()),
                "종목 수": signals["code"].astype(str).str.zfill(6).nunique(),
                "설명": "현재 의사결정에 직접 쓰는 최신 신호",
            }
        )
    return pd.DataFrame(records)


def build_cards(signal_df: pd.DataFrame, decision_df: pd.DataFrame, data: dict[str, Any]) -> list[dict[str, str]]:
    latest_date = str(pd.to_datetime(signal_df["date"]).max().date()) if not signal_df.empty else "-"
    fast_latest_date = "-"
    if not data.get("signals_fast", pd.DataFrame()).empty:
        fast_latest_date = str(pd.to_datetime(data["signals_fast"]["date"], errors="coerce").max().date())
    execution_window = is_execution_window()
    execution_date = latest_date if execution_window else next_business_day(latest_date)
    regime = "unknown"
    exposure = 1.0
    target_positions = 0
    if not decision_df.empty:
        last = decision_df.sort_values("date").iloc[-1]
        regime = str(last.get("market_regime", "unknown"))
        exposure = _safe_float(last.get("exposure"), 1.0)
        target_positions = _safe_int(last.get("target_positions"), 0)
    regime_label = market_state_label(regime)
    intensity_label = operating_intensity_label(exposure)
    counts = signal_df["display_signal"].value_counts().to_dict() if not signal_df.empty else {}
    buy_count = _display_signal_count(counts, "BUY")
    watch_count = _display_signal_count(counts, "BUY_WATCH")
    hold_count = _display_signal_count(counts, "HOLD")
    reduce_count = _display_signal_count(counts, "SELL_WATCH")
    sell_count = _display_signal_count(counts, "SELL")

    def _decision_item(label: str, count: int) -> str:
        cls = "active" if count > 0 else "inactive"
        return f"<span class='ns-decision-item {cls}'>{html.escape(label)} {count}</span>"

    refresh_meta = data["refresh_meta"]
    latest_refresh = refresh_meta.get("price_date_max") or refresh_meta.get("latest_price_date") or latest_date
    return [
        {
            "label": "분석일자 / 실행일자",
            "value": f"분석 {latest_date} / 실행 {execution_date}",
            "caption": f"전략 {latest_date} · 데이터 {latest_refresh} · fast {fast_latest_date}",
        },
        {
            "label": "시장 상태",
            "value": regime_label,
            "caption": f"운용강도 {intensity_label} · 노출 {exposure:.2f} · 목표 {target_positions}개",
        },
        {
            "label": "현재 의사결정",
            "value_html": " · ".join(
                [
                    _decision_item("매수", buy_count),
                    _decision_item("관심", watch_count),
                    _decision_item("보유", hold_count),
                ]
            ),
            "caption_html": " · ".join(
                [
                    _decision_item("축소검토", reduce_count),
                    _decision_item("매도", sell_count),
                ]
            ),
        },
    ]


def render_cards(cards: list[dict[str, str]]) -> None:
    ratios = [1.35, 0.95, 1.15] if len(cards) == 3 else [1.0] * len(cards)
    cols = st.columns(ratios)
    for col, card in zip(cols, cards):
        with col:
            label = html.escape(str(card["label"]))
            if "value_html" in card:
                value = str(card["value_html"]).replace("\n", "<br>")
            else:
                value = html.escape(str(card["value"])).replace("\n", "<br>")
            if "caption_html" in card:
                caption = str(card["caption_html"]).replace("\n", "<br>")
            else:
                caption = html.escape(str(card["caption"])).replace("\n", "<br>")
            st.markdown(
                f"""
                <div class="ns-card">
                  <div class="ns-card-label">{label}</div>
                  <div class="ns-card-value">{value}</div>
                  <div class="ns-card-caption">{caption}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_architecture() -> None:
    cols = st.columns([1.2, 0.2, 1.2, 0.2, 1.2, 0.2, 1.2])
    steps = [
        ("1. 원천 데이터", ["KRX 일별 주가", "키움 전종목 현재가(30분)", "DART 재무 공시", "매크로·금 데이터"]),
        ("2. 정제 레이어", ["price_panel.csv", "macro_daily.csv", "fundamental_quarterly_multi.csv", "장 종료 후 종가 기준 재정리"]),
        ("3. 전략 엔진", ["실적 중심 코어 엔진", "타이밍 보정", "리스크 게이트", "fast alert / full backtest"]),
        ("4. 전달 채널", ["Streamlit 대시보드", "텔레그램 브리지", "07:00 KRX 보조 갱신", "08:10부터 30분 점검", "20:10 장후 마감 요약"]),
    ]
    step_idx = 0
    for idx, col in enumerate(cols):
        with col:
            if idx % 2 == 0:
                title, items = steps[step_idx]
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    for item in items:
                        st.markdown(f"- {item}")
                step_idx += 1
            else:
                st.markdown("<div style='text-align:center;font-size:28px;padding-top:56px;color:#64748b;'>→</div>", unsafe_allow_html=True)


def current_macro_snapshot(macro_df: pd.DataFrame) -> pd.DataFrame:
    if macro_df.empty:
        return pd.DataFrame()
    latest = macro_df.dropna(subset=["date"]).sort_values("date").iloc[-1]
    return pd.DataFrame(
        [
            {"지표": "KOSPI", "값": latest.get("kospi"), "최신일": latest["date"].date()},
            {"지표": "VIX*", "값": latest.get("vix"), "최신일": latest["date"].date()},
            {"지표": "USD/KRW", "값": latest.get("usdkrw"), "최신일": latest["date"].date()},
            {"지표": "미국 10년 금리", "값": latest.get("us10y"), "최신일": latest["date"].date()},
            {"지표": "한국 10년 금리", "값": latest.get("kr10y"), "최신일": latest["date"].date()},
            {"지표": "국내 금 가격", "값": latest.get("gold_kr_close"), "최신일": latest["date"].date()},
        ]
    )


def render_strategy_logic(cfg: dict[str, Any]) -> None:
    st.markdown(
        f"""
### 전략 로직 상세

1. **V2 기본안**
   - 기본 전략은 **월봉매수 / 주봉매도 / buy_0%__sell_-5%** 입니다.
   - 방향 결정은 종목별 **최적 월이평선**이 메인입니다.
   - **월봉 신규 상향돌파**일 때만 `BUY`로 진입합니다.
   - 이미 전달에도 월이평 위였던 종목은 `BUY`가 아니라 `BUY_WATCH` 또는 `HOLD`로 해석합니다.
   - 보유 중에는 **최적 주이평선 -5% 이탈**을 우선 매도 기준으로 봅니다.

2. **축 역할 분리**
   - **최적 MA**: 메인 축. 방향과 진입/청산 기준을 정합니다.
   - **주가위치**: 보조 축. 과열, 추격 여부, 분할 진입 강도를 조절합니다.
   - **매크로**: 보조 축. 시장 상태와 운용강도를 조절합니다.
   - **재무**: 보조 축. 종목 통과 여부와 해석 근거를 제공합니다.

3. **매크로 해석**
   - 환율과 VIX만으로 시장 상태를 나눕니다.
   - `정상구간 / 주의구간 / 방어구간`
   - 운용강도는 **100% / 70% / 40%** 기준으로 봅니다.
   - 매크로는 종목을 부정하는 축이 아니라, 같은 종목이라도 얼마나 조심해서 들어갈지 정하는 축입니다.

4. **주가위치 / 재무 역할**
   - 주가위치는 **추격 금지 / 과열 경계 / 초기 관찰** 판단에 씁니다.
   - 재무는 **수익성 / 성장성 / 지속성 / 안정성** 4블록으로 해석합니다.
   - 즉 V2는 단일 점수보다 `왜 지금 사는지/왜 기다리는지/왜 줄이는지`를 설명하는 구조를 우선합니다.

5. **운영 원칙**
   - 장 시작 전에는 **07:00에 KRX 보조 데이터 갱신**을 한 번 수행합니다.
   - 장중 fast alert는 **08:10부터 30분마다 전종목 Kiwoom 갱신** 후 계산합니다.
   - 프리장 `08:20` 브리핑은 `08:10` 슬롯 결과, 본장 `09:20` 브리핑은 `09:10` 슬롯 결과를 사용합니다.
   - 장후에는 **20:10에 EOD 수집과 마감 요약**을 한 번 더 수행합니다.
   - 상시 실시간 시세수집은 기본 운용에서 사용하지 않습니다.
   - 데이터가 없으면 기본값으로 대체하지 않고 `없음`으로 명시합니다.

6. **최종 의사결정 매핑**
   - `BUY`: 미보유 + 월봉 신규 상향돌파 + 주봉 정상 + 재무 통과 + 주가 위치 양호
   - `BUY_WATCH`: 미보유 + 월봉 유지상방 또는 신규 상향돌파 + 주봉 경계/가격 부담
   - `HOLD`: 보유 + 월봉 유지상방 + 주봉 정상
   - `SELL_WATCH`: 보유 + 월봉 유지상방 + 주봉 매도경계
   - `SELL`: 보유 + 주봉 매도트리거 또는 월봉 하향 전환
        """
    )


def render_term_notes() -> None:
    st.caption("전문용어 주석")
    for note in TERM_NOTES:
        st.caption(f"- {note}")


def decision_text(signal_df: pd.DataFrame, decision_df: pd.DataFrame) -> str:
    if signal_df.empty:
        return "최신 전략 신호가 아직 없습니다."
    counts = signal_df["display_signal"].value_counts().to_dict()
    execution_window = is_execution_window()
    regime = "unknown"
    exposure = 1.0
    if not decision_df.empty:
        last = decision_df.sort_values("date").iloc[-1]
        regime = str(last.get("market_regime", "unknown"))
        exposure = _safe_float(last.get("exposure"), 1.0)
    regime_label = market_state_label(regime)
    intensity_label = operating_intensity_label(exposure)
    return (
        f"현재 시장 상태는 {regime_label}이며 운용강도는 {intensity_label} (노출 {exposure:.2f})입니다. "
        f"신호 분포는 {signal_distribution_text(counts, execution_window=execution_window)}입니다."
    )


def render_signal_detail_panel(
    selected_row: pd.Series,
    data: dict[str, Any],
    context: dict[str, Any],
    *,
    decision_df: pd.DataFrame | None = None,
) -> None:
    latest_price = context.get("latest_price", pd.DataFrame())
    manual_positions = context.get("manual_positions", pd.DataFrame())
    fast_state = context.get("fast_state", pd.DataFrame())

    selected_code = str(selected_row["code"]).zfill(6)
    version_tokens = data["version_tokens"]
    price_df = load_price_history(selected_code, version_tokens["price"])
    price_df, live_info = attach_live_quote(price_df, selected_code, data["live_quotes"])
    fundamental_df = load_fundamental(selected_code, version_tokens["fundamental"])
    macro_df = load_macro(version_tokens["macro"])
    manual_position_row = manual_positions[manual_positions["code"] == selected_code].iloc[-1] if not manual_positions.empty and (manual_positions["code"] == selected_code).any() else None
    fast_position_row = fast_state[fast_state["code"] == selected_code].iloc[-1] if not fast_state.empty and (fast_state["code"] == selected_code).any() else None
    chart_ma_selection = load_optimal_ma_chart_selection(data["version_tokens"]["optimal_ma"])
    chart_ma_rows = chart_ma_selection[chart_ma_selection["code"] == selected_code].copy() if not chart_ma_selection.empty else pd.DataFrame()

    left, right = st.columns([1.7, 1.1])
    with left:
        timeframe = st.radio("차트 기준", ["월봉", "주봉", "일봉"], horizontal=True, key=f"chart_timeframe_{selected_code}")
        tf_key = {"일봉": "daily", "주봉": "weekly", "월봉": "monthly"}[timeframe]
        chart_ma_row = chart_ma_rows[chart_ma_rows["ma_timeframe"] == tf_key].head(1)
        chart_optimal_row = chart_ma_row.iloc[0] if not chart_ma_row.empty else None
        bars = resample_ohlcv(price_df, timeframe, chart_optimal_row).tail(180 if timeframe == "일봉" else 120)
        monthly_chart_row = chart_ma_rows[chart_ma_rows["ma_timeframe"] == "monthly"].head(1)
        monthly_optimal_row = monthly_chart_row.iloc[0] if not monthly_chart_row.empty else None
        chart_domain: tuple[pd.Timestamp, pd.Timestamp] | None = None
        if not bars.empty:
            chart_domain = (pd.to_datetime(bars["date"]).min(), pd.to_datetime(bars["date"]).max())
        st.altair_chart(
            candlestick_chart(bars, f"{selected_row['name']} ({selected_code}) · {timeframe}", x_domain=chart_domain),
            use_container_width=True,
        )

        if timeframe == "월봉":
            monthly_gap = build_monthly_gap_series(price_df, monthly_optimal_row).tail(len(bars) if not bars.empty else 120)
            gap_title = "월봉 이격률"
        else:
            monthly_gap = build_weekly_monthly_gap_series(price_df, monthly_optimal_row).tail(104)
            gap_title = "주별 월봉 이격률"

        if not monthly_gap.empty:
            latest_gap = monthly_gap.iloc[-1]
            st.caption(
                f"{gap_title}: 현재 {_safe_float(latest_gap['gap_pct']):+.2%} / "
                f"최적 월이평 {_safe_int(latest_gap['window'], 0)}"
            )
            st.altair_chart(
                percent_line_chart(monthly_gap, "gap_pct", gap_title, "#7c3aed", x_domain=chart_domain),
                use_container_width=True,
            )
        if not bars.empty:
            st.altair_chart(line_chart(bars, "volume", "거래량", "#7c3aed", x_domain=chart_domain), use_container_width=True)

    with right:
        detail_row = selected_row.copy()
        if decision_df is not None and not decision_df.empty:
            last = decision_df.sort_values("date").iloc[-1]
            detail_row["market_regime"] = str(last.get("market_regime", "unknown"))
            detail_row["market_exposure"] = _safe_float(last.get("exposure"), 1.0)
        detail_row["최적 MA 축"] = detail_row.get("최적 MA 축") or format_v2_ma_axis_summary(detail_row)
        detail_row["주가 위치 축"] = detail_row.get("주가 위치 축") or format_price_axis_summary(detail_row)
        detail_row["재무 축"] = detail_row.get("재무 축") or format_financial_axis_summary(detail_row)
        detail_row["매크로 축"] = detail_row.get("매크로 축") or format_macro_axis_summary(detail_row)
        detail_row["실행 요약"] = detail_row.get("실행 요약") or compact_execution_guide(detail_row, execution_window=is_execution_window())

        if decision_df is not None and not decision_df.empty:
            last = decision_df.sort_values("date").iloc[-1]
            st.caption(
                f"시장 상태: {market_state_label(str(last.get('market_regime', 'unknown')))} / "
                f"운용강도 {operating_intensity_label(_safe_float(last.get('exposure'), 1.0))}"
            )
        current_price = None
        current_basis = "-"
        price_snapshot_row = latest_price[latest_price["code"] == selected_code].head(1)
        if not price_snapshot_row.empty:
            current_price = _safe_float(price_snapshot_row.iloc[0].get("latest_close", price_snapshot_row.iloc[0].get("close")), float("nan"))
            current_basis = format_eod_basis(price_snapshot_row.iloc[0].get("latest_price_date", price_snapshot_row.iloc[0].get("date")))
        elif not price_df.empty:
            last = price_df.iloc[-1]
            current_price = _safe_float(last["close"], float("nan"))
            current_basis = format_eod_basis(last["date"])
        price_execution_guide = build_price_execution_guide(
            detail_row,
            current_price=current_price if current_price is not None and not pd.isna(current_price) else None,
            current_basis=current_basis,
            execution_window=is_execution_window(),
            position_row=manual_position_row if manual_position_row is not None else fast_position_row,
        )
        st.markdown("##### 현재 신호 요약")

        if live_info:
            price_title = "현재가"
            price_value = f"{_safe_float(live_info.get('close')):,.0f}"
            price_caption = f"{live_info.get('quote_time', '-')} / 변동률 {_safe_float(live_info.get('change_pct')):.2f}%"
        elif current_price is not None and not pd.isna(current_price):
            price_title = "종가"
            price_value = f"{_safe_float(current_price):,.0f}"
            price_caption = f"기준일 {html.escape(str(current_basis))}"
        else:
            price_title = "종가"
            price_value = "-"
            price_caption = "-"

        summary_cols = st.columns([1.1, 1.0], gap="small")
        with summary_cols[0]:
            st.markdown(
                f"""
                <div class="ns-mini-card">
                  <div class="ns-mini-label">의사결정</div>
                  <div class="ns-mini-value">{html.escape(str(detail_row["display_signal_ko"]))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with summary_cols[1]:
            st.markdown(
                f"""
                <div class="ns-mini-card price">
                  <div class="ns-mini-label">{html.escape(price_title)}</div>
                  <div class="ns-mini-value">{html.escape(price_value)}</div>
                  <div class="ns-mini-caption">{html.escape(price_caption)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("##### 4축 의견")
        axis_blocks = [
            ("최적 MA", str(detail_row.get("최적 MA 축") or "-")),
            ("주가 위치", str(detail_row.get("주가 위치 축") or "-")),
            ("재무", str(detail_row.get("재무 축") or "-")),
            ("매크로", str(detail_row.get("매크로 축") or "-")),
        ]
        axis_html_parts: list[str] = []
        for title, body in axis_blocks:
            lines = [x.strip() for x in body.splitlines() if x.strip()]
            line_html = []
            for idx, line in enumerate(lines):
                klass = "ns-axis-line" if idx == 0 else "ns-axis-line subtle"
                line_html.append(f"<div class='{klass}'>{html.escape(line)}</div>")
            axis_body_html = "".join(line_html) if line_html else "<div class='ns-axis-line subtle'>-</div>"
            axis_html_parts.append(
                "<div class='ns-axis-card'>"
                f"<div class='ns-axis-title'>{html.escape(title)}</div>"
                f"{axis_body_html}"
                "</div>"
            )
        st.markdown(f"<div class='ns-axis-grid'>{''.join(axis_html_parts)}</div>", unsafe_allow_html=True)

        guide_lines = [x.strip() for x in str(price_execution_guide).replace(" / ", "\n").splitlines() if x.strip()]
        st.markdown(
            """
            <div style="height:0.25rem"></div>
            """,
            unsafe_allow_html=True,
        )
        guide_html = "".join(f"<div class='ns-guide-line'>{html.escape(line)}</div>" for line in guide_lines) if guide_lines else "<div class='ns-guide-line'>-</div>"
        st.markdown(
            f"""
            <div class="ns-guide-card">
              <div class="ns-guide-title">실행 가이드</div>
              {guide_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

    tabs = st.tabs(["재무 데이터", "공통 매크로", "업데이트 메타"])
    with tabs[0]:
        if fundamental_df.empty:
            st.info("선택한 종목의 재무 데이터가 없습니다.")
        else:
            latest_fund = fundamental_df.iloc[-1]
            st.markdown("##### 재무 4축 요약")
            financial_blocks = build_financial_blocks(selected_row, fundamental_df)
            block_cols = st.columns(4)
            for col, block in zip(block_cols, financial_blocks):
                with col:
                    with st.container(border=True):
                        st.markdown(f"**{block['title']}**")
                        for line in str(block["body"]).splitlines():
                            st.caption(line)
                        if str(block.get("note") or "").strip():
                            st.caption(f"주석: {block['note']}")
            st.markdown("##### 원천 분기 재무")
            cards = st.columns(4)
            with cards[0]:
                st.metric("최근 분기 매출", _format_large_number(latest_fund.get("분기매출액")))
            with cards[1]:
                st.metric("최근 분기 영업이익", _format_large_number(latest_fund.get("분기영업이익")))
            with cards[2]:
                st.metric("최근 분기 당기순이익", _format_large_number(latest_fund.get("분기당기순이익")))
            with cards[3]:
                st.metric("최근 분기 영업이익률", f"{_safe_float(latest_fund.get('분기영업이익률')):.2%}")
            raw_fund_view = fundamental_df[["분기", "공시일", "분기매출액", "분기영업이익", "분기당기순이익", "분기영업이익률"]].tail(8).sort_values("공시일", ascending=False).copy()
            raw_fund_view["공시일"] = pd.to_datetime(raw_fund_view["공시일"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("-")
            render_table(raw_fund_view)
    with tabs[1]:
        macro_snapshot = current_macro_snapshot(macro_df)
        if not macro_snapshot.empty:
            render_table(macro_snapshot)
        recent_macro = macro_df.sort_values("date").tail(120)
        macro_titles = {"kospi": "KOSPI", "vix": "VIX", "usdkrw": "USD/KRW"}
        for metric, color in [("kospi", "#0f766e"), ("vix", "#dc2626"), ("usdkrw", "#1d4ed8")]:
            if metric in recent_macro.columns and not recent_macro[metric].dropna().empty:
                st.altair_chart(
                    line_chart(
                        recent_macro,
                        metric,
                        macro_titles.get(metric, metric.upper()),
                        color,
                        zero_baseline=False,
                    ),
                    use_container_width=True,
                )
    with tabs[2]:
        st.write(
            {
                "주가 최신일": data["refresh_meta"].get("price_date_max") or data["refresh_meta"].get("latest_price_date"),
                "feature 최신일": data["refresh_meta"].get("feature_date_max"),
                "fast alert 최신일": data["fast_meta"].get("latest_signal_date"),
                "KRX 보조 갱신": "07:00 / 장전 보조 데이터 갱신",
                "fast 갱신 방식": "08:10부터 30분마다 전종목 Kiwoom 갱신",
                "장후 마감 처리": "20:10 / EOD 수집 + 마감 요약",
                "최근 작업": data["schedule_state"].get("last_action", "-"),
            }
        )


def render_today_decision(signal_df: pd.DataFrame, decision_df: pd.DataFrame, data: dict[str, Any], cfg: dict[str, Any]) -> None:
    st.subheader("오늘의 의사결정")
    st.write(decision_text(signal_df, decision_df))
    render_cards(build_cards(signal_df, decision_df, data))
    st.markdown("<div class='ns-section-divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='ns-section-label'>의사결정 표</div>", unsafe_allow_html=True)
    st.caption("V2 기준: `월봉매수 / 주봉매도 / buy_0%__sell_-5%`. 표는 `최적 MA / 주가 위치 / 재무 / 매크로` 4개 축을 함께 요약합니다.")
    if signal_df.empty:
        st.info("최신 전략 신호가 없습니다.")
        return

    signal_df, context = enrich_signal_display(signal_df, data)
    signal_df = finalize_signal_axes(signal_df, data=data, context=context, decision_df=decision_df)

    st.caption(f"표시 종목 {len(signal_df)}건")
    view_df = signal_df[
        [
            "display_signal_ko",
            "code",
            "name",
            "industry",
            "latest_close",
            "latest_volume",
            "근거 기준 분기",
            "기준 공시일",
            "최적 MA 축",
            "주가 위치 축",
            "재무 축",
            "매크로 축",
            "리스크",
            "실행 요약",
        ]
    ].rename(
        columns={
            "display_signal_ko": "의사결정",
            "code": "종목코드",
            "name": "종목명",
            "industry": "업종",
            "최적 MA 축": "최적 MA",
            "주가 위치 축": "주가 위치",
            "재무 축": "재무",
            "매크로 축": "매크로",
            "실행 요약": "실행 가이드",
        }
    )
    render_decision_summary_table(view_df)

    st.markdown("##### 종목 선택")
    options = [(row["code"], f"{row['display_signal_ko']} · {row['code']} {row['name']}") for _, row in signal_df.iterrows()]
    compact_labels = {
        row["code"]: (
            f"{str(row['name'])[:10]}{'…' if len(str(row['name'])) > 10 else ''}"
        )
        for _, row in signal_df.iterrows()
    }
    state_key = "decision_selected_code"
    if state_key not in st.session_state and options:
        st.session_state[state_key] = options[0][0]
    if options and st.session_state.get(state_key) not in [code for code, _ in options]:
        st.session_state[state_key] = options[0][0]

    button_cols = st.columns(min(6, max(1, len(options))))
    for idx, (code, _label) in enumerate(options):
        with button_cols[idx % len(button_cols)]:
            if st.button(compact_labels.get(code, code), key=f"decision_pick_{code}", use_container_width=True):
                st.session_state[state_key] = code

    selected_code = st.selectbox(
        "상세 분석 종목",
        [code for code, _ in options],
        index=[code for code, _ in options].index(st.session_state[state_key]),
        format_func=lambda x: next((label for code, label in options if code == x), x),
        key="decision_detail_select",
    )
    st.session_state[state_key] = selected_code
    selected_row = signal_df[signal_df["code"] == selected_code].iloc[0]
    render_signal_detail_panel(selected_row, data, context, decision_df=decision_df)


def render_strategy_report(data: dict[str, Any]) -> None:
    cfg = load_default_config(data["meta"])
    manual_positions = load_manual_positions_snapshot(data["version_tokens"]["output"])
    latest_price = load_price_latest_snapshot(data["version_tokens"]["price"])
    real_holding_codes = set()
    if not manual_positions.empty:
        real_holding_codes |= set(manual_positions["code"].astype(str).str.zfill(6))
    source_signal_df = select_v2_decision_signals(
        data["signals"],
        data.get("signals_fast", pd.DataFrame()),
        real_holding_codes=real_holding_codes,
    )
    source_signal_df = append_manual_holding_placeholders(
        source_signal_df,
        real_holding_codes=real_holding_codes,
        manual_positions=manual_positions,
        latest_price=latest_price,
        decision_df=data["decision_fast"] if not data.get("decision_fast", pd.DataFrame()).empty else data["decision"],
    )
    signal_df = prepare_signal_display(source_signal_df, cfg, real_holding_codes=real_holding_codes)
    if not signal_df.empty:
        monthly_new_buy = signal_df.get("v2_month_buy_cross", pd.Series(False, index=signal_df.index)).fillna(False)
        signal_df = signal_df[signal_df["is_real_holding"] | monthly_new_buy].copy()
        signal_df = signal_df.sort_values(["is_real_holding", "signal_rank", "code"], ascending=[False, True, True]).reset_index(drop=True)
    decision_df = data["decision_fast"] if not data.get("decision_fast", pd.DataFrame()).empty else data["decision"]
    render_page_heading(
        "의사결정",
        kicker="Today",
        subtitle="보유 종목 판단과 신규 매수·매도 후보만 집중해서 봅니다.",
    )
    show_flash()
    render_today_decision(signal_df, decision_df, data, cfg)


def render_universe_analysis(data: dict[str, Any]) -> None:
    cfg = load_default_config(data["meta"])
    decision_df = data["decision_fast"] if not data.get("decision_fast", pd.DataFrame()).empty else data["decision"]
    feature_latest = load_feature_latest_snapshot(data["version_tokens"]["output"])
    latest_price = load_price_latest_snapshot(data["version_tokens"]["price"])
    signal_lookup = merge_latest_signal_sources(data["signals"], data.get("signals_fast", pd.DataFrame()))
    render_page_heading(
        "전종목 분석",
        kicker="Universe",
        subtitle="코스피 전체 종목을 검색·필터·정렬로 탐색하고, 신호가 없는 종목까지 포함해 상세 차트로 바로 내려갑니다.",
    )
    if feature_latest.empty:
        st.info("코스피 전체 분석 스냅샷이 없습니다.")
        return

    signal_df = feature_latest.copy()
    signal_df["code"] = signal_df["code"].astype(str).str.zfill(6)
    if "market" not in signal_df.columns:
        signal_df["market"] = "전체"
    signal_df["industry"] = signal_df.get("industry", pd.Series(index=signal_df.index)).fillna("-")
    signal_df["latest_close"] = pd.to_numeric(signal_df.get("close"), errors="coerce")
    signal_df["latest_volume"] = pd.to_numeric(signal_df.get("volume"), errors="coerce")
    signal_df["latest_market_cap"] = pd.to_numeric(signal_df.get("market_cap"), errors="coerce")
    signal_df["latest_price_date"] = pd.to_datetime(signal_df.get("date"), errors="coerce")

    if not signal_lookup.empty:
        signal_lookup = signal_lookup.copy()
        signal_lookup["code"] = signal_lookup["code"].astype(str).str.zfill(6)
        if "date" in signal_lookup.columns:
            signal_lookup["signal_date"] = pd.to_datetime(signal_lookup["date"], errors="coerce")
        merge_cols = [col for col in signal_lookup.columns if col not in {"name", "industry", "close", "date", "market"}]
        signal_df = signal_df.merge(signal_lookup[merge_cols], on="code", how="left")

    required_signal_cols = [
        "signal",
        "strategy_id",
        "conviction_score",
        "holding_horizon",
        "reason_1",
        "reason_2",
        "reason_3",
        "risk_flag",
        "stop_rule",
        "target_exit_rule",
        "intraday_action_guide",
        "next_day_action_guide",
        "v2_month_window",
        "v2_month_period_dist",
        "v2_week_window",
        "v2_week_period_dist",
        "v2_month_buy_ready",
        "v2_month_buy_cross",
        "v2_month_sell_cross",
        "v2_month_above_maintain",
        "v2_week_sell_trigger",
        "v2_week_sell_watch",
    ]
    for col in required_signal_cols:
        if col not in signal_df.columns:
            signal_df[col] = np.nan

    execution_window = is_execution_window()
    signal_df["has_signal"] = signal_df["signal"].astype(str).str.strip().ne("") & signal_df["signal"].notna()
    signal_df["display_signal"] = np.where(
        signal_df["has_signal"],
        signal_df.apply(lambda row: classify_signal(row, cfg), axis=1),
        "NO_SIGNAL",
    )
    signal_df["display_signal_ko"] = np.where(
        signal_df["display_signal"].eq("NO_SIGNAL"),
        "신호없음",
        signal_df["display_signal"].map(lambda x: signal_label(x, execution_window=execution_window)),
    )
    universe_signal_order = {**SIGNAL_ORDER, "NO_SIGNAL": 9}
    signal_df["signal_rank"] = signal_df["display_signal"].map(universe_signal_order).fillna(99)
    manual_positions = load_manual_positions_snapshot(data["version_tokens"]["output"])
    real_holding_codes = set()
    if not manual_positions.empty:
        real_holding_codes |= set(manual_positions["code"].astype(str).str.zfill(6))
    signal_df["is_real_holding"] = signal_df["code"].isin(real_holding_codes)
    signal_df["active_execution_guide"] = np.where(
        signal_df["display_signal"].eq("NO_SIGNAL"),
        "최신 전략 신호 없음",
        signal_df.apply(lambda row: resolve_action_guide(row, execution_window=execution_window), axis=1),
    )
    signal_df = signal_df.sort_values(["signal_rank", "is_real_holding", "code"], ascending=[True, False, True]).reset_index(drop=True)

    filter_cols = st.columns([1.4, 0.8, 0.95, 1.2, 0.9, 0.9, 0.8])
    with filter_cols[0]:
        query = st.text_input("검색", value="", placeholder="종목명, 코드, 업종")
    with filter_cols[1]:
        markets = ["전체"] + sorted([x for x in signal_df["market"].dropna().astype(str).unique().tolist() if x.strip()])
        market_filter = st.selectbox("시장", markets, index=0)
    with filter_cols[2]:
        signal_scope = st.selectbox("신호상태", ["전체", "신호 종목만", "신호없음만"], index=0)
    with filter_cols[3]:
        signal_filter = st.multiselect(
            "의사결정",
            options=["BUY", "BUY_WATCH", "HOLD", "SELL_WATCH", "SELL", "NO_SIGNAL"],
            default=["BUY", "BUY_WATCH", "HOLD", "SELL_WATCH", "SELL", "NO_SIGNAL"],
            format_func=lambda x: "신호없음" if x == "NO_SIGNAL" else signal_label(x, execution_window=execution_window),
        )
    with filter_cols[4]:
        holding_filter = st.selectbox("보유여부", ["전체", "보유만", "미보유만"], index=0)
    with filter_cols[5]:
        industries = ["전체"] + sorted([x for x in signal_df["industry"].dropna().astype(str).unique().tolist() if x.strip()])
        industry_filter = st.selectbox("업종", industries, index=0)
    with filter_cols[6]:
        limit = st.selectbox("표시건수", [30, 50, 100, 200], index=1)

    filtered = signal_df.copy()
    if query.strip():
        q = query.strip().lower()
        mask = (
            filtered["code"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["name"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["industry"].astype(str).str.lower().str.contains(q, na=False)
        )
        filtered = filtered[mask].copy()
    if market_filter != "전체":
        filtered = filtered[filtered["market"].astype(str) == market_filter].copy()
    if signal_scope == "신호 종목만":
        filtered = filtered[filtered["display_signal"] != "NO_SIGNAL"].copy()
    elif signal_scope == "신호없음만":
        filtered = filtered[filtered["display_signal"] == "NO_SIGNAL"].copy()
    if signal_filter:
        filtered = filtered[filtered["display_signal"].isin(signal_filter)].copy()
    if holding_filter == "보유만":
        filtered = filtered[filtered["is_real_holding"]].copy()
    elif holding_filter == "미보유만":
        filtered = filtered[~filtered["is_real_holding"]].copy()
    if industry_filter != "전체":
        filtered = filtered[filtered["industry"].astype(str) == industry_filter].copy()

    st.caption(f"검색 결과 {len(filtered)}건")
    if filtered.empty:
        return

    render_pool = filtered.head(max(limit, 200)).copy()
    render_pool, context = enrich_signal_display(render_pool, data)

    render_pool["실보유"] = np.where(render_pool["is_real_holding"], "보유", "-")
    render_pool["시장"] = render_pool["market"].astype(str)
    render_pool["현재가"] = render_pool["latest_close"].map(lambda x: "-" if pd.isna(x) else f"{float(x):,.0f}원")
    render_pool["시가총액"] = render_pool["latest_market_cap"].map(_format_large_number)
    render_pool["영업이익 QoQ"] = render_pool["op_income_qoq_pti"].map(_format_large_number)
    render_pool["영업이익률"] = render_pool["op_margin_pti"]
    render_pool["순이익률"] = render_pool["net_margin_pti"]

    view_df = render_pool[
        [
            "display_signal_ko",
            "실보유",
            "시장",
            "code",
            "name",
            "industry",
            "현재가",
            "시가총액",
            "최적 MA",
            "V2 타이밍",
            "영업이익률",
            "순이익률",
            "영업이익 QoQ",
            "리스크",
        ]
    ].rename(
        columns={
            "display_signal_ko": "의사결정",
            "code": "종목코드",
            "name": "종목명",
        }
    )
    render_table(view_df.head(limit), height=420)
    st.caption("상세 패널은 차트·원천 재무·업종 수익률 계산 때문에 무겁습니다. 필요한 종목만 열어보세요.")
    detail_open = st.toggle("상세 패널 열기", value=False, key="universe_detail_open")
    if not detail_open:
        return
    options = [(row["code"], f"{row['display_signal_ko']} · {row['code']} {row['name']}") for _, row in render_pool.head(200).iterrows()]
    state_key = "universe_selected_code"
    if state_key not in st.session_state:
        st.session_state[state_key] = options[0][0]
    if st.session_state[state_key] not in [code for code, _ in options]:
        st.session_state[state_key] = options[0][0]
    selected_code = st.selectbox(
        "상세 분석 종목",
        [code for code, _ in options],
        index=[code for code, _ in options].index(st.session_state[state_key]),
        format_func=lambda x: next((label for code, label in options if code == x), x),
        key="universe_detail_select",
    )
    st.session_state[state_key] = selected_code
    selected_row_df = render_pool[render_pool["code"] == selected_code].head(1).copy()
    selected_row_df = finalize_signal_axes(selected_row_df, data=data, context=context, decision_df=decision_df)
    selected_row = selected_row_df.iloc[0]
    render_signal_detail_panel(selected_row, data, context, decision_df=decision_df)


def render_validation_sections(data: dict[str, Any]) -> None:
    if MANUAL_TRADES_PATH.exists():
        manual_all = pd.read_csv(MANUAL_TRADES_PATH, dtype={"chat_id": str}, low_memory=False)
    else:
        manual_all = pd.DataFrame()
    if not manual_all.empty:
        manual_all["chat_id"] = manual_all["chat_id"].astype(str)
        manual_all["created_at"] = pd.to_datetime(manual_all.get("created_at"), errors="coerce")
        latest_by_chat = manual_all.dropna(subset=["chat_id"]).groupby("chat_id")["created_at"].max().sort_values()
        chat_ids = [str(x) for x in latest_by_chat.index.tolist() if str(x)]
        if not chat_ids:
            chat_ids = sorted([str(x) for x in manual_all["chat_id"].dropna().unique().tolist() if str(x)])
        visible_chat_ids = [x for x in chat_ids if "_test" not in x.lower()]
        if visible_chat_ids:
            chat_ids = visible_chat_ids
        default_chat = chat_ids[-1]
        selected_chat = st.selectbox("실체결 검증 대상", chat_ids, index=chat_ids.index(default_chat), key="validation_chat")
        manual_trades_token = _file_stamp(MANUAL_TRADES_PATH)
        manual_positions_token = _file_stamp(MANUAL_POSITIONS_PATH)
        manual_audit, manual_detail = load_manual_trade_audit(
            data["version_tokens"]["price"],
            manual_trades_token,
            manual_positions_token,
            selected_chat,
        )
        st.subheader("텔레그램 실체결 기준 사후검증")
        st.caption("텔레그램으로 입력한 실제 체결 종목 전체를 기준으로 검증합니다. 상세표는 체결 종목 전부를 보여주고, 요약표는 당일종가/1일후/7일후 가격이 존재하는 표본만 집계합니다.")
        info_cols = st.columns(3)
        with info_cols[0]:
            st.metric("실체결 종목 수", f"{len(manual_detail)}")
        with info_cols[1]:
            current_hold_count = int((manual_detail.get("현재보유", pd.Series(dtype=str)).astype(str) == "예").sum()) if not manual_detail.empty else 0
            st.metric("현재보유 포함", f"{current_hold_count}")
        with info_cols[2]:
            st.metric("요약 집계 행 수", f"{len(manual_audit)}")
        if not manual_detail.empty:
            st.subheader("실체결 상세 검증")
            render_table(manual_detail.head(100))
        if not manual_audit.empty:
            st.subheader("실체결 요약 검증")
            render_table(manual_audit)
        else:
            st.info("선택한 chat_id의 실체결 검증 데이터가 아직 충분하지 않습니다.")
    else:
        st.info("텔레그램 실체결 기록이 아직 없습니다.")

    timing_audit = load_signal_timing_audit(data["version_tokens"]["output"], data["version_tokens"]["price"])
    if not timing_audit.empty:
        st.subheader("신호일 종가 기준 사후검증")
        st.caption("신호 발생일 종가 기준으로 1영업일 후·7영업일 후 방향이 유리했는지 확인합니다.")
        render_table(timing_audit)
    execution_audit, execution_detail = load_execution_timing_audit(data["version_tokens"]["output"], data["version_tokens"]["price"])
    if not execution_audit.empty:
        with st.expander("전략 시뮬레이션 체결 로그 기준 검증", expanded=False):
            st.caption("이 섹션은 전략 엔진 내부 trade_log 기준입니다. 실제 텔레그램 실체결과는 별도입니다.")
            render_table(execution_audit)
            if not execution_detail.empty:
                render_table(execution_detail.head(50))


def render_holdings_validation(data: dict[str, Any]) -> None:
    render_page_heading(
        "보유/검증",
        kicker="Operations",
        subtitle="실보유 현황과 실체결 사후검증을 중심으로 확인합니다.",
    )
    latest_price = load_price_latest_snapshot(data["version_tokens"]["price"])
    manual_positions = load_manual_positions_snapshot(data["version_tokens"]["output"])
    fast_positions = load_fast_position_state(data["version_tokens"]["output"])
    signal_df = merge_latest_signal_sources(data["signals"], data.get("signals_fast", pd.DataFrame()))
    cfg = load_default_config(data["meta"])

    signal_lookup = pd.DataFrame()
    if not signal_df.empty:
        signal_df = signal_df.copy()
        signal_df["code"] = signal_df["code"].astype(str).str.zfill(6)
        signal_df["display_signal"] = signal_df.apply(lambda row: classify_signal(row, cfg), axis=1)
        signal_df["display_signal_ko"] = signal_df["display_signal"].map(lambda x: signal_label(x, execution_window=is_execution_window()))
        signal_df["active_execution_guide"] = signal_df.apply(lambda row: resolve_action_guide(row, execution_window=is_execution_window()), axis=1)
        signal_df, _ = enrich_signal_display(signal_df, data)
        signal_lookup = signal_df[["code", "display_signal_ko", "V2 타이밍", "리스크", "active_execution_guide"]].copy()

    if not manual_positions.empty:
        manual_view = manual_positions.copy()
        manual_view["code"] = manual_view["code"].astype(str).str.zfill(6)
        if not latest_price.empty:
            price_cols = latest_price[["code", "close"]].copy().rename(columns={"close": "현재가수치"})
            manual_view = manual_view.merge(price_cols, on="code", how="left")
        if not signal_lookup.empty:
            manual_view = manual_view.merge(signal_lookup, on="code", how="left")
        manual_view["display_signal_ko"] = manual_view.get("display_signal_ko", pd.Series(index=manual_view.index)).fillna("신호없음")
        manual_view["V2 타이밍"] = manual_view.get("V2 타이밍", pd.Series(index=manual_view.index)).fillna("-")
        manual_view["리스크"] = manual_view.get("리스크", pd.Series(index=manual_view.index)).fillna("-")
        manual_view["현재가"] = manual_view["현재가수치"].map(lambda x: "-" if pd.isna(x) else f"{float(x):,.0f}원")
        manual_view["평가금액"] = manual_view.apply(
            lambda row: float(row["quantity"]) * float(row["현재가수치"]) if pd.notna(row.get("현재가수치")) else float("nan"),
            axis=1,
        )
        manual_view["평가손익"] = manual_view.apply(
            lambda row: float(row["quantity"]) * (float(row["현재가수치"]) - float(row["avg_price"])) if pd.notna(row.get("현재가수치")) and pd.notna(row.get("avg_price")) else float("nan"),
            axis=1,
        )
        manual_view["평가수익률"] = manual_view.apply(
            lambda row: float(row["현재가수치"]) / float(row["avg_price"]) - 1.0 if pd.notna(row.get("현재가수치")) and pd.notna(row.get("avg_price")) and float(row["avg_price"]) != 0 else float("nan"),
            axis=1,
        )
        summary_cols = st.columns(3)
        with summary_cols[0]:
            st.metric("실보유 종목 수", f"{len(manual_view)}")
        with summary_cols[1]:
            st.metric("실보유 평가금액", f"{pd.to_numeric(manual_view['평가금액'], errors='coerce').sum():,.0f}원")
        with summary_cols[2]:
            st.metric("실보유 평가손익", f"{pd.to_numeric(manual_view['평가손익'], errors='coerce').sum():,.0f}원")
        st.subheader("실보유 현황")
        st.caption(f"실보유 {len(manual_view)}건 · 테스트 계정 제외")
        manual_view["수량표시"] = pd.to_numeric(manual_view["quantity"], errors="coerce").fillna(0).astype(int)
        manual_view["평단표시"] = pd.to_numeric(manual_view["avg_price"], errors="coerce").map(lambda x: "-" if pd.isna(x) else f"{float(x):,.0f}원")
        manual_view["평가금액표시"] = pd.to_numeric(manual_view["평가금액"], errors="coerce").map(lambda x: "-" if pd.isna(x) else f"{float(x):,.0f}원")
        manual_view["평가손익표시"] = pd.to_numeric(manual_view["평가손익"], errors="coerce").map(lambda x: "-" if pd.isna(x) else f"{float(x):,.0f}원")
        manual_view["평가수익률표시"] = pd.to_numeric(manual_view["평가수익률"], errors="coerce").map(lambda x: "-" if pd.isna(x) else f"{float(x):+.1%}")
        manual_view = manual_view.sort_values(["updated_at", "code"], ascending=[False, True], kind="stable")
        render_table(
            manual_view[
                [
                    "chat_id",
                    "code",
                    "name",
                    "수량표시",
                    "평단표시",
                    "현재가",
                    "평가금액표시",
                    "평가손익표시",
                    "평가수익률표시",
                    "display_signal_ko",
                    "V2 타이밍",
                    "리스크",
                ]
            ].rename(
                columns={
                    "chat_id": "계정",
                    "code": "종목코드",
                    "name": "종목명",
                    "수량표시": "수량",
                    "평단표시": "평단",
                    "평가금액표시": "평가금액",
                    "평가손익표시": "평가손익",
                    "평가수익률표시": "평가수익률",
                    "display_signal_ko": "현재 행동",
                }
            ),
            height=320,
        )
    else:
        st.info("실보유 종목이 없습니다.")

    if not fast_positions.empty:
        fast_view = fast_positions.copy()
        fast_view["code"] = fast_view["code"].astype(str).str.zfill(6)
        if not latest_price.empty:
            price_cols = latest_price[["code", "close"]].copy().rename(columns={"close": "현재가수치"})
            fast_view = fast_view.merge(price_cols, on="code", how="left")
        if not signal_lookup.empty:
            fast_view = fast_view.merge(signal_lookup, on="code", how="left")
        fast_view["display_signal_ko"] = fast_view.get("display_signal_ko", pd.Series(index=fast_view.index)).fillna("신호없음")
        fast_view["V2 타이밍"] = fast_view.get("V2 타이밍", pd.Series(index=fast_view.index)).fillna("-")
        fast_view["리스크"] = fast_view.get("리스크", pd.Series(index=fast_view.index)).fillna("-")
        fast_view["평가수익률"] = fast_view.apply(
            lambda row: float(row["현재가수치"]) / float(row["entry_price"]) - 1.0 if pd.notna(row.get("현재가수치")) and pd.notna(row.get("entry_price")) and float(row["entry_price"]) != 0 else float("nan"),
            axis=1,
        )
        fast_view["진입가표시"] = pd.to_numeric(fast_view["entry_price"], errors="coerce").map(lambda x: "-" if pd.isna(x) else f"{float(x):,.0f}원")
        fast_view["현재가표시"] = pd.to_numeric(fast_view["현재가수치"], errors="coerce").map(lambda x: "-" if pd.isna(x) else f"{float(x):,.0f}원")
        fast_view["평가수익률표시"] = pd.to_numeric(fast_view["평가수익률"], errors="coerce").map(lambda x: "-" if pd.isna(x) else f"{float(x):+.1%}")
        fast_view["보유일수표시"] = pd.to_numeric(fast_view["hold_bars"], errors="coerce").fillna(0).astype(int)
        with st.expander("전략 내부 시뮬레이션 보유(참고)", expanded=False):
            st.caption("이 섹션은 실제 보유가 아니라 전략 엔진 내부 포지션 상태입니다. 실운영 판단은 위 `실보유 현황`과 아래 `실체결 기준 사후검증`을 우선으로 봅니다.")
            render_table(
                fast_view[
                    [
                        "trade_id",
                        "code",
                        "name",
                        "entry_date",
                        "진입가표시",
                        "보유일수표시",
                        "현재가표시",
                        "평가수익률표시",
                        "display_signal_ko",
                        "V2 타이밍",
                        "리스크",
                    ]
                ].rename(
                    columns={
                        "trade_id": "전략ID",
                        "code": "종목코드",
                        "name": "종목명",
                        "entry_date": "진입일",
                        "진입가표시": "진입가",
                        "보유일수표시": "보유일수",
                        "현재가표시": "현재가",
                        "평가수익률표시": "평가수익률",
                        "display_signal_ko": "현재 행동",
                    }
                ),
                height=260,
            )

    st.markdown("---")
    render_validation_sections(data)


def interpret_row(row: pd.Series) -> str:
    diff = _safe_float(row.get("mean_diff"))
    win_diff = _safe_float(row.get("win_rate_diff"))
    direction = "유리" if diff > 0 else "불리"
    win_direction = "높게" if win_diff > 0 else "낮게"
    condition = _translate_condition(row.get("condition", "-"))
    target = _translate_target(row.get("target", "-"))
    return f"`{condition}` 조건은 {target} 기준으로 평균 수익률이 {direction}하며 승률도 {win_direction} 나타났습니다."


def build_runtime_health_table(data: dict[str, Any]) -> pd.DataFrame:
    latest_dates = runtime_latest_dates(data)
    price_meta = _read_json(data_path("price_panel_meta.json")).get("bounds", {})
    feature_meta = _read_json(data_path("feature_daily_meta.json")).get("bounds", {})
    health = data["health"]
    health_map = {str(row.get("dataset", "")): row for _, row in health.iterrows()} if not health.empty else {}
    live_latest = "-"
    live_rows = 0
    live_codes = 0
    if not data["live_quotes"].empty:
        live_dates = pd.to_datetime(data["live_quotes"]["date"], errors="coerce").dropna()
        if not live_dates.empty:
            live_latest = str(live_dates.max().date())
        live_rows = len(data["live_quotes"])
        live_codes = data["live_quotes"]["code"].astype(str).str.zfill(6).nunique()
    rows = [
        {
            "데이터셋": "주가 통합 패널",
            "행 수": _safe_int(price_meta.get("rows")),
            "시작일": price_meta.get("date_min", "-"),
            "최신일": latest_dates["price_latest"],
            "종목 수": _safe_int(price_meta.get("codes")),
            "설명": "price_panel.csv 메타 기준",
        },
        {
            "데이터셋": "전략 입력셋",
            "행 수": _safe_int(feature_meta.get("rows")),
            "시작일": feature_meta.get("date_min", "-"),
            "최신일": latest_dates["feature_latest"],
            "종목 수": _safe_int(feature_meta.get("codes")),
            "설명": "feature_daily.csv 메타 기준",
        },
        {
            "데이터셋": "매크로",
            "행 수": _safe_int(health_map.get("macro_daily", {}).get("rows")),
            "시작일": health_map.get("macro_daily", {}).get("date_min", "-"),
            "최신일": latest_dates["macro_latest"],
            "종목 수": 0,
            "설명": "macro_daily.csv 실제 최신일 기준",
        },
        {
            "데이터셋": "재무",
            "행 수": _safe_int(health_map.get("fundamental_quarterly_multi", {}).get("rows")),
            "시작일": health_map.get("fundamental_quarterly_multi", {}).get("date_min", "-"),
            "최신일": latest_dates["fundamental_latest"],
            "종목 수": _safe_int(health_map.get("fundamental_quarterly_multi", {}).get("codes")),
            "설명": "fundamental_quarterly_multi.csv 실제 최신 공시일 기준",
        },
        {
            "데이터셋": "live_quotes 잔존 파일",
            "행 수": live_rows,
            "시작일": live_latest,
            "최신일": live_latest,
            "종목 수": live_codes,
            "설명": "기본 fast 경로는 미사용. 남아 있으면 참고용 캐시로만 봅니다.",
        },
        {
            "데이터셋": "최신 전략 신호",
            "행 수": len(data["signals"]),
            "시작일": str(pd.to_datetime(data["signals"]["date"], errors="coerce").min().date()) if not data["signals"].empty else "-",
            "최신일": str(pd.to_datetime(data["signals"]["date"], errors="coerce").max().date()) if not data["signals"].empty else "-",
            "종목 수": data["signals"]["code"].astype(str).str.zfill(6).nunique() if not data["signals"].empty else 0,
            "설명": "signal_daily_fast_latest.csv 또는 signal_daily_latest.csv 기준",
        },
    ]
    return pd.DataFrame(rows)


def render_data_health(data: dict[str, Any]) -> None:
    render_page_heading("데이터 상태", kicker="Data", subtitle="최신 데이터 범위와 메타데이터를 확인합니다.")
    show_flash()
    runtime_health = build_runtime_health_table(data)
    render_table(runtime_health)
    st.caption("데이터 최신일은 data_health_summary.csv가 아니라 메타 JSON과 실제 최신 결과 파일을 우선 기준으로 표시합니다.")
    left, right = st.columns(2)
    with left:
        st.markdown("#### 최신화 메타데이터")
        st.json(data["refresh_meta"] or {})
    with right:
        st.markdown("#### fast alert 메타데이터")
        st.json(data["fast_meta"] or {})
    show_last_command_output()


def render_backtest(data: dict[str, Any]) -> None:
    render_page_heading("연구실", kicker="Research", subtitle="조건 조합 탐색, 최적 MA 연구, V2 후보 로직 실험을 진행합니다.")
    if not data.get("v2_sim", pd.DataFrame()).empty:
        st.subheader("V2 시뮬레이션")
        st.success("현재 V2 기본안은 `월봉매수 / 주봉매도 / buy_0%__sell_-5%` 입니다.")
        st.caption("기본 구조는 `최적 MA 메인`, `주가위치·매크로·재무 보조`입니다.")
        render_table(prettify_v2_sim_summary(data["v2_sim"]))
    if not data["eval"].empty:
        st.subheader("전략 성과 요약")
        render_table(data["eval"])
    st.info("연구실 화면은 규칙 후보와 조건부 성과를 통해 의사결정 로직을 개선하기 위한 탐색용 화면입니다. 오늘의 의사결정과 직접 동일한 실행 화면은 아닙니다.")
    if not data["research"].empty:
        target = st.selectbox("조건부 성과 평가 구간", sorted(data["research"]["target"].dropna().unique().tolist()))
        filtered = data["research"][data["research"]["target"] == target].copy().sort_values("mean_diff", ascending=False)
        render_table(prettify_condition_perf(filtered))
        if not filtered.empty:
            st.info(interpret_row(filtered.iloc[0]))
            st.warning(interpret_row(filtered.iloc[-1]))
    if not data["rule_top"].empty:
        st.subheader("우선 검토할 규칙 후보")
        target = st.selectbox("규칙 후보 평가 구간", sorted(data["rule_top"]["target"].dropna().unique().tolist()), key="rule_target")
        top = data["rule_top"][data["rule_top"]["target"] == target].copy().sort_values("score", ascending=False).head(20)
        render_table(prettify_rule_candidates(top))
        st.caption("우선점수는 표본수 가중 없이 평균 수익률 차이와 승률 차이 중심으로 계산합니다. 표본수는 최소 표본 필터로만 사용합니다.")
        if not top.empty:
            top_row = top.iloc[0]
            st.success(
                f"현재 전체 기준 최우선 규칙 후보는 `{_translate_rule_expr(top_row['rule_expr'])}` 입니다. "
                f"평균 수익률 차이 {_safe_float(top_row['mean_diff']):.2%}, 승률 차이 {_safe_float(top_row['win_rate_diff']):.2%} 입니다."
            )
    if not data["research_industry"].empty:
        industries = sorted([x for x in data["research_industry"]["group"].dropna().unique().tolist() if x != "ALL"])
        industry = st.selectbox("업종별 조건부 성과", industries, key="industry_research")
        render_table(prettify_condition_perf(data["research_industry"][data["research_industry"]["group"] == industry].copy().sort_values("mean_diff", ascending=False)))
    if not data["rule_industry"].empty:
        industries = sorted([x for x in data["rule_industry"]["group"].dropna().unique().tolist() if x != "ALL"])
        industry = st.selectbox("업종별 규칙 후보", industries, key="industry_rule")
        render_table(prettify_rule_candidates(data["rule_industry"][data["rule_industry"]["group"] == industry].copy().sort_values("score", ascending=False).head(20)))
        st.caption("업종별 규칙 후보 역시 탐색용입니다. 오늘의 의사결정 엔진과 직접 동일한 실행 로직은 아닙니다.")
    st.caption("전략 기준과 운영 스케줄은 별도 `전략보드`에서 확인합니다.")
    show_last_command_output()


def render_post_audit(data: dict[str, Any]) -> None:
    render_page_heading("사후검증", kicker="Audit", subtitle="실체결과 신호 이후 성과를 검증합니다.")
    render_validation_sections(data)


def render_settings(data: dict[str, Any]) -> None:
    render_page_heading("전략 설정", kicker="Config", subtitle="운영 파라미터와 실행 옵션을 조정합니다.")
    show_flash()
    cfg = load_default_config(data["meta"]).copy()
    with st.form("strategy_config_form"):
        for group in sorted({spec["group"] for spec in CONFIG_SPECS}):
            st.markdown(f"#### {group}")
            cols = st.columns(2)
            specs = [spec for spec in CONFIG_SPECS if spec["group"] == group]
            for idx, spec in enumerate(specs):
                with cols[idx % 2]:
                    key = spec["key"]
                    if spec["kind"] == "int":
                        cfg[key] = st.number_input(spec["label"], value=_safe_int(cfg.get(key)), step=_safe_int(spec.get("step", 1), 1), help=spec["help"], key=f"cfg_{key}")
                    elif spec["kind"] == "float":
                        cfg[key] = st.number_input(spec["label"], value=_safe_float(cfg.get(key)), step=float(spec.get("step", 0.01)), format="%.4f", help=spec["help"], key=f"cfg_{key}")
                    else:
                        cfg[key] = st.text_input(spec["label"], value=str(cfg.get(key)), help=spec["help"], key=f"cfg_{key}")
        save_clicked = st.form_submit_button("설정 저장", use_container_width=True)
    if save_clicked:
        save_config(cfg)
        set_flash("전략 설정을 저장했습니다.")
        st.rerun()
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("저장값으로 fast alert 재계산", use_container_width=True):
            launch_pipeline_job(cfg, "fast alert 재계산", fast_alerts=True, job_feedback_label="fast alert 재계산")
            st.rerun()
    with col2:
        if st.button("저장값으로 전체 재계산", use_container_width=True):
            launch_pipeline_job(cfg, "전체 재계산", job_feedback_label="전체 재계산")
            st.rerun()
    with col3:
        if st.button("저장값으로 최신화 + 알림", use_container_width=True):
            launch_pipeline_job(
                cfg,
                "주가/매크로/금 전체 증분 최신화와 알림 발송",
                refresh_data=True,
                refresh_macro=True,
                refresh_gold=True,
                prefer_kiwoom_eod=True,
                fast_alerts=True,
                send_alerts=True,
                job_feedback_label="전체증분최신화",
            )
            st.rerun()
    show_df = pd.DataFrame([{"구분": spec["group"], "파라미터": spec["key"], "설정명": spec["label"], "값": cfg[spec["key"]], "설명": spec["help"]} for spec in CONFIG_SPECS])
    render_table(show_df)
    show_last_command_output()


def render_access_guide() -> None:
    render_page_heading("접속 안내", kicker="Access", subtitle="모바일과 외부 기기 접속 절차를 정리합니다.")
    ts = load_tailscale_status()
    docs = build_access_guide_documents(ts)
    st.write("지인에게 바로 전달할 수 있는 접속 안내입니다.")
    status_cols = st.columns(4)
    with status_cols[0]:
        st.metric("Tailscale 설치", "완료" if ts.get("installed") else "미설치")
    with status_cols[1]:
        st.metric("Tailscale 로그인", "완료" if ts.get("logged_in") else "필요")
    with status_cols[2]:
        st.metric("Tailscale IP", ts.get("ipv4", "-"))
    with status_cols[3]:
        st.metric("MagicDNS", ts.get("dns_name", "-"))
    st.markdown("### 모바일 설치 링크")
    st.markdown("1. 휴대폰에 Tailscale을 설치합니다.")
    st.markdown("- Android (Google Play): https://play.google.com/store/apps/details?id=com.tailscale.ipn")
    st.markdown("- iPhone/iPad (App Store): https://apps.apple.com/app/tailscale/id1470499037")
    st.markdown("- Windows/Mac/Linux: https://tailscale.com/download")
    st.markdown("2. Tailscale 로그인 후, 공유를 받은 계정으로 접속합니다.")
    st.markdown(f"3. 접속 주소: `{docs['ip_url']}` 또는 `{docs['dns_url']}`")
    st.markdown("### 안내문 파일")
    st.code(docs['markdown_path'], language='text')
    st.code(docs['html_path'], language='text')
    st.markdown("### 참고")
    if ts.get('login_url') and ts.get('login_url') != '-':
        st.warning(f"이 PC의 Tailscale 로그인이 아직 필요합니다: {ts['login_url']}")


def render_footer(data: dict[str, Any]) -> None:
    return


def render_sidebar_panel(data: dict[str, Any]) -> None:
    latest_dates = runtime_latest_dates(data)
    st.sidebar.markdown('<div class="ns-sidebar-section-title">운영 요약</div>', unsafe_allow_html=True)
    st.sidebar.caption(f"주가 {latest_dates['price_latest']} · feature {latest_dates['feature_latest']}")
    st.sidebar.caption(f"매크로 {latest_dates['macro_latest']} · 재무 {latest_dates['fundamental_latest']}")
    with st.sidebar:
        render_pipeline_progress()
    with st.sidebar.expander("운영 스케줄", expanded=False):
        st.markdown(
            "\n".join(
                [
                    "- `07:00` KRX 보조 데이터 갱신",
                    "- `08:20~08:25` 프리장 1차 메시지 (`08:10` 슬롯 기준)",
                    "- `09:20~09:25` 본장 2차 메시지 (`09:10` 슬롯 기준)",
                    "- `08:10`부터 30분마다 전종목 갱신 + fast 변화 알림",
                    "- `20:10` EOD 수집 + 마감 요약",
                ]
            )
        )
    with st.sidebar.expander("서비스 상태", expanded=False):
        st.markdown("\n".join(build_service_status(data)))
    st.sidebar.markdown('<div class="ns-sidebar-section-title">빠른 실행</div>', unsafe_allow_html=True)
    cfg = load_default_config(data["meta"])
    if st.sidebar.button("전체 증분 최신화 + fast alert", use_container_width=True, key="sidebar_refresh_fast"):
        launch_pipeline_job(
            cfg,
            "주가/매크로/금 전체 증분 최신화와 fast alert",
            refresh_data=True,
            refresh_macro=True,
            refresh_gold=True,
            prefer_kiwoom_eod=True,
            fast_alerts=True,
            job_feedback_label="증분최신화",
        )
        st.rerun()
    if st.sidebar.button("전체 증분 최신화 + 전체 재계산", use_container_width=True, key="sidebar_refresh_full"):
        launch_pipeline_job(
            cfg,
            "주가/매크로/금 전체 증분 최신화와 전체 재계산",
            refresh_data=True,
            refresh_macro=True,
            refresh_gold=True,
            prefer_kiwoom_eod=True,
            job_feedback_label="전체증분최신화",
        )
        st.rerun()
    st.sidebar.caption("대시보드 주소: http://192.168.219.113:8501")


def main() -> None:
    st.set_page_config(page_title="Strategy V2 Dashboard", layout="wide")
    inject_base_css()
    version_tokens = build_version_tokens()
    data = load_output_data(version_tokens["output"])
    data["version_tokens"] = version_tokens
    with st.sidebar:
        render_live_clock("sidebar_live_clock", compact=True)
    st.sidebar.markdown('<div class="ns-sidebar-title">V2 전략보드</div>', unsafe_allow_html=True)
    page = st.sidebar.radio(
        "화면 선택",
        ["의사결정", "전종목 분석", "보유/검증", "연구실", "전략보드"],
        index=0,
        label_visibility="collapsed",
    )
    st.sidebar.markdown('<div class="ns-sidebar-divider"></div>', unsafe_allow_html=True)
    render_sidebar_panel(data)
    if page == "의사결정":
        render_strategy_report(data)
    elif page == "전종목 분석":
        render_universe_analysis(data)
    elif page == "보유/검증":
        render_holdings_validation(data)
    elif page == "연구실":
        render_backtest(data)
    else:
        render_operations_page(data)
    render_footer(data)


if __name__ == "__main__":
    main()


