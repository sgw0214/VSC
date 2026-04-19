from __future__ import annotations

import html
import json
import os
import re
import requests
import subprocess
import sys
import textwrap
from functools import lru_cache
from email.utils import parsedate_to_datetime
from datetime import datetime, time, timedelta, timezone
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import quote
import xml.etree.ElementTree as ET

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup

APP_FILE = Path(__file__).resolve()
PROJECT_ROOT = APP_FILE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from new_strategy.earnings_signal_engine import EarningsStrategyConfig, add_v2_optimal_ma_features
from new_strategy.optimal_ma_overlay import (
    MA_SELECTION_PATH as OPTIMAL_MA_SELECTION_PATH,
    OVERLAY_SNAPSHOT_PATH as OPTIMAL_MA_SNAPSHOT_PATH,
)
from new_strategy.optimal_ma_publish_contract import OPTIMAL_MA_ALL_SELECTION_PATH
from new_strategy.paths import data_path, output_path, stock_root, strategy_output_path, trend_data_path
from new_strategy.price_latest_snapshot import (
    PRICE_PANEL_INDUSTRY_SNAPSHOT_META_PATH,
    PRICE_SNAPSHOT_META_PATH,
    read_price_panel_industry_snapshot,
    read_price_latest_snapshot,
)
from new_strategy.price_level_map import build_contract_price_level_map, build_price_level_map, DEFAULT_MA_STOP_PCT
from new_strategy.v2_ma_contract import (
    normalize_v2_ma_frame,
    normalize_v2_mode_contract_frame,
    v2_ma_context,
    v2_mode_contract_context,
)

# Touching the main script file should force Streamlit source reload when
# runtime logic changes need to replace stale in-memory caches.
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
FEATURE_DAILY_PATH = data_path("feature_daily.pkl")
BEST_MODE_BY_STOCK_PATH = output_path("v2_four_timing_mode_grid", "best_mode_by_stock_full.csv")

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
BRIDGE_STATE_PATH = APP_DIR / "telegram_bridge" / "telegram_bridge_state.json"
ACCESS_GUIDE_MD_PATH = APP_DIR / "friend_access_guide.md"
ACCESS_GUIDE_HTML_PATH = APP_DIR / "friend_access_guide.html"
FAST_STATE_PATH = APP_DIR / "fast_position_state.csv"
V2_SIM_SUMMARY_PATH = output_path("v2_simulation_summary", "v2_simulation_master_summary.csv")
TAILSCALE_EXE_PATH = Path(r"C:\Program Files\Tailscale\tailscale.exe")
TRADE_LOG_PATH = APP_DIR / "trade_log.csv"
FEATURE_SNAPSHOT_PATH = APP_DIR / "feature_latest_snapshot.pkl"
LEGACY_FEATURE_SNAPSHOT_PATH = APP_DIR / "feature_latest_snapshot.csv"
PRICE_SNAPSHOT_PATH = APP_DIR / "price_panel_latest_snapshot.csv"
PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH = APP_DIR / "price_panel_industry_base.pkl"
BRIDGE_DIR = APP_DIR / "telegram_bridge"
MANUAL_TRADES_PATH = BRIDGE_DIR / "manual_portfolio_trades.csv"
MANUAL_POSITIONS_PATH = BRIDGE_DIR / "manual_portfolio_positions.csv"
TELEGRAM_JOB_LOG_PATH = BRIDGE_DIR / "telegram_bridge_job_log.csv"
DART_CORP_CODES_PATH = data_path("dart_corp_codes.csv")
FNGUIDE_SNAPSHOT_XML_URL = "https://comp.fnguide.com/SVO2/xml/Snapshot_all/{code}.xml"
DART_DISCLOSURE_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
DART_COMPANY_SEARCH_URL = "https://dart.fss.or.kr/dsab001/searchCorp.ax"
GOOGLE_NEWS_RSS_SEARCH_URL = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
TREND_OUTPUT_DIR = strategy_output_path("trend_lab")
TREND_SNAPSHOT_PATH = TREND_OUTPUT_DIR / "trend_global_snapshot.json"
TREND_DAILY_SCORES_PATH = TREND_OUTPUT_DIR / "trend_keyword_daily_scores.csv"
TREND_LINKS_PATH = TREND_OUTPUT_DIR / "trend_keyword_industry_links.csv"
TREND_HOLDING_EXPOSURE_PATH = TREND_OUTPUT_DIR / "trend_holding_exposure.csv"
TREND_COLLECTION_STATUS_PATH = TREND_OUTPUT_DIR / "trend_collection_status.csv"
TREND_MENTIONS_ROLLING_PATH = TREND_OUTPUT_DIR / "trend_news_mentions_rolling.csv"
TREND_CLASSIFICATION_LOG_PATH = TREND_OUTPUT_DIR / "trend_classification_log.csv"
TREND_TAXONOMY_PATH = trend_data_path("trend_keyword_taxonomy.csv")
TREND_ALIAS_PATH = trend_data_path("trend_keyword_aliases.csv")
TREND_UNCLASSIFIED_PATH = trend_data_path("trend_unclassified_keywords.csv")

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
    "SELL_WATCH": "소액매도검토",
    "SELL": "매도",
}
SIGNAL_LABELS_POSTCLOSE = {
    "BUY": "익일매수",
    "BUY_WATCH": "익일관심유지",
    "WATCH": "익일관심유지",
    "HOLD": "익일보유",
    "SELL_WATCH": "익일소액매도검토",
    "SELL": "익일매도",
}
SHORT_SIGNAL_LABELS_INTRADAY = {
    "BUY": "매수",
    "BUY_WATCH": "관심",
    "WATCH": "관심",
    "HOLD": "보유",
    "SELL_WATCH": "소액매도",
    "SELL": "매도",
}
SHORT_SIGNAL_LABELS_POSTCLOSE = {
    "BUY": "익일매수",
    "BUY_WATCH": "익일관심",
    "WATCH": "익일관심",
    "HOLD": "익일보유",
    "SELL_WATCH": "익일소액매도",
    "SELL": "익일매도",
}
DEFAULT_FIXED_STOP_LOSS = EarningsStrategyConfig().fixed_stop_loss
DEFAULT_MA_STOP_LOSS = DEFAULT_MA_STOP_PCT

TERM_NOTES = [
    "PTI*: 공시일 기준으로 실제 시장이 알 수 있었던 재무 정보만 쓰는 방식입니다.",
    "QoQ*: 직전 분기 대비 변화입니다.",
    "TTM*: 최근 4개 분기 합계입니다.",
    "ATR*: 평균 진폭 기반 변동성 지표입니다.",
    "EOD*: 장 종료 후 확정 종가 기준 데이터입니다.",
]


def is_execution_window(now: datetime | None = None) -> bool:
    now = now or datetime.now(SEOUL_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=SEOUL_TZ)
    else:
        now = now.astimezone(SEOUL_TZ)
    if now.weekday() >= 5:
        return False
    current = now.time()
    if current < time(8, 0):
        return False
    if current > time(20, 0):
        return False
    if _postclose_summary_sent_for_datetime(now):
        return False
    if _scheduled_brief_sent_for_datetime(now, "preopen_1", "regular_open_1"):
        return True
    return True


def _bridge_state_signature() -> int:
    try:
        return BRIDGE_STATE_PATH.stat().st_mtime_ns
    except FileNotFoundError:
        return 0


@lru_cache(maxsize=4)
def _load_bridge_state(signature: int) -> dict[str, Any]:
    if not signature or not BRIDGE_STATE_PATH.exists():
        return {}
    try:
        return json.loads(BRIDGE_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _postclose_summary_sent_for_datetime(now: datetime) -> bool:
    date_str = now.date().isoformat()
    state = _load_bridge_state(_bridge_state_signature())
    key = f"{date_str}:postclose_summary"
    scheduled = state.get("scheduled_briefs")
    if isinstance(scheduled, dict) and key in scheduled:
        try:
            sent_at = datetime.fromisoformat(str(scheduled[key])).astimezone(SEOUL_TZ)
            if sent_at <= now:
                return True
        except Exception:
            return True
    last_sent = str(state.get("last_postclose_summary_at") or "").strip()
    if not last_sent.startswith(date_str):
        return False
    try:
        sent_at = datetime.fromisoformat(last_sent).astimezone(SEOUL_TZ)
        return sent_at <= now
    except Exception:
        return True


def _scheduled_brief_sent_for_datetime(now: datetime, *brief_suffixes: str) -> bool:
    date_str = now.date().isoformat()
    state = _load_bridge_state(_bridge_state_signature())
    scheduled = state.get("scheduled_briefs")
    if not isinstance(scheduled, dict):
        return False
    for suffix in brief_suffixes:
        key = f"{date_str}:{suffix}"
        if key not in scheduled:
            continue
        try:
            sent_at = datetime.fromisoformat(str(scheduled[key])).astimezone(SEOUL_TZ)
            if sent_at <= now:
                return True
        except Exception:
            return True
    return False


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
    if pd.isna(value):
        return "위험없음"
    raw = str(value).strip()
    if raw.lower() in {"", "nan", "none", "null", "na", "nat"}:
        return "위험없음"
    mapping = {
        "macro_risk_off": "매크로 위험장",
        "high_volatility": "고변동성",
        "earnings_exception": "실적 예외",
        "sell_watch": "매도경계",
        "weekly_sell_watch": "주봉 매도경계",
        "monthly_overheat": "월봉 과열",
        "timing_break": "타이밍 훼손",
        "quality_drop": "품질 저하",
        "stop_loss": "손절 기준",
        "signal_missing": "전략신호 없음",
    }
    if not raw:
        return "위험없음"
    parts = [
        mapping.get(part.strip(), part.strip().replace("_", " "))
        for part in raw.split("|")
        if part.strip() and part.strip().lower() not in {"nan", "none", "null", "na", "nat"}
    ]
    return " · ".join(parts) if parts else "위험없음"


def _display_signal_count(counts: dict[str, int], signal: str) -> int:
    signal = str(signal or "").upper()
    if signal == "BUY_WATCH":
        return int(counts.get("BUY_WATCH", 0)) + int(counts.get("WATCH", 0))
    return int(counts.get(signal, 0))


def _is_missing_scalar(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except Exception:
        return False
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


def _coalesce_text(*values: Any, default: str = "") -> str:
    for value in values:
        if _is_missing_scalar(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return default


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
    if target_text == "weekly_sell_watch":
        return "weekly_sell_watch" in parts or "sell_watch" in parts
    if target_text == "sell_watch":
        return "sell_watch" in parts or "weekly_sell_watch" in parts
    return target_text in parts


def _v2_display_signal(row: pd.Series | dict[str, Any], *, is_real_holding: bool) -> str:
    signal = str(row.get("signal", "")).upper()
    risk_flag = "" if pd.isna(row.get("risk_flag")) else str(row.get("risk_flag")).strip()
    sell_trigger = bool(row.get("v2_sell_trigger", row.get("v2_week_sell_trigger", False)))
    sell_watch = bool(row.get("v2_sell_watch", row.get("v2_week_sell_watch", False)))

    if is_real_holding:
        if signal == "SELL" or sell_trigger:
            return "SELL"
        if signal == "SELL_WATCH" or sell_watch or has_risk_flag(risk_flag, "sell_watch"):
            return "SELL_WATCH"
        return "HOLD"

    if signal in {"BUY", "BUY_WATCH", "SELL", "SELL_WATCH"}:
        return signal
    if signal == "WATCH":
        return "BUY_WATCH"
    if signal == "HOLD" and has_risk_flag(risk_flag, "sell_watch"):
        return "SELL_WATCH"
    return "HOLD"


def _apply_display_signal_fields(
    signal_df: pd.DataFrame,
    cfg: dict[str, Any],
    *,
    execution_window: bool,
) -> pd.DataFrame:
    if signal_df.empty:
        return signal_df
    out = signal_df.copy()
    if "is_real_holding" not in out.columns:
        out["is_real_holding"] = False
    out["display_signal"] = out.apply(
        lambda row: _v2_display_signal(row, is_real_holding=bool(row.get("is_real_holding", False))),
        axis=1,
    )
    out["display_signal_ko"] = out["display_signal"].map(lambda x: signal_label(x, execution_window=execution_window))
    out["active_execution_guide"] = out.apply(lambda row: resolve_action_guide(row, execution_window=execution_window), axis=1)
    out["signal_rank"] = out["display_signal"].map(SIGNAL_ORDER).fillna(99)
    return out


def _contract_action_text(contract: dict[str, Any], side: str, *, detailed: bool = False) -> str:
    label = "매수" if side == "buy" else "매도"
    timeframe_label = contract.get(f"{side}_label")
    timeframe_short = contract.get(f"{side}_short_label")
    window = contract.get(f"{side}_window")
    if timeframe_label is None or timeframe_short is None or window is None:
        return ""
    trigger = "상향돌파" if side == "buy" else "하향돌파"
    if detailed:
        return f"{label} {timeframe_label} {int(window)}이평 {trigger}"
    return f"{label} {timeframe_short}{int(window)} {trigger}"


def _contract_action_with_dist_text(
    row: pd.Series | dict[str, Any],
    contract: dict[str, Any],
    side: str,
    *,
    detailed: bool = False,
) -> str:
    base_text = _contract_action_text(contract, side, detailed=detailed)
    if not base_text:
        return ""
    dist = _safe_float(
        row.get(f"v2_{side}_live_dist", row.get(f"v2_{side}_period_dist", float("nan"))),
        float("nan"),
    )
    if pd.notna(dist):
        return f"{base_text} ({dist:+.1%})"
    return base_text


def format_v2_timing_summary(row: pd.Series | dict[str, Any], *, multiline: bool = False) -> str:
    contract = v2_mode_contract_context(row)
    parts: list[str] = []
    if contract.get("mode_label"):
        parts.append(str(contract["mode_label"]))
    buy_text = _contract_action_with_dist_text(row, contract, "buy")
    sell_text = _contract_action_with_dist_text(row, contract, "sell")
    if buy_text:
        parts.append(buy_text)
    if sell_text:
        parts.append(sell_text)
    if not parts:
        return "-"
    return "\n".join(parts) if multiline else " / ".join(parts)


def format_v2_ma_axis_summary(row: pd.Series | dict[str, Any]) -> str:
    contract = v2_mode_contract_context(row)
    parts: list[str] = []
    if contract.get("mode_label"):
        parts.append(str(contract["mode_label"]))
    buy_text = _contract_action_with_dist_text(row, contract, "buy", detailed=True)
    sell_text = _contract_action_with_dist_text(row, contract, "sell", detailed=True)
    if buy_text:
        parts.append(buy_text)
    if sell_text:
        parts.append(sell_text)
    return "\n".join(parts) if parts else "-"


def format_price_axis_summary(row: pd.Series | dict[str, Any]) -> str:
    row = _risk_row_with_fallbacks(row)
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
    stock_ret = pd.to_numeric(pd.Series([row.get("stock_period_return")]), errors="coerce").iloc[0]
    industry_ret = pd.to_numeric(pd.Series([row.get("industry_period_return")]), errors="coerce").iloc[0]
    industry_volume = pd.to_numeric(pd.Series([row.get("industry_volume_avg")]), errors="coerce").iloc[0]
    industry_tf = str(row.get("industry_timeframe") or "").strip().lower()
    industry_window = pd.to_numeric(pd.Series([row.get("industry_window")]), errors="coerce").iloc[0]
    tf_label = ""
    if pd.notna(industry_window):
        prefix = "월" if industry_tf == "monthly" else "주" if industry_tf == "weekly" else "일"
        tf_label = f"{prefix}{int(float(industry_window))}"
    if pd.notna(stock_ret):
        if tf_label:
            extra_lines.append(f"종목 수익률({tf_label}) {float(stock_ret):+.1%}")
        else:
            extra_lines.append(f"종목 수익률 {float(stock_ret):+.1%}")
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
def load_price_panel_industry_base(_price_token: Any) -> pd.DataFrame:
    return read_price_panel_industry_snapshot(allow_refresh=False)


def _normalize_return_combo_specs(combo_specs: tuple[tuple[str, int], ...]) -> tuple[tuple[str, int], ...]:
    normalized: set[tuple[str, int]] = set()
    for raw_timeframe, raw_window in combo_specs:
        timeframe = str(raw_timeframe or "").strip().lower()
        if not timeframe:
            continue
        try:
            window = int(raw_window)
        except Exception:
            continue
        if window <= 0:
            continue
        normalized.add((timeframe, window))
    return tuple(sorted(normalized))


@st.cache_data(show_spinner=False)
def load_latest_return_context(_price_token: Any, combo_specs: tuple[tuple[str, int], ...]) -> pd.DataFrame:
    specs = _normalize_return_combo_specs(combo_specs)
    if not specs:
        return pd.DataFrame(
            columns=["code", "industry_timeframe", "industry_window", "stock_period_return", "industry_period_return"]
        )

    df = load_price_panel_industry_base(_price_token)
    if df.empty:
        return pd.DataFrame(
            columns=["code", "industry_timeframe", "industry_window", "stock_period_return", "industry_period_return"]
        )

    frames: list[pd.DataFrame] = []
    for timeframe in sorted({tf for tf, _ in specs}):
        windows = tuple(sorted(window for tf, window in specs if tf == timeframe))
        if not windows:
            continue

        if timeframe == "weekly":
            scoped = df.copy()
            scoped["bucket"] = scoped["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
            base = (
                scoped.groupby(["code", "industry", "bucket"], as_index=False)
                .agg({"close": "last"})
                .sort_values(["code", "bucket"])
                .reset_index(drop=True)
            )
        elif timeframe == "monthly":
            scoped = df.copy()
            scoped["bucket"] = scoped["date"].dt.to_period("M").dt.end_time.dt.normalize()
            base = (
                scoped.groupby(["code", "industry", "bucket"], as_index=False)
                .agg({"close": "last"})
                .sort_values(["code", "bucket"])
                .reset_index(drop=True)
            )
        else:
            base = df[["code", "industry", "date", "close"]].copy().sort_values(["code", "date"]).reset_index(drop=True)

        grouped_close = base.groupby("code", sort=False)["close"]
        for window in windows:
            tmp = base[["code", "industry", "close"]].copy()
            tmp["stock_period_return"] = tmp["close"] / grouped_close.shift(int(window)) - 1.0
            latest = tmp.groupby("code", as_index=False).tail(1).dropna(subset=["stock_period_return"]).copy()
            if latest.empty:
                continue
            industry_ret = (
                latest.groupby("industry", as_index=False)["stock_period_return"]
                .mean()
                .rename(columns={"stock_period_return": "industry_period_return"})
            )
            latest = latest.merge(industry_ret, on="industry", how="left")
            latest["industry_timeframe"] = timeframe
            latest["industry_window"] = int(window)
            frames.append(
                latest[
                    [
                        "code",
                        "industry_timeframe",
                        "industry_window",
                        "stock_period_return",
                        "industry_period_return",
                    ]
                ]
            )

    if not frames:
        return pd.DataFrame(
            columns=["code", "industry_timeframe", "industry_window", "stock_period_return", "industry_period_return"]
        )
    return pd.concat(frames, ignore_index=True)


@st.cache_data(show_spinner=False)
def load_latest_industry_return_by_timeframe_windows(_price_token: Any, timeframe: str, windows: tuple[int, ...]) -> pd.DataFrame:
    specs = tuple((str(timeframe or "").lower(), int(w)) for w in windows if pd.notna(w))
    context = load_latest_return_context(_price_token, specs)
    if context.empty:
        return pd.DataFrame(columns=["industry", "industry_window", "industry_return"])
    scoped = load_price_panel_industry_base(_price_token)[["code", "industry"]].drop_duplicates()
    if scoped.empty:
        return pd.DataFrame(columns=["industry", "industry_window", "industry_return"])
    out = context.merge(scoped, on="code", how="left")
    out = (
        out[["industry", "industry_window", "industry_period_return"]]
        .dropna(subset=["industry", "industry_period_return"])
        .drop_duplicates(subset=["industry", "industry_window"], keep="first")
        .rename(columns={"industry_period_return": "industry_return"})
        .reset_index(drop=True)
    )
    return out


@st.cache_data(show_spinner=False)
def load_latest_industry_return_by_timeframe_window(_price_token: Any, timeframe: str, window: int) -> pd.DataFrame:
    df = load_latest_industry_return_by_timeframe_windows(_price_token, timeframe, (int(window),))
    if df.empty:
        return pd.DataFrame(columns=["industry", "industry_return"])
    return df[df["industry_window"] == int(window)][["industry", "industry_return"]].reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_latest_stock_return_by_timeframe_windows(_price_token: Any, timeframe: str, windows: tuple[int, ...]) -> pd.DataFrame:
    specs = tuple((str(timeframe or "").lower(), int(w)) for w in windows if pd.notna(w))
    context = load_latest_return_context(_price_token, specs)
    if context.empty:
        return pd.DataFrame(columns=["code", "return_window", "stock_return"])
    out = (
        context[["code", "industry_window", "stock_period_return"]]
        .dropna(subset=["stock_period_return"])
        .rename(columns={"industry_window": "return_window", "stock_period_return": "stock_return"})
        .reset_index(drop=True)
    )
    return out


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
            "SELL_WATCH": "소액매도 검토",
            "SELL": "매도 우선",
            "NO_SIGNAL": "신호 없음 · 조건 대기",
        }
    else:
        guide_map = {
            "BUY": "익일 눌림 확인 후 진입",
            "BUY_WATCH": "익일 관심 유지",
            "WATCH": "익일 관심 유지",
            "HOLD": "익일보유 · 방어선 점검",
            "SELL_WATCH": "익일 소액매도 검토",
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
            "SELL_WATCH": "소액매도 검토가 우선입니다. 약세가 이어지면 절반정리 또는 매도로 강화합니다.",
            "SELL": "실행 가능한 매도 신호입니다. 반등 대기보다 정리를 우선합니다.",
            "NO_SIGNAL": "최신 전략 신호가 없어 조건 충족 전까지 관찰만 유지합니다.",
        }
    else:
        guide_map = {
            "BUY": "익일 시초 5~15분 대기 후 가격 안정 또는 첫 눌림 확인 뒤 분할 진입합니다.",
            "BUY_WATCH": "익일 관심 유지가 기본입니다. 시초 강도가 좋으면 소액매수를 검토하고, 아니면 관찰 유지로 둡니다.",
            "WATCH": "익일 관심 유지가 기본입니다. 주문보다 장초반 흐름 확인이 우선입니다.",
            "HOLD": "익일 보유 유지가 기본입니다. 시초 약세가 크면 비중축소, 방어선 이탈이면 매도로 전환합니다.",
            "SELL_WATCH": "익일 소액매도 검토가 우선입니다. 장초반 약세면 절반정리 또는 축소를 먼저 봅니다.",
            "SELL": "익일 장 초반 유동성 구간에서 매도를 우선합니다. 약세가 크면 지체 없이 정리합니다.",
            "NO_SIGNAL": "최신 전략 신호가 없어 다음 계산 시점까지 관찰만 유지합니다.",
        }
    return guide_map.get(signal, "장 시작 후 신호를 다시 확인합니다.")


def resolve_action_guide(row: pd.Series, *, execution_window: bool) -> str:
    key = "intraday_action_guide" if execution_window else "next_day_action_guide"
    value = str(row.get(key) or "").strip()
    if value and value.lower() not in {"nan", "none", "null"}:
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
        pct = float(text) / 100.0
    except Exception:
        return None
    return None if pd.isna(pct) else float(pct)


def _non_nan_float(value: Any) -> float | None:
    num = _safe_float(value, float("nan"))
    return None if pd.isna(num) else float(num)

def _latest_weekly_ma_from_price_panel(code: Any, window: int = 10) -> float | None:
    norm = str(code or "").strip().zfill(6)
    if not norm or not PRICE_PANEL_PATH.exists():
        return None
    try:
        df = pd.read_csv(PRICE_PANEL_PATH, usecols=["date", "code", "close"], dtype={"code": str}, low_memory=False)
        df = df[df["code"].astype(str).str.zfill(6) == norm].copy()
        if df.empty:
            return None
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["date", "close"]).sort_values("date")
        if df.empty:
            return None
        weekly = df.set_index("date")["close"].resample("W-FRI").last().dropna()
        if weekly.empty:
            return None
        ma = weekly.rolling(window=window, min_periods=1).mean().iloc[-1]
        return None if pd.isna(ma) else float(ma)
    except Exception:
        return None


def _risk_row_with_fallbacks(row: pd.Series | dict[str, Any]) -> pd.Series:
    base = row.copy() if isinstance(row, pd.Series) else pd.Series(dict(row))
    stop_pct = _parse_stop_pct(base.get("stop_rule"))
    if stop_pct is None and DEFAULT_FIXED_STOP_LOSS is not None:
        base["stop_rule"] = f"{DEFAULT_FIXED_STOP_LOSS:.0%}"
    return base


def compute_risk_levels(
    row: pd.Series | dict[str, Any],
    *,
    current_price: float | None,
    entry_price: float | None = None,
) -> dict[str, float | None]:
    row = _risk_row_with_fallbacks(row)
    stop_pct = _parse_stop_pct(row.get("stop_rule"))
    if stop_pct is None:
        stop_pct = DEFAULT_FIXED_STOP_LOSS
    day_20_ma = _non_nan_float(row.get("ma_day_20"))
    price_map = build_price_level_map(
        row.get("code"),
        buy_price=entry_price,
        buy_stop_pct=float(stop_pct),
        ma_stop_pct=DEFAULT_MA_STOP_LOSS,
    )
    initial_stop = price_map["buy_stop_price"]
    weekly_ma_price = price_map["weekly_ma_price"]
    weekly_ma_guard = price_map["weekly_ma_stop_price"]
    monthly_ma_price = price_map["monthly_ma_price"]
    monthly_ma_guard = price_map["monthly_ma_stop_price"]

    breakeven_guard = None
    if entry_price is not None and current_price is not None and current_price >= entry_price * 1.08:
        breakeven_guard = entry_price

    effective_candidates = [v for v in [initial_stop, breakeven_guard, weekly_ma_guard, monthly_ma_guard] if v is not None]
    effective_guard = max(effective_candidates) if effective_candidates else None

    return {
        "buy_price": price_map["buy_price"],
        "initial_stop": initial_stop,
        "breakeven_guard": breakeven_guard,
        "weekly_window": price_map["weekly_window"],
        "weekly_ma_price": weekly_ma_price,
        "weekly_ma_guard": weekly_ma_guard,
        "monthly_window": price_map["monthly_window"],
        "monthly_ma_price": monthly_ma_price,
        "monthly_ma_guard": monthly_ma_guard,
        "month_10_ma": monthly_ma_price,
        "week_10_ma": weekly_ma_price,
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
        avg_price = _non_nan_float(position_row.get("avg_price"))
        entry_from_row = _non_nan_float(position_row.get("entry_price"))
        if avg_price is not None:
            entry_price = avg_price
        elif entry_from_row is not None:
            entry_price = entry_from_row
    contract = v2_mode_contract_context(row)
    levels = build_contract_price_level_map(
        row.get("code"),
        current_price=float(base_price),
        buy_price=entry_price,
        buy_stop_pct=float(_parse_stop_pct(row.get("stop_rule")) or DEFAULT_FIXED_STOP_LOSS),
        ma_stop_pct=DEFAULT_MA_STOP_PCT,
        buy_timeframe=contract.get("buy_timeframe"),
        buy_window=contract.get("buy_window"),
        sell_timeframe=contract.get("sell_timeframe"),
        sell_window=contract.get("sell_window"),
        buy_ma_price_override=_row_contract_ma_price(row, "buy"),
        sell_ma_price_override=_row_contract_ma_price(row, "sell"),
    )
    parts = [resolve_action_guide(row, execution_window=execution_window), f"기준가 {base_price:,.0f}원({current_basis})"]

    if signal in {"BUY", "BUY_WATCH"}:
        watch_low = base_price * 0.99
        watch_high = base_price * 1.01
        no_chase = base_price * 1.02
        parts.append(f"관찰 구간 {watch_low:,.0f}~{watch_high:,.0f}원")
        parts.append(f"추격 금지 상단 {no_chase:,.0f}원")
        if levels["buy_stop_price"] is None:
            stop_pct = _parse_stop_pct(row.get("stop_rule"))
            if stop_pct is not None:
                parts.append(f"진입 후 초기 손절가 {base_price * (1.0 + stop_pct):,.0f}원")
        for side in ("buy", "sell"):
            timeframe = str(levels.get(f"{side}_timeframe") or "").strip().lower()
            window = levels.get(f"{side}_window")
            ma_price = levels.get(f"{side}_contract_ma_price")
            if not timeframe or window is None or ma_price is None or pd.isna(ma_price):
                continue
            side_label = "매수" if side == "buy" else "매도"
            parts.append(f"{side_label}이평가({_contract_timeframe_short_label(timeframe)}{int(window)}) {float(ma_price):,.0f}원")
        parts.append("익절 고정 목표가는 없고 추세 유지 여부로 재평가합니다.")
    elif signal in {"HOLD", "SELL", "SELL_WATCH"}:
        if levels["buy_price"] is not None:
            parts.append(f"매수가 {float(levels['buy_price']):,.0f}원")
        if levels["buy_stop_price"] is not None:
            parts.append(f"매수손절가 {float(levels['buy_stop_price']):,.0f}원")
        for side in ("buy", "sell"):
            timeframe = str(levels.get(f"{side}_timeframe") or "").strip().lower()
            window = levels.get(f"{side}_window")
            ma_price = levels.get(f"{side}_contract_ma_price")
            stop_price = levels.get(f"{side}_contract_stop_price")
            if not timeframe or window is None or ma_price is None or pd.isna(ma_price):
                continue
            side_label = "매수" if side == "buy" else "매도"
            parts.append(f"{side_label}이평가({_contract_timeframe_short_label(timeframe)}{int(window)}) {float(ma_price):,.0f}원")
            if stop_price is not None and not pd.isna(stop_price):
                parts.append(f"{side_label}이평손절가 {float(stop_price):,.0f}원")
        parts.append("가격 방어는 매수손절가와 계약 기준 이평손절가를 함께 점검합니다.")

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

BRIEFING_UPDATE_POLICY: dict[str, dict[str, str]] = {
    "company_info": {
        "label": "회사정보 / 컨센서스",
        "mode": "daily_once",
        "start": "07:00",
        "display": "07:00 / 1회",
    },
    "news": {
        "label": "최근 기사",
        "mode": "window_hourly",
        "start": "07:00",
        "end": "22:00",
        "display": "07:00-22:00 / 1시간",
    },
    "general_disclosure": {
        "label": "일반 공시",
        "mode": "daily_once",
        "start": "07:00",
        "display": "07:00 / 1회",
    },
    "financial_disclosure": {
        "label": "재무 공시",
        "mode": "pipeline",
        "display": "파이프라인 완료 후 반영",
    },
}
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
    padding: 4px 8px;
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    min-height: 52px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    gap: 2px;
}
.ns-card-stack {
    display: grid;
    gap: 4px;
}
.ns-summary-board {
    border: 1px solid #e5e7eb;
    border-radius: 18px;
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    overflow: hidden;
    height: 100%;
    display: flex;
    flex-direction: column;
}
.ns-summary-row {
    padding: 8px 10px 7px 10px;
    flex: 1 1 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.ns-summary-row + .ns-summary-row {
    border-top: 1px solid rgba(148, 163, 184, 0.18);
}
.ns-summary-label {
    font-size: 0.78rem;
    color: #475569;
    font-weight: 700;
    margin-bottom: 2px;
}
.ns-summary-value {
    font-size: 0.94rem;
    line-height: 1.14;
    font-weight: 800;
    color: #111827;
    white-space: normal;
    word-break: keep-all;
    overflow-wrap: anywhere;
}
.ns-summary-caption {
    margin-top: 2px;
    font-size: 0.72rem;
    line-height: 1.1;
    color: #475569;
}
.ns-summary-detail {
    margin-top: 2px;
    font-size: 0.72rem;
    line-height: 1.08;
    color: #64748b;
}
.ns-summary-divider {
    border-top: 1px solid rgba(148, 163, 184, 0.18);
}
[data-testid="stSlider"] [role="slider"] {
    width: 18px !important;
    height: 18px !important;
    cursor: ew-resize !important;
}
[data-testid="stSlider"] [role="slider"]:hover,
[data-testid="stSlider"] [role="slider"]:focus-visible {
    box-shadow: 0 0 0 5px rgba(239, 68, 68, 0.18) !important;
}
[data-testid="stSlider"] [data-testid="stSliderTickBar"] {
    padding-top: 0.9rem !important;
}
[data-testid="stSlider"] [data-testid="stSliderTickBarMin"],
[data-testid="stSlider"] [data-testid="stSliderTickBarMax"] {
    margin-top: 0.1rem !important;
}
.ns-overview-top,
.ns-overview-foot {
    padding: 9px 10px 8px 10px;
}
.ns-overview-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
}
.ns-overview-cell {
    padding: 8px 10px;
    min-height: 72px;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.ns-overview-cell + .ns-overview-cell {
    border-left: 1px solid rgba(148, 163, 184, 0.18);
}
@media (max-width: 980px) {
    .ns-overview-grid {
        grid-template-columns: 1fr;
    }
    .ns-overview-cell + .ns-overview-cell {
        border-left: 0;
        border-top: 1px solid rgba(148, 163, 184, 0.18);
    }
}
div[data-testid="stHorizontalBlock"]:has(.ns-summary-board):has(.ns-stage-guide-card) {
    align-items: stretch;
}
div[data-testid="stHorizontalBlock"]:has(.ns-summary-board):has(.ns-stage-guide-card) > div[data-testid="column"] {
    display: flex;
}
div[data-testid="stHorizontalBlock"]:has(.ns-summary-board):has(.ns-stage-guide-card) > div[data-testid="column"] > div {
    width: 100%;
}
.ns-card-label {
    font-size: 0.78rem;
    color: #475569;
    margin-bottom: 0;
    font-weight: 600;
}
.ns-card-value {
    font-size: 0.92rem;
    line-height: 1.12;
    font-weight: 700;
    color: #111827;
    white-space: normal;
    word-break: keep-all;
    overflow-wrap: anywhere;
}
.ns-card-caption {
    font-size: 0.72rem;
    line-height: 1.1;
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
.ns-axis-line .ns-trigger-buy {
    color: #2563eb;
    font-weight: 700;
}
.ns-axis-line .ns-trigger-sell {
    color: #dc2626;
    font-weight: 700;
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
.ns-detail-block-title {
    font-size: 1rem;
    font-weight: 800;
    color: #0f172a;
    margin: 0 0 0.45rem 0;
}
.ns-panel-card {
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 9px 11px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    min-height: 88px;
}
.ns-panel-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 4px;
}
.ns-panel-kicker {
    font-size: 0.74rem;
    line-height: 1.1;
    color: #64748b;
    font-weight: 700;
    white-space: nowrap;
    flex-shrink: 0;
}
.ns-panel-title {
    font-size: 0.92rem;
    line-height: 1.18;
    color: #0f172a;
    font-weight: 800;
    margin: 0;
    flex: 1 1 auto;
}
.ns-panel-line {
    font-size: 0.8rem;
    line-height: 1.28;
    color: #334155;
    margin: 0;
}
.ns-panel-line + .ns-panel-line {
    margin-top: 2px;
}
.ns-panel-note {
    font-size: 0.72rem;
    line-height: 1.24;
    color: #64748b;
    margin-top: 5px;
}
.ns-stage-guide-card {
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 11px 12px 10px 12px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}
.ns-stage-guide-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
}
.ns-stage-guide-top .ns-stage-guide-title {
    font-size: 0.94rem;
    line-height: 1.16;
    color: #0f172a;
    font-weight: 800;
}
.ns-stage-guide-top .ns-stage-guide-kicker {
    font-size: 0.74rem;
    line-height: 1.1;
    color: #64748b;
    font-weight: 700;
    white-space: nowrap;
}
.ns-stage-guide-stack {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
}
.ns-stage-guide-section {
    border: 1px solid #e5e7eb;
    border-radius: 13px;
    padding: 9px 10px;
    background: rgba(255, 255, 255, 0.82);
}
.ns-stage-guide-section.active {
    border-color: #bfdbfe;
    background: linear-gradient(180deg, #f8fbff 0%, #eef6ff 100%);
    box-shadow: inset 0 0 0 1px rgba(191, 219, 254, 0.38);
}
.ns-stage-guide-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 2px;
}
.ns-stage-guide-headline {
    font-size: 0.88rem;
    line-height: 1.12;
    color: #0f172a;
    font-weight: 800;
}
.ns-stage-guide-status {
    font-size: 0.68rem;
    line-height: 1;
    color: #1d4ed8;
    font-weight: 800;
    background: #dbeafe;
    border-radius: 999px;
    padding: 4px 7px;
}
.ns-stage-guide-caption {
    font-size: 0.73rem;
    line-height: 1.18;
    color: #64748b;
    margin-bottom: 7px;
}
.ns-stage-guide-list {
    display: grid;
    gap: 6px;
}
.ns-stage-guide-item {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px;
    align-items: start;
}
.ns-stage-guide-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 60px;
    padding: 3px 7px;
    border-radius: 999px;
    font-size: 0.7rem;
    line-height: 1.05;
    font-weight: 800;
    border: 1px solid transparent;
    white-space: nowrap;
}
.ns-stage-guide-pill.buy {
    color: #065f46;
    background: #ecfdf5;
    border-color: #bbf7d0;
}
.ns-stage-guide-pill.hold {
    color: #1d4ed8;
    background: #eff6ff;
    border-color: #bfdbfe;
}
.ns-stage-guide-pill.watch {
    color: #92400e;
    background: #fffbeb;
    border-color: #fde68a;
}
.ns-stage-guide-pill.sell {
    color: #9f1239;
    background: #fff1f2;
    border-color: #fecdd3;
}
.ns-stage-guide-copy {
    font-size: 0.77rem;
    line-height: 1.28;
    color: #334155;
    word-break: keep-all;
}
.ns-stage-guide-note {
    margin-top: 8px;
    font-size: 0.72rem;
    line-height: 1.22;
    color: #64748b;
}
@media (max-width: 980px) {
    .ns-stage-guide-stack {
        grid-template-columns: minmax(0, 1fr);
    }
}
.ns-brief-wrap {
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 11px 13px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}
.ns-brief-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 8px;
}
.ns-brief-chip-stack {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 6px;
}
.ns-brief-title {
    font-size: 0.96rem;
    line-height: 1.2;
    font-weight: 800;
    color: #0f172a;
}
.ns-brief-subtitle {
    font-size: 0.78rem;
    line-height: 1.22;
    color: #64748b;
    margin-top: 2px;
}
.ns-brief-chip {
    display: inline-flex;
    align-items: center;
    padding: 3px 8px;
    border-radius: 999px;
    font-size: 0.73rem;
    font-weight: 700;
    color: #1d4ed8;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
}
.ns-brief-body {
    font-size: 0.82rem;
    line-height: 1.38;
    color: #334155;
}
.ns-brief-body + .ns-brief-body {
    margin-top: 0.35rem;
}
.ns-brief-meta {
    font-size: 0.76rem;
    line-height: 1.3;
    color: #64748b;
    margin-top: 0.45rem;
}
.ns-brief-side-grid {
    display: grid;
    gap: 10px;
}
.ns-link-card {
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 11px 13px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}
.ns-link-card-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
}
.ns-link-card-title {
    font-size: 0.92rem;
    line-height: 1.18;
    font-weight: 800;
    color: #0f172a;
    margin: 0;
}
.ns-link-card-kicker {
    font-size: 0.72rem;
    line-height: 1.14;
    color: #64748b;
    white-space: nowrap;
    flex-shrink: 0;
}
.ns-link-list {
    display: grid;
    gap: 8px;
}
.ns-link-item {
    padding-bottom: 7px;
    border-bottom: 1px solid #eef2f7;
}
.ns-link-item:last-child {
    padding-bottom: 0;
    border-bottom: 0;
}
.ns-link-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
}
.ns-link-title {
    font-size: 0.81rem;
    line-height: 1.28;
    font-weight: 700;
    color: #0f172a;
    text-decoration: none;
    flex: 1 1 auto;
}
.ns-link-date {
    font-size: 0.72rem;
    line-height: 1.15;
    color: #64748b;
    white-space: nowrap;
    flex-shrink: 0;
}
.ns-link-meta {
    font-size: 0.75rem;
    line-height: 1.25;
    color: #64748b;
    margin-top: 3px;
}
.ns-link-note {
    font-size: 0.73rem;
    line-height: 1.22;
    color: #64748b;
    margin-top: 8px;
}
.ns-summary-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    margin: 0.05rem 0 0.35rem 0;
}
.ns-summary-title {
    font-size: 1rem;
    font-weight: 800;
    color: #0f172a;
    line-height: 1.15;
}
.ns-summary-meta {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 6px;
    text-align: right;
}
.ns-summary-chip {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 700;
    border: 1px solid #dbe3f0;
    background: #f8fafc;
    color: #0f172a;
}
.ns-summary-chip.price {
    background: #eff6ff;
    border-color: #bfdbfe;
    color: #1d4ed8;
}
.ns-summary-chip.signal {
    background: #f8fafc;
}
.ns-summary-note {
    font-size: 0.76rem;
    color: #64748b;
    line-height: 1.25;
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
    margin: 0.10rem 0 1.05rem 0;
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
.ns-section-head {
    display: flex;
    align-items: baseline;
    gap: 0.35rem;
    margin: 0.05rem 0 0.08rem 0;
}
.ns-section-head .ns-section-title {
    font-size: 1.08rem;
    font-weight: 800;
    line-height: 1.15;
    color: #0f172a;
}
.ns-section-head .ns-section-count {
    font-size: 0.93rem;
    font-weight: 700;
    line-height: 1.1;
    color: #64748b;
}
.ns-section-note {
    margin: 0 0 0.28rem 0;
    font-size: 0.82rem;
    line-height: 1.32;
    color: #64748b;
}
.ns-section-note code {
    font-family: inherit;
    font-size: inherit;
    font-weight: 600;
    color: inherit;
    background: transparent;
    padding: 0;
    border-radius: 0;
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
[data-testid="stSidebar"] .ns-sidebar-summary p {
    margin: 0.03rem 0 0.06rem 0;
    line-height: 1.18;
}
[data-testid="stSidebar"] .ns-sidebar-summary {
    margin-bottom: 0.18rem;
    border: 1px solid #dbe3f0;
    border-radius: 14px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    padding: 10px 10px 9px 10px;
}
[data-testid="stSidebar"] .ns-sidebar-summary-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 0.42rem;
}
[data-testid="stSidebar"] .ns-sidebar-summary-title {
    font-size: 0.86rem;
    line-height: 1.15;
    font-weight: 800;
    color: #0f172a;
}
[data-testid="stSidebar"] .ns-sidebar-summary-time {
    font-size: 0.71rem;
    line-height: 1.15;
    color: #64748b;
    font-weight: 600;
    white-space: nowrap;
}
[data-testid="stSidebar"] .ns-sidebar-summary-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 7px;
}
[data-testid="stSidebar"] .ns-sidebar-summary-item {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    background: #ffffff;
    padding: 7px 8px 6px 8px;
}
[data-testid="stSidebar"] .ns-sidebar-summary-label {
    font-size: 0.68rem;
    line-height: 1.12;
    color: #64748b;
    font-weight: 700;
    letter-spacing: 0.01em;
}
[data-testid="stSidebar"] .ns-sidebar-summary-value {
    font-size: 0.83rem;
    line-height: 1.16;
    color: #0f172a;
    font-weight: 800;
    margin-top: 2px;
}
[data-testid="stSidebar"] .ns-sidebar-summary-note {
    font-size: 0.69rem;
    line-height: 1.2;
    color: #64748b;
    margin-top: 0.45rem;
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


def _resolve_feature_snapshot_path() -> Path:
    if FEATURE_SNAPSHOT_PATH.exists():
        return FEATURE_SNAPSHOT_PATH
    if not LEGACY_FEATURE_SNAPSHOT_PATH.exists():
        return FEATURE_SNAPSHOT_PATH
    try:
        LEGACY_FEATURE_SNAPSHOT_PATH.replace(FEATURE_SNAPSHOT_PATH)
        return FEATURE_SNAPSHOT_PATH
    except Exception:
        # Keep one explicit migration path for already-generated legacy files.
        return LEGACY_FEATURE_SNAPSHOT_PATH


def build_version_tokens() -> dict[str, Any]:
    return {
        "output": (
            _file_stamp(SIGNAL_FAST_LATEST_PATH),
            _file_stamp(SIGNAL_LATEST_PATH),
            _file_stamp(SIGNAL_DAILY_PATH),
            _file_stamp(DECISION_FAST_LATEST_PATH),
            _file_stamp(DECISION_DAILY_PATH),
            _file_stamp(HEALTH_PATH),
            _file_stamp(EVAL_PATH),
            _file_stamp(RESEARCH_PATH),
            _file_stamp(RESEARCH_INDUSTRY_PATH),
            _file_stamp(RULE_TOP_PATH),
            _file_stamp(RULE_INDUSTRY_PATH),
            _file_stamp(V2_SIM_SUMMARY_PATH),
            _file_stamp(STRATEGY_META_PATH),
            _file_stamp(REFRESH_META_PATH),
            _file_stamp(FAST_ALERT_META_PATH),
            _file_stamp(SCHEDULE_STATE_PATH),
            _file_stamp(LIVE_QUOTES_PATH),
            _file_stamp(MANUAL_POSITIONS_PATH),
            _file_stamp(MANUAL_TRADES_PATH),
            _file_stamp(_resolve_feature_snapshot_path()),
            _file_stamp(FEATURE_DAILY_PATH),
            _file_stamp(TREND_SNAPSHOT_PATH),
            _file_stamp(TREND_DAILY_SCORES_PATH),
            _file_stamp(TREND_LINKS_PATH),
            _file_stamp(TREND_HOLDING_EXPOSURE_PATH),
            _file_stamp(TREND_COLLECTION_STATUS_PATH),
            _file_stamp(TREND_MENTIONS_ROLLING_PATH),
            _file_stamp(TREND_CLASSIFICATION_LOG_PATH),
            _file_stamp(TREND_TAXONOMY_PATH),
            _file_stamp(TREND_ALIAS_PATH),
            _file_stamp(TREND_UNCLASSIFIED_PATH),
        ),
        "macro": _file_stamp(MACRO_DAILY_PATH),
        "fundamental": _file_stamp(FUNDAMENTAL_PATH),
        "price": (
            _file_stamp(PRICE_SNAPSHOT_PATH),
            _file_stamp(PRICE_SNAPSHOT_META_PATH),
            _file_stamp(PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH),
            _file_stamp(PRICE_PANEL_INDUSTRY_SNAPSHOT_META_PATH),
        ),
        "optimal_ma": (
            _file_stamp(PRICE_PANEL_PATH),
            _file_stamp(OPTIMAL_MA_SELECTION_PATH),
            _file_stamp(OPTIMAL_MA_ALL_SELECTION_PATH),
            _file_stamp(OPTIMAL_MA_SNAPSHOT_PATH),
            _file_stamp(BEST_MODE_BY_STOCK_PATH),
        ),
    }


@st.cache_data(show_spinner=False)
def load_latest_data_dates(
    _price_meta_token: Any,
    _feature_meta_token: Any,
    _macro_token: Any,
    _fundamental_token: Any,
    _session_refresh_token: Any = "",
) -> dict[str, str]:
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
    feature_snapshot = _resolve_feature_snapshot_path()
    if feature_snapshot.exists():
        try:
            snapshot = pd.read_pickle(feature_snapshot)
            snapshot_dates = pd.to_datetime(snapshot["date"], errors="coerce").dropna()
            if not snapshot_dates.empty:
                result["feature_latest"] = str(snapshot_dates.max().date())
        except Exception:
            pass
    if result["feature_latest"] == "-" and FEATURE_DAILY_PATH.exists():
        try:
            feat = pd.read_pickle(FEATURE_DAILY_PATH)
            feat_dates = pd.to_datetime(feat["date"], errors="coerce").dropna()
            if not feat_dates.empty:
                result["feature_latest"] = str(feat_dates.max().date())
        except Exception:
            pass
    feature_meta = data_path("feature_daily_meta.json")
    if result["feature_latest"] == "-" and feature_meta.exists():
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
    latest = load_latest_data_dates(
        _file_stamp(data_path("price_panel_meta.json")),
        _file_stamp(data_path("feature_daily_meta.json")),
        data["version_tokens"]["macro"],
        data["version_tokens"]["fundamental"],
        data.get("session_refresh_token", ""),
    )
    krx_raw_latest = "-"
    try:
        raw_dates = []
        for path in stock_root().glob("basic_*.xlsx"):
            name = path.name
            if name.startswith("basic_") and name.endswith(".xlsx") and len(name) >= 18:
                raw_dates.append(name[6:14])
        if raw_dates:
            raw_latest = max(raw_dates)
            krx_raw_latest = f"{raw_latest[:4]}-{raw_latest[4:6]}-{raw_latest[6:8]}"
    except Exception:
        pass
    result = {
        "krx_raw_latest": str(krx_raw_latest or "-"),
        "price_latest": str(latest.get("price_latest", "-") or "-"),
        "feature_latest": str(latest.get("feature_latest", "-") or "-"),
        "macro_latest": str(latest.get("macro_latest", "-") or "-"),
        "fundamental_latest": str(latest.get("fundamental_latest", "-") or "-"),
    }
    krx_dt = pd.to_datetime(result["krx_raw_latest"], errors="coerce")
    price_dt = pd.to_datetime(result["price_latest"], errors="coerce")
    if pd.notna(krx_dt) and pd.notna(price_dt):
        lag_days = max(0, int((price_dt.normalize() - krx_dt.normalize()).days))
        result["krx_raw_lag_days"] = str(lag_days)
        result["krx_raw_stale"] = "yes" if lag_days >= 1 else "no"
    else:
        result["krx_raw_lag_days"] = "-"
        result["krx_raw_stale"] = "unknown"
    return result


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


def _sanitize_ohlc_frame_for_chart(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    for col in ["close", "open", "high", "low"]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["close"] = out["close"].where(np.isfinite(out["close"]) & (out["close"] > 0))
    out["open"] = out["open"].where(np.isfinite(out["open"]) & (out["open"] > 0)).combine_first(out["close"])
    valid_high = out["high"].where(np.isfinite(out["high"]) & (out["high"] > 0))
    valid_low = out["low"].where(np.isfinite(out["low"]) & (out["low"] > 0))
    out["high"] = pd.concat([valid_high, out["open"], out["close"]], axis=1).max(axis=1, skipna=True)
    out["low"] = pd.concat([valid_low, out["open"], out["close"]], axis=1).min(axis=1, skipna=True)
    out["close"] = out["close"].combine_first(out["open"])
    out["open"] = out["open"].combine_first(out["close"])
    return out.dropna(subset=["open", "high", "low", "close"])


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


def _safe_window_from_row(row: pd.Series | dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = pd.to_numeric(pd.Series([row.get(key)]), errors="coerce").iloc[0]
        if pd.notna(value) and int(float(value)) > 0:
            return int(float(value))
    return None


def _format_ma_axis_line(prefix: str, window: int | None, state: str, dist: float) -> str | None:
    if window is None or window <= 0:
        return None
    suffix = f" ({_safe_float(dist):+.1%})" if pd.notna(dist) else ""
    state_text = state.strip() if state else "확인"
    return f"{prefix}{int(window)} {state_text}{suffix}"


def _format_ma_axis_line_html(line: str) -> str:
    escaped = html.escape(str(line or "").strip())
    if not escaped:
        return "-"
    escaped = escaped.replace(
        "매수트리거",
        "<span class='ns-trigger-buy' style='color:#2563eb;font-weight:700;'>매수트리거</span>",
    )
    escaped = escaped.replace(
        "매도트리거",
        "<span class='ns-trigger-sell' style='color:#dc2626;font-weight:700;'>매도트리거</span>",
    )
    return escaped


def _optimal_ma_compact_text(row: pd.Series) -> str:
    contract = v2_mode_contract_context(row)
    lines: list[str] = []
    buy_label = contract.get("buy_short_label")
    sell_label = contract.get("sell_short_label")
    buy_window = contract.get("buy_window")
    sell_window = contract.get("sell_window")
    buy_dist = _safe_float(row.get("v2_buy_live_dist", row.get("v2_buy_period_dist", float("nan"))), float("nan"))
    sell_dist = _safe_float(row.get("v2_sell_live_dist", row.get("v2_sell_period_dist", float("nan"))), float("nan"))
    if buy_label is not None and buy_window is not None:
        buy_text = f"매수 {buy_label}{int(buy_window)}"
        if pd.notna(buy_dist):
            buy_text += f" ({buy_dist:+.1%})"
        lines.append(buy_text)
    if sell_label is not None and sell_window is not None:
        sell_text = f"매도 {sell_label}{int(sell_window)}"
        if pd.notna(sell_dist):
            sell_text += f" ({sell_dist:+.1%})"
        lines.append(sell_text)
    if lines:
        return "<br>".join(lines)
    return "없음"


def _optimal_ma_table_text(row: pd.Series | dict[str, Any]) -> str:
    contract = v2_mode_contract_context(row)
    parts: list[str] = []
    buy_label = contract.get("buy_short_label")
    sell_label = contract.get("sell_short_label")
    buy_window = contract.get("buy_window")
    sell_window = contract.get("sell_window")
    buy_dist = _safe_float(row.get("v2_buy_live_dist", row.get("v2_buy_period_dist", float("nan"))), float("nan"))
    sell_dist = _safe_float(row.get("v2_sell_live_dist", row.get("v2_sell_period_dist", float("nan"))), float("nan"))
    if buy_label is not None and buy_window is not None:
        buy_text = f"매수 {buy_label}{int(buy_window)}"
        if pd.notna(buy_dist):
            buy_text += f" ({buy_dist:+.1%})"
        parts.append(buy_text)
    if sell_label is not None and sell_window is not None:
        sell_text = f"매도 {sell_label}{int(sell_window)}"
        if pd.notna(sell_dist):
            sell_text += f" ({sell_dist:+.1%})"
        parts.append(sell_text)
    return " / ".join(parts) if parts else "없음"


def _optimal_ma_detail_text(row: pd.Series) -> str:
    contract = v2_mode_contract_context(row)
    if contract.get("buy_window") is None and contract.get("sell_window") is None:
        return "없음"
    lines: list[str] = []
    if contract.get("mode_label"):
        lines.append(str(contract["mode_label"]))
    buy_text = _contract_action_text(contract, "buy", detailed=True)
    sell_text = _contract_action_text(contract, "sell", detailed=True)
    if buy_text:
        lines.append(buy_text)
    if sell_text:
        lines.append(sell_text)
    return "<br>".join(lines)


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
def load_output_data(_version_token: Any, _session_refresh_token: Any = "") -> dict[str, Any]:
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
    signal_full = pd.DataFrame()
    if signal_latest_file.empty:
        signal_full_history = _read_csv(SIGNAL_DAILY_PATH)
        signal_full = latest_snapshot(signal_full_history)
    decision_fast = _read_csv(DECISION_FAST_LATEST_PATH)
    decision_full = latest_snapshot(_read_csv(DECISION_DAILY_PATH))
    return {
        "signals": signal_latest_file if not signal_latest_file.empty else (signal_full if not signal_full.empty else signal_fast),
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
        "trend_snapshot": _read_json(TREND_SNAPSHOT_PATH),
        "trend_scores": _read_csv(TREND_DAILY_SCORES_PATH),
        "trend_links": _read_csv(TREND_LINKS_PATH),
        "trend_holding_exposure": _read_csv(TREND_HOLDING_EXPOSURE_PATH),
        "trend_status": _read_csv(TREND_COLLECTION_STATUS_PATH),
        "trend_classification_log": _read_csv(TREND_CLASSIFICATION_LOG_PATH),
        "trend_taxonomy": _read_csv(TREND_TAXONOMY_PATH),
        "trend_unclassified": _read_csv(TREND_UNCLASSIFIED_PATH),
        "trend_aliases": _read_csv(TREND_ALIAS_PATH),
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

    price_df = load_price_forward_snapshot(_price_token)
    if price_df.empty:
        return pd.DataFrame()

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
def load_price_forward_snapshot(_price_token: Any) -> pd.DataFrame:
    if not PRICE_PANEL_PATH.exists():
        return pd.DataFrame(columns=["date", "code", "close_0d", "close_1d", "close_7d"])
    price_df = pd.read_csv(PRICE_PANEL_PATH, usecols=["date", "code", "close"], dtype={"code": str}, low_memory=False)
    if price_df.empty:
        return pd.DataFrame(columns=["date", "code", "close_0d", "close_1d", "close_7d"])
    price_df["code"] = price_df["code"].astype(str).str.zfill(6)
    price_df["date"] = pd.to_datetime(price_df["date"], errors="coerce")
    price_df["close"] = pd.to_numeric(price_df["close"], errors="coerce")
    price_df = price_df.dropna(subset=["date", "close"]).sort_values(["code", "date"])
    grp = price_df.groupby("code", sort=False)
    price_df["close_0d"] = price_df["close"]
    price_df["close_1d"] = grp["close"].shift(-1)
    price_df["close_7d"] = grp["close"].shift(-7)
    return price_df[["date", "code", "close_0d", "close_1d", "close_7d"]].copy()


@st.cache_data(show_spinner=False)
def load_feature_latest_snapshot(_output_token: Any, _session_refresh_token: Any = "") -> pd.DataFrame:
    path = _resolve_feature_snapshot_path()
    feature_path = FEATURE_DAILY_PATH
    needs_refresh = (not path.exists()) or (feature_path.exists() and path.stat().st_mtime < feature_path.stat().st_mtime)
    if needs_refresh:
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
def load_price_latest_snapshot(_price_token: Any, _session_refresh_token: Any = "") -> pd.DataFrame:
    return read_price_latest_snapshot(allow_refresh=False)


LIVE_V2_STATE_KEYS = [
    "v2_contract_mode",
    "v2_buy_timeframe",
    "v2_sell_timeframe",
    "v2_buy_window",
    "v2_sell_window",
    "v2_month_window",
    "v2_week_window",
    "v2_month_ma",
    "v2_week_ma",
    "v2_buy_ma",
    "v2_sell_ma",
    "v2_month_period_dist",
    "v2_month_prev_period_dist",
    "v2_week_period_dist",
    "v2_week_prev_period_dist",
    "v2_buy_period_dist",
    "v2_buy_prev_period_dist",
    "v2_sell_period_dist",
    "v2_month_buy_ready",
    "v2_month_buy_cross",
    "v2_month_above_maintain",
    "v2_month_sell_cross",
    "v2_week_sell_trigger",
    "v2_week_sell_watch",
    "v2_buy_ready",
    "v2_buy_cross",
    "v2_buy_above_maintain",
    "v2_buy_sell_cross",
    "v2_sell_trigger",
    "v2_sell_watch",
    "weekly_aux_ok",
    "monthly_main_ok",
]


@st.cache_data(show_spinner=False)
def load_live_v2_timing_states(
    codes: tuple[str, ...],
    _price_token: Any,
    _optimal_ma_token: Any,
    monthly_buy_threshold: float,
    weekly_sell_threshold: float,
    _session_refresh_token: Any = "",
) -> pd.DataFrame:
    normalized_codes = _normalize_code_tuple(codes)
    if not normalized_codes:
        return pd.DataFrame(columns=["code", *LIVE_V2_STATE_KEYS])

    price_df = load_price_panel_industry_base(_price_token)
    if price_df.empty:
        return pd.DataFrame(columns=["code", *LIVE_V2_STATE_KEYS])
    price_df = price_df[price_df["code"].isin(set(normalized_codes))].copy()
    if price_df.empty:
        return pd.DataFrame(columns=["code", *LIVE_V2_STATE_KEYS])

    base = price_df[["code", "date", "close"]].copy()
    cfg = EarningsStrategyConfig(
        monthly_buy_threshold=float(monthly_buy_threshold),
        weekly_sell_threshold=float(weekly_sell_threshold),
    )
    latest = add_v2_optimal_ma_features(base, cfg)
    if latest.empty:
        return pd.DataFrame(columns=["code", *LIVE_V2_STATE_KEYS])
    latest = (
        latest.sort_values(["code", "date"])
        .groupby("code", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
    for key in LIVE_V2_STATE_KEYS:
        if key not in latest.columns:
            latest[key] = np.nan
    return latest[["code", *LIVE_V2_STATE_KEYS]].copy()


def load_live_v2_timing_state(
    code: str,
    _price_token: Any,
    _optimal_ma_token: Any,
    monthly_buy_threshold: float,
    weekly_sell_threshold: float,
    _session_refresh_token: Any = "",
) -> dict[str, Any]:
    states = load_live_v2_timing_states(
        (str(code).zfill(6),),
        _price_token,
        _optimal_ma_token,
        monthly_buy_threshold,
        weekly_sell_threshold,
        _session_refresh_token,
    )
    if states.empty:
        return {}
    row = states.iloc[-1]
    return {key: row.get(key, np.nan) for key in LIVE_V2_STATE_KEYS}


def refresh_row_live_v2_timing(
    row: pd.Series | dict[str, Any],
    *,
    price_token: Any,
    optimal_ma_token: Any,
    cfg: dict[str, Any],
    session_refresh_token: Any = "",
) -> pd.Series:
    out = pd.Series(row).copy()
    code = str(out.get("code") or "").strip().zfill(6)
    if not code or code == "000000":
        return out
    live_state = load_live_v2_timing_state(
        code,
        price_token,
        optimal_ma_token,
        _safe_float(cfg.get("monthly_buy_threshold"), EarningsStrategyConfig().monthly_buy_threshold),
        _safe_float(cfg.get("weekly_sell_threshold"), EarningsStrategyConfig().weekly_sell_threshold),
        session_refresh_token,
    )
    if not live_state:
        return out
    for key, value in live_state.items():
        out[key] = value
    return out


def refresh_signal_df_live_v2_timing(
    signal_df: pd.DataFrame,
    *,
    price_token: Any,
    optimal_ma_token: Any,
    cfg: dict[str, Any],
    session_refresh_token: Any = "",
) -> pd.DataFrame:
    if signal_df.empty:
        return signal_df
    out = signal_df.copy()
    if "code" not in out.columns:
        return out
    holding_mask = out.get("is_real_holding", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    if not holding_mask.any():
        return out

    holding_codes = tuple(out.loc[holding_mask, "code"].astype(str).str.zfill(6).tolist())
    refreshed_df = load_live_v2_timing_states(
        holding_codes,
        price_token,
        optimal_ma_token,
        _safe_float(cfg.get("monthly_buy_threshold"), EarningsStrategyConfig().monthly_buy_threshold),
        _safe_float(cfg.get("weekly_sell_threshold"), EarningsStrategyConfig().weekly_sell_threshold),
        session_refresh_token,
    )
    if refreshed_df.empty:
        return out

    refreshed_map = refreshed_df.drop_duplicates(subset=["code"], keep="last").set_index("code")
    holding_codes_series = out.loc[holding_mask, "code"].astype(str).str.zfill(6)
    for key in LIVE_V2_STATE_KEYS:
        if key not in out.columns:
            out[key] = np.nan
        if key not in refreshed_map.columns:
            out.loc[holding_mask, key] = np.nan
            continue
        mapped = holding_codes_series.map(refreshed_map[key])
        out.loc[holding_mask, key] = mapped.values
    return out


def load_manual_positions_snapshot(_output_token: Any, _manual_positions_token: Any) -> pd.DataFrame:
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
def load_optimal_ma_chart_selection(_optimal_ma_token: Any) -> pd.DataFrame:
    if not OPTIMAL_MA_ALL_SELECTION_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(OPTIMAL_MA_ALL_SELECTION_PATH, dtype={"code": str}, low_memory=False)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["ma_timeframe"] = df["ma_timeframe"].astype(str).str.lower()
    return df


@st.cache_data(show_spinner=False)
def load_optimal_ma_timeframe_snapshot(_optimal_ma_token: Any, _session_refresh_token: Any = "") -> pd.DataFrame:
    df = load_optimal_ma_chart_selection(_optimal_ma_token)
    if df.empty:
        return pd.DataFrame(columns=["code", "monthly_optimal_window", "weekly_optimal_window", "daily_optimal_window"])

    latest = (
        df.sort_values(["code", "ma_timeframe"])
        .drop_duplicates(["code", "ma_timeframe"], keep="last")
        .copy()
    )
    keep = latest[["code", "ma_timeframe", "ma_window"]].copy()
    keep["ma_window"] = pd.to_numeric(keep["ma_window"], errors="coerce")
    pivot = (
        keep.pivot(index="code", columns="ma_timeframe", values="ma_window")
        .rename(
            columns={
                "monthly": "monthly_optimal_window",
                "weekly": "weekly_optimal_window",
                "daily": "daily_optimal_window",
            }
        )
        .reset_index()
    )
    return pivot


@st.cache_data(show_spinner=False)
def load_best_mode_contract_snapshot(_optimal_ma_token: Any, _session_refresh_token: Any = "") -> pd.DataFrame:
    columns = [
        "code",
        "v2_contract_mode",
        "v2_buy_timeframe",
        "v2_sell_timeframe",
        "v2_buy_window",
        "v2_sell_window",
    ]
    if not BEST_MODE_BY_STOCK_PATH.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(BEST_MODE_BY_STOCK_PATH, dtype={"code": str}, low_memory=False)
    if df.empty:
        return pd.DataFrame(columns=columns)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df = normalize_v2_mode_contract_frame(df)
    return df[columns].drop_duplicates(subset=["code"], keep="last").reset_index(drop=True)


def merge_best_mode_contract(frame: pd.DataFrame, contract_df: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or contract_df.empty:
        return frame.copy()
    work = frame.copy()
    work["code"] = work["code"].astype(str).str.zfill(6)
    merged = work.merge(contract_df, on="code", how="left", suffixes=("", "_contract"))
    for col in [column for column in contract_df.columns if column != "code"]:
        aux = f"{col}_contract"
        if aux not in merged.columns:
            continue
        if col in merged.columns:
            merged[col] = merged[col].combine_first(merged[aux])
        else:
            merged[col] = merged[aux]
        merged = merged.drop(columns=[aux])
    return merged


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


def format_intraday_basis(date_value: Any, quote_time_value: Any) -> str:
    qt = pd.to_datetime(quote_time_value, errors="coerce")
    if pd.notna(qt):
        return qt.strftime("%Y-%m-%d %H:%M:%S")
    dt = pd.to_datetime(date_value, errors="coerce")
    if pd.notna(dt):
        return f"{dt.date()} 실시간"
    return "-"


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
    if levels["buy_price"] is not None:
        parts.append(f"매수가 {levels['buy_price']:,.0f}원")
    if levels["initial_stop"] is not None:
        parts.append(f"매수손절 {levels['initial_stop']:,.0f}원")
    if levels["weekly_ma_price"] is not None:
        parts.append(f"주이평 {levels['weekly_ma_price']:,.0f}원")
    if levels["weekly_ma_guard"] is not None:
        parts.append(f"주이평손절 {levels['weekly_ma_guard']:,.0f}원")
    if levels["monthly_ma_price"] is not None:
        parts.append(f"월이평 {levels['monthly_ma_price']:,.0f}원")
    if levels["monthly_ma_guard"] is not None:
        parts.append(f"월이평손절 {levels['monthly_ma_guard']:,.0f}원")
    if levels["breakeven_guard"] is not None:
        parts.append(f"원금보호 {levels['breakeven_guard']:,.0f}원")
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

    def compact_optimal_ma_block(value: Any, *, is_real_holding: bool) -> str:
        raw = str(value or "").replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
        parts = [part.strip() for part in raw.splitlines() if part.strip()]
        if not parts:
            return "-"
        focus_token = "매도" if is_real_holding else "매수"
        line_html_parts: list[str] = []
        for part in parts:
            line_html = _format_ma_axis_line_html(part)
            if focus_token in str(part):
                line_html = f"<strong>{line_html}</strong>"
            line_html_parts.append(f"<div class='ns-axis-line'>{line_html}</div>")
        return "".join(line_html_parts)

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

    headers = ["의사결정", "종목", "근거 기준", "최적 MA", "주가 위치", "재무", "리스크", "실행 가이드"]
    col_widths = ["9%", "14%", "10%", "18%", "14%", "14%", "9%", "12%"]

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
        holding_value = row.get("is_real_holding", False)
        if pd.isna(holding_value):
            is_real_holding = False
        elif isinstance(holding_value, str):
            is_real_holding = holding_value.strip().lower() in {"1", "true", "y", "yes", "예", "보유"}
        else:
            is_real_holding = bool(holding_value)
        optimal_ma_html = compact_optimal_ma_block(row["최적 MA"], is_real_holding=is_real_holding)
        price_axis_html = compact_axis_block(row["주가 위치"])
        financial_html = compact_axis_block(row["재무"])
        risk_html = compact_axis_block(prettify_risk_flag(row["리스크"]).replace(" · ", "\n"), emphasize_first=False)
        guide_html = compact_axis_block(row["실행 가이드"], emphasize_first=False)
        cells = [decision_html, stock_html, basis_html, optimal_ma_html, price_axis_html, financial_html, risk_html, guide_html]
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
          overflow-x: hidden;
          overflow-y: hidden;
        }}
        table.ns-decision-table {{
          width: 100%;
          min-width: 100%;
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
        table.ns-decision-table thead th {{
          text-align: left;
          font-size: 13px;
          font-weight: 800;
          color: #0f172a;
          padding: 0 7px 7px 7px;
          border-bottom: 1px solid #dbe3f0;
          position: sticky;
          top: 0;
          z-index: 3;
          background: #ffffff;
          box-shadow: inset 0 -1px 0 #dbe3f0;
        }}
        table.ns-decision-table tbody td {{
          vertical-align: top;
          padding: 7px 7px;
          font-size: 12.2px;
          line-height: 1.3;
          word-break: keep-all;
          overflow-wrap: anywhere;
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
          font-size: 11.9px;
          padding-left: 5px;
          padding-right: 5px;
        }}
        table.ns-decision-table tbody td:nth-child(7),
        table.ns-decision-table tbody td:nth-child(8) {{
          line-height: 1.4;
        }}
        .ns-subtle-cell {{
          color: #64748b;
          font-size: 10.9px;
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
          font-size: 12.2px;
          font-weight: 700;
          color: #0f172a;
          margin-bottom: 2px;
        }}
        .ns-stock-name {{
          display: inline-block;
          font-size: 13.6px;
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
            <col><col><col><col><col><col><col><col>
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
    prices = load_price_forward_snapshot(_price_token)
    if prices.empty:
        return pd.DataFrame(), pd.DataFrame()

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

    prices = load_price_forward_snapshot(_price_token)
    if prices.empty:
        return pd.DataFrame(), pd.DataFrame()

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
        # 상세 검증 표는 체결시각 역순(최신 우선)으로 고정한다.
        # 매수/매도 그룹 생성 순서에 영향을 받지 않도록 최종 단계에서 정렬한다.
        detail["_체결시각_dt"] = pd.to_datetime(detail["체결시각"], errors="coerce")
        detail = detail.sort_values("_체결시각_dt", ascending=False, na_position="last")
        detail = detail.drop(columns=["_체결시각_dt"]).reset_index(drop=True)
    return summary, detail


@st.cache_data(show_spinner=False)
def load_macro(_version_token: Any, _session_refresh_token: Any = "") -> pd.DataFrame:
    df = _read_csv(MACRO_DAILY_PATH)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_fundamental(code: str, _version_token: Any, _session_refresh_token: Any = "") -> pd.DataFrame:
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
def load_price_history(code: str, _version_token: Any, _session_refresh_token: Any = "") -> pd.DataFrame:
    return load_price_history_for_codes((str(code).zfill(6),), _version_token, _session_refresh_token)


def _normalize_code_tuple(codes: tuple[str, ...]) -> tuple[str, ...]:
    normalized = {
        str(code or "").strip().zfill(6)
        for code in codes
        if str(code or "").strip()
    }
    normalized.discard("000000")
    return tuple(sorted(normalized))


@st.cache_data(show_spinner=False)
def load_price_history_for_codes(codes: tuple[str, ...], _version_token: Any, _session_refresh_token: Any = "") -> pd.DataFrame:
    normalized_codes = _normalize_code_tuple(codes)
    if not PRICE_PANEL_PATH.exists():
        return pd.DataFrame()
    if not normalized_codes:
        return pd.DataFrame(columns=["code", "name", "date", "open", "high", "low", "close", "volume", "trading_value", "market_cap", "industry"])
    frames: list[pd.DataFrame] = []
    cols = ["code", "name", "date", "open", "high", "low", "close", "volume", "trading_value", "market_cap", "industry"]
    code_set = set(normalized_codes)
    for chunk in pd.read_csv(PRICE_PANEL_PATH, usecols=cols, chunksize=250000, dtype={"code": str}, low_memory=False):
        chunk["code"] = chunk["code"].astype(str).str.zfill(6)
        part = chunk[chunk["code"].isin(code_set)]
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
    daily_latest: bool = False,
    refresh_optimal_ma: bool = False,
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
    if daily_latest:
        cmd.append("--daily-latest")
    if refresh_optimal_ma:
        cmd.append("--refresh-optimal-ma")
    if str(job_feedback_label).strip():
        cmd.extend(["--job-feedback-label", str(job_feedback_label).strip()])
    return cmd


def is_pid_running(pid: int | None) -> bool:
    try:
        pid_int = int(pid)
    except (TypeError, ValueError, OverflowError):
        return False
    if pid_int <= 0:
        return False
    if os.name == "nt":
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid_int}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=creationflags,
            )
            output = str(result.stdout or "").strip()
            if not output or "No tasks are running" in output or "정보:" in output:
                return False
            return f'"{pid_int}"' in output or f",{pid_int}," in output
        except Exception:
            # Fall back to os.kill probe below if tasklist is unavailable.
            pass
    try:
        os.kill(pid_int, 0)
        return True
    except PermissionError:
        # Windows may deny signal-style probes for a live process.
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False
    except Exception:
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


def run_trend_collect_now(*, run_at: datetime | None = None, timeout_seconds: int = 900) -> subprocess.CompletedProcess[str]:
    target_dt = run_at or datetime.now(SEOUL_TZ)
    if target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=SEOUL_TZ)
    else:
        target_dt = target_dt.astimezone(SEOUL_TZ)
    cmd = [
        sys.executable,
        "-m",
        "new_strategy.run_trend_pipeline",
        "--execute-once",
        "--run-at",
        target_dt.isoformat(timespec="seconds"),
    ]
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(60, int(timeout_seconds)),
        cwd=str(PROJECT_ROOT),
    )


def classify_signal(row: pd.Series, cfg: dict[str, Any]) -> str:
    is_real_holding = bool(row.get("is_real_holding", False))
    return _v2_display_signal(row, is_real_holding=is_real_holding)


def prepare_signal_display(
    signal_df: pd.DataFrame,
    cfg: dict[str, Any],
    real_holding_codes: set[str] | None = None,
    *,
    execution_window: bool | None = None,
) -> pd.DataFrame:
    if signal_df.empty:
        return signal_df
    execution_window = is_execution_window() if execution_window is None else execution_window
    df = signal_df.copy()
    real_holding_codes = set(real_holding_codes or set())
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["is_real_holding"] = df["code"].isin(real_holding_codes)
    df = _apply_display_signal_fields(df, cfg, execution_window=execution_window)
    if real_holding_codes:
        df = df[df["is_real_holding"] | df["display_signal"].isin(["BUY", "BUY_WATCH"])].copy()
    else:
        df = df[df["display_signal"].isin(["BUY", "BUY_WATCH"])].copy()
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
    *,
    prefer_fast: bool | None = None,
) -> pd.DataFrame:
    real_holding_codes = set(real_holding_codes or set())
    fast = signal_fast_df.copy() if not signal_fast_df.empty else pd.DataFrame()
    full = signal_df.copy() if not signal_df.empty else pd.DataFrame()
    prefer_fast = is_execution_window() if prefer_fast is None else prefer_fast

    if prefer_fast and not fast.empty:
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
        if (not prefer_fast) or fast.empty:
            return full

    if not fast.empty:
        fast["code"] = fast["code"].astype(str).str.zfill(6)
    return fast


def select_decision_snapshot(data: dict[str, Any], *, execution_window: bool | None = None) -> pd.DataFrame:
    execution_window = is_execution_window() if execution_window is None else execution_window
    fast = data.get("decision_fast", pd.DataFrame())
    full = data.get("decision", pd.DataFrame())
    if execution_window:
        return fast if not fast.empty else full
    return full if not full.empty else fast


def merge_latest_signal_sources(signal_df: pd.DataFrame, signal_fast_df: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    prefer_fast = is_execution_window()
    if not signal_fast_df.empty:
        fast = signal_fast_df.copy()
        fast["code"] = fast["code"].astype(str).str.zfill(6)
        fast["_source_rank"] = 0 if prefer_fast else 1
        frames.append(fast)
    if not signal_df.empty:
        full = signal_df.copy()
        full["code"] = full["code"].astype(str).str.zfill(6)
        full["_source_rank"] = 1 if prefer_fast else 0
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
    overlay = _sanitize_ohlc_frame_for_chart(overlay)
    if overlay.empty:
        return price_df, row.to_dict()
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


def enrich_signal_display(
    signal_df: pd.DataFrame,
    data: dict[str, Any],
    *,
    include_price_guides: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if signal_df.empty:
        return signal_df.copy(), {
            "feature_latest": pd.DataFrame(),
            "latest_price": pd.DataFrame(),
            "fast_state": pd.DataFrame(),
            "manual_positions": pd.DataFrame(),
        }

    out = signal_df.copy()
    session_refresh_token = data.get("session_refresh_token", "")
    feature_latest = load_feature_latest_snapshot(data["version_tokens"]["output"], session_refresh_token)
    latest_price = load_price_latest_snapshot(data["version_tokens"]["price"], session_refresh_token)
    fast_state = load_fast_position_state(data["version_tokens"]["output"])
    manual_positions = load_manual_positions_snapshot(data["version_tokens"]["output"], _file_stamp(MANUAL_POSITIONS_PATH))
    best_mode_contract = load_best_mode_contract_snapshot(data["version_tokens"]["optimal_ma"], session_refresh_token)

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
                out[base_col] = out[price_col].combine_first(out[base_col])
                out = out.drop(columns=[price_col])
        if "latest_industry" in out.columns:
            out["industry"] = out["industry"].fillna(out["latest_industry"])
            out = out.drop(columns=["latest_industry"])

    if not best_mode_contract.empty:
        out = merge_best_mode_contract(out, best_mode_contract)
    out = normalize_v2_mode_contract_frame(out)

    out["최적 MA"] = out.apply(_optimal_ma_compact_text, axis=1)
    out["최적 MA 상세"] = out.apply(_optimal_ma_detail_text, axis=1)
    out["V2 타이밍"] = out.apply(lambda row: format_v2_timing_summary(row), axis=1)

    if include_price_guides:
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
    else:
        out["가격 기준"] = out["latest_close"].map(lambda x: "-" if pd.isna(x) else f"{_safe_float(x):,.0f}원")
        out["가격 규칙"] = "-"
    out["리스크"] = out["risk_flag"].map(prettify_risk_flag).fillna("위험없음") if "risk_flag" in out.columns else "위험없음"

    return out, {
        "feature_latest": feature_latest,
        "latest_price": latest_price,
        "fast_state": fast_state,
        "manual_positions": manual_positions,
    }


def finalize_signal_axes(
    signal_df: pd.DataFrame,
    *,
    data: dict[str, Any],
    context: dict[str, Any],
    decision_df: pd.DataFrame,
    execution_window: bool | None = None,
    include_industry_context: bool = True,
) -> pd.DataFrame:
    if signal_df.empty:
        return signal_df.copy()

    out = normalize_v2_mode_contract_frame(normalize_v2_ma_frame(signal_df))
    last_decision = decision_df.sort_values("date").iloc[-1] if not decision_df.empty else None
    market_regime = str(last_decision.get("market_regime", "unknown")) if last_decision is not None else "unknown"
    market_exposure = _safe_float(last_decision.get("exposure"), float("nan")) if last_decision is not None else float("nan")
    execution_window = is_execution_window() if execution_window is None else execution_window

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

    out["stock_period_return"] = float("nan")
    out["industry_period_return"] = float("nan")
    contract_buy_tf = out.get("v2_buy_timeframe", pd.Series(index=out.index, dtype="object")).astype("string").str.strip().str.lower()
    contract_buy_window = pd.to_numeric(out.get("v2_buy_window", pd.Series(index=out.index)), errors="coerce")
    monthly_window = pd.to_numeric(out.get("v2_month_window", pd.Series(index=out.index)), errors="coerce")
    out["industry_timeframe"] = contract_buy_tf.fillna("monthly")
    out["industry_window"] = contract_buy_window.combine_first(monthly_window)
    out["industry_window_key"] = out["industry_window"].fillna(-1).astype(int)
    if include_industry_context:
        combo_df = (
            out.loc[out["industry_window_key"] > 0, ["industry_timeframe", "industry_window_key"]]
            .drop_duplicates()
            .copy()
        )
        combo_specs = tuple(
            (str(row["industry_timeframe"]).lower(), int(row["industry_window_key"]))
            for _, row in combo_df.iterrows()
        )
        if combo_specs:
            return_context = load_latest_return_context(data["version_tokens"]["price"], combo_specs)
            if not return_context.empty:
                merged_context = return_context.rename(columns={"industry_window": "industry_window_key"})
                out = out.merge(
                    merged_context,
                    on=["code", "industry_timeframe", "industry_window_key"],
                    how="left",
                    suffixes=("", "_ctx"),
                )
                for src, dst in [
                    ("stock_period_return_ctx", "stock_period_return"),
                    ("industry_period_return_ctx", "industry_period_return"),
                ]:
                    if src in out.columns:
                        out[dst] = out[src].combine_first(out[dst])
                        out = out.drop(columns=[src])
    out = out.drop(columns=["industry_window_key"], errors="ignore")

    out["최적 MA 축"] = out.apply(lambda row: format_v2_ma_axis_summary(row), axis=1)
    out["주가 위치 축"] = out.apply(lambda row: format_price_axis_summary(row), axis=1)
    out["재무 축"] = out.apply(lambda row: format_financial_axis_summary(row), axis=1)
    out["매크로 축"] = out.apply(lambda row: format_macro_axis_summary(row), axis=1)
    out["실행 요약"] = out.apply(lambda row: compact_execution_guide(row, execution_window=execution_window), axis=1)
    return out


@st.cache_data(show_spinner=False)
def build_strategy_report_payload(
    _output_token: Any,
    _price_token: Any,
    _fundamental_token: Any,
    _optimal_ma_token: Any,
    _manual_positions_token: Any,
    _execution_window: bool,
    _refresh_bucket: int = 0,
    _session_refresh_token: Any = "",
) -> dict[str, Any]:
    data = load_output_data(_output_token, _session_refresh_token)
    version_tokens = {
        "output": _output_token,
        "price": _price_token,
        "fundamental": _fundamental_token,
        "optimal_ma": _optimal_ma_token,
        "macro": 0,
    }
    cfg = load_default_config(data["meta"])
    manual_positions = load_manual_positions_snapshot(_output_token, _manual_positions_token)
    latest_price = load_price_latest_snapshot(_price_token, _session_refresh_token)
    real_holding_codes: set[str] = set()
    if not manual_positions.empty:
        real_holding_codes |= set(manual_positions["code"].astype(str).str.zfill(6))

    source_signal_df = select_v2_decision_signals(
        data["signals"],
        data.get("signals_fast", pd.DataFrame()),
        real_holding_codes=real_holding_codes,
        prefer_fast=_execution_window,
    )
    decision_df = select_decision_snapshot(data, execution_window=_execution_window)
    source_signal_df = append_manual_holding_placeholders(
        source_signal_df,
        real_holding_codes=real_holding_codes,
        manual_positions=manual_positions,
        latest_price=latest_price,
        decision_df=decision_df,
    )
    signal_df = prepare_signal_display(
        source_signal_df,
        cfg,
        real_holding_codes=real_holding_codes,
        execution_window=_execution_window,
    )
    if not signal_df.empty:
        buy_cross = signal_df.get("v2_buy_cross", signal_df.get("v2_month_buy_cross", pd.Series(False, index=signal_df.index))).fillna(False)
        signal_df = signal_df[signal_df["is_real_holding"] | buy_cross].copy()
        signal_df = signal_df.sort_values(["is_real_holding", "signal_rank", "code"], ascending=[False, True, True]).reset_index(drop=True)
        signal_df = refresh_signal_df_live_v2_timing(
            signal_df,
            price_token=version_tokens["price"],
            optimal_ma_token=version_tokens["optimal_ma"],
            cfg=cfg,
            session_refresh_token=_session_refresh_token,
        )
        signal_df = _apply_display_signal_fields(signal_df, cfg, execution_window=_execution_window)

    data["version_tokens"] = version_tokens
    signal_df, context = enrich_signal_display(signal_df, data, include_price_guides=False)
    signal_df = finalize_signal_axes(
        signal_df,
        data=data,
        context=context,
        decision_df=decision_df,
        execution_window=_execution_window,
        include_industry_context=True,
    )
    return {
        "cfg": cfg,
        "signal_df": signal_df,
        "decision_df": decision_df,
        "context": context,
    }


def resample_ohlcv(df: pd.DataFrame, timeframe: str, optimal_row: pd.Series | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date"])
    work = _sanitize_ohlc_frame_for_chart(work)
    if work.empty:
        return work
    frame = work.set_index("date").sort_index()
    optimal_timeframe = ""
    optimal_window = 0
    window = 0
    label = "없음"
    color = "#9ca3af"
    custom_label = ""
    custom_color = ""
    if optimal_row is not None:
        raw_timeframe = str(optimal_row.get("ma_timeframe") or "").strip()
        raw_window = optimal_row.get("ma_window")
        optimal_window = _safe_int(raw_window, 0)
        custom_label = str(optimal_row.get("ma_label") or "").strip()
        custom_color = str(optimal_row.get("ma_color") or "").strip()
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
    if custom_label:
        label = custom_label
    if custom_color:
        color = custom_color
    out["date"] = pd.to_datetime(out["date"])
    if window > 0:
        min_periods = max(1, min(window, max(5, int(window * 0.6))))
        out["ma_overlay"] = out["close"].rolling(window, min_periods=min_periods).mean()
    else:
        out["ma_overlay"] = np.nan
    out["ma_label"] = label
    out["ma_color"] = color
    return out


def build_optimal_overlay_series(price_df: pd.DataFrame, timeframe: str, optimal_row: pd.Series | None) -> pd.DataFrame:
    if price_df.empty or optimal_row is None:
        return pd.DataFrame(columns=["date", "overlay_value"])
    window = _safe_int(optimal_row.get("ma_window"), 0)
    if window <= 0:
        return pd.DataFrame(columns=["date", "overlay_value"])

    daily = price_df[["date", "close"]].copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
    daily = daily.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    if daily.empty:
        return pd.DataFrame(columns=["date", "overlay_value"])

    if timeframe == "일봉":
        out = daily.reset_index(drop=True)
    elif timeframe == "주봉":
        out = (
            daily.assign(week_key=daily["date"].dt.to_period("W-FRI"))
            .groupby("week_key", as_index=False)
            .agg(date=("date", "max"), close=("close", "last"))
            .sort_values("date")
            .reset_index(drop=True)
        )
    else:
        out = (
            daily.assign(month_key=daily["date"].dt.to_period("M"))
            .groupby("month_key", as_index=False)
            .agg(date=("date", "max"), close=("close", "last"))
            .sort_values("date")
            .reset_index(drop=True)
        )
    if out.empty:
        return pd.DataFrame(columns=["date", "overlay_value"])

    min_periods = max(1, min(window, max(5, int(window * 0.6))))
    out["overlay_value"] = out["close"].rolling(window, min_periods=min_periods).mean()
    return out[["date", "overlay_value"]].dropna(subset=["overlay_value"]).copy()


def _build_contract_chart_row(
    timeframe: str | None,
    window: int | float | None,
    *,
    side: str,
) -> dict[str, Any] | None:
    timeframe_key = str(timeframe or "").strip().lower()
    window_int = _safe_int(window, 0)
    if timeframe_key not in {"daily", "weekly", "monthly"} or window_int <= 0:
        return None
    short_label = _contract_timeframe_short_label(timeframe_key)
    side_label = "매수" if side == "buy" else "매도"
    color = _contract_side_color(side)
    return {
        "ma_timeframe": timeframe_key,
        "ma_window": window_int,
        "ma_label": f"{side_label} {short_label}{window_int}이평",
        "ma_color": color,
        "side": side,
    }


def _contract_chart_rows(row: pd.Series | dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    contract = v2_mode_contract_context(row)
    buy_row = _build_contract_chart_row(contract.get("buy_timeframe"), contract.get("buy_window"), side="buy")
    sell_row = _build_contract_chart_row(contract.get("sell_timeframe"), contract.get("sell_window"), side="sell")
    return buy_row, sell_row


def _primary_contract_chart_row(
    timeframe_key: str,
    buy_row: dict[str, Any] | None,
    sell_row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if buy_row is not None and str(buy_row.get("ma_timeframe")) == timeframe_key:
        return buy_row
    if sell_row is not None and str(sell_row.get("ma_timeframe")) == timeframe_key:
        return sell_row
    return None


def attach_contract_overlays(
    bars: pd.DataFrame,
    price_df: pd.DataFrame,
    *,
    timeframe: str,
    overlay_rows: list[dict[str, Any]],
    primary_row: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if bars.empty:
        return bars, []

    out = bars.copy().sort_values("date").reset_index(drop=True)
    overlay_specs: list[dict[str, Any]] = []

    for idx, overlay_row in enumerate(overlay_rows):
        if overlay_row is None or overlay_row == primary_row:
            continue
        source = build_contract_overlay_series(price_df, base_timeframe=timeframe, overlay_row=overlay_row)
        if source.empty:
            continue
        source = source[["date", "ma_value"]].copy()
        column = f"contract_overlay_{idx}"
        merged = pd.merge_asof(
            out[["date"]].sort_values("date"),
            source.sort_values("date"),
            on="date",
            direction="backward",
        ).rename(columns={"ma_value": column})
        out = out.merge(merged, on="date", how="left")
        if column in out.columns and not out[column].dropna().empty:
            overlay_specs.append(
                {
                    "column": column,
                    "label": str(overlay_row.get("ma_label") or column),
                    "color": str(overlay_row.get("ma_color") or "#111827"),
                }
            )

    return out, overlay_specs


def attach_cross_timeframe_overlays(
    bars: pd.DataFrame,
    price_df: pd.DataFrame,
    *,
    timeframe: str,
    monthly_optimal_row: pd.Series | None,
    weekly_optimal_row: pd.Series | None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if bars.empty:
        return bars, []

    out = bars.copy().sort_values("date").reset_index(drop=True)
    overlay_specs: list[dict[str, Any]] = []
    timeframe_key = {
        "일봉": "daily",
        "주봉": "weekly",
        "월봉": "monthly",
        "daily": "daily",
        "weekly": "weekly",
        "monthly": "monthly",
    }.get(str(timeframe).strip().lower(), str(timeframe).strip())

    def merge_overlay(
        source_timeframe: str,
        optimal_row: pd.Series | None,
        column: str,
        label_prefix: str,
        color: str,
    ) -> None:
        nonlocal out, overlay_specs
        if optimal_row is None:
            return
        window = _safe_int(optimal_row.get("ma_window"), 0)
        if window <= 0:
            return
        source = build_optimal_overlay_series(
            price_df,
            {"daily": "일봉", "weekly": "주봉", "monthly": "월봉"}.get(source_timeframe, source_timeframe),
            optimal_row,
        )
        if source.empty:
            return
        merged = pd.merge_asof(
            out[["date"]].sort_values("date"),
            source.sort_values("date"),
            on="date",
            direction="backward",
        ).rename(columns={"overlay_value": column})
        out = out.merge(merged, on="date", how="left")
        if column in out.columns and not out[column].dropna().empty:
            overlay_specs.append(
                {
                    "column": column,
                    "label": f"{label_prefix} {window}이평(최적)",
                    "color": color,
                }
            )

    if timeframe_key == "monthly":
        merge_overlay("weekly", weekly_optimal_row, "weekly_overlay", "주봉", "#059669")
    elif timeframe_key == "weekly":
        merge_overlay("monthly", monthly_optimal_row, "monthly_overlay", "월봉", "#7c3aed")
    else:
        merge_overlay("monthly", monthly_optimal_row, "monthly_overlay", "월봉", "#7c3aed")
        merge_overlay("weekly", weekly_optimal_row, "weekly_overlay", "주봉", "#059669")

    return out, overlay_specs


def build_weekly_monthly_gap_series(price_df: pd.DataFrame, monthly_optimal_row: pd.Series | None) -> pd.DataFrame:
    if price_df.empty:
        return pd.DataFrame()
    window = 0
    if monthly_optimal_row is not None:
        raw_window = monthly_optimal_row.get("ma_window")
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


def build_contract_overlay_series(
    price_df: pd.DataFrame,
    *,
    base_timeframe: str,
    overlay_row: dict[str, Any] | None,
) -> pd.DataFrame:
    if price_df.empty or overlay_row is None:
        return pd.DataFrame()
    overlay_timeframe = str(overlay_row.get("ma_timeframe") or "").strip().lower()
    window = _safe_int(overlay_row.get("ma_window"), 0)
    if overlay_timeframe not in {"daily", "weekly", "monthly"} or window <= 0:
        return pd.DataFrame()

    daily = price_df[["date", "close"]].copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
    daily = daily.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    if daily.empty:
        return pd.DataFrame()

    def _aggregate(series_df: pd.DataFrame, timeframe_key: str) -> pd.DataFrame:
        if timeframe_key == "daily":
            return series_df[["date", "close"]].copy().reset_index(drop=True)
        if timeframe_key == "weekly":
            return (
                series_df.assign(period_key=series_df["date"].dt.to_period("W-FRI"))
                .groupby("period_key", as_index=False)
                .agg(date=("date", "max"), close=("close", "last"))
                .sort_values("date")
                .reset_index(drop=True)
            )
        return (
            series_df.assign(period_key=series_df["date"].dt.to_period("M"))
            .groupby("period_key", as_index=False)
            .agg(date=("date", "max"), close=("close", "last"))
            .sort_values("date")
            .reset_index(drop=True)
        )

    overlay = _aggregate(daily, overlay_timeframe)
    if overlay.empty:
        return pd.DataFrame()
    min_periods = max(1, min(window, max(5, int(window * 0.6))))
    overlay["ma_value"] = overlay["close"].rolling(window, min_periods=min_periods).mean()
    overlay = overlay.dropna(subset=["ma_value"]).copy()
    if overlay.empty:
        return pd.DataFrame()

    target = _aggregate(daily, base_timeframe)
    if target.empty:
        return pd.DataFrame()
    out = pd.merge_asof(
        target.sort_values("date"),
        overlay[["date", "ma_value"]].sort_values("date"),
        on="date",
        direction="backward",
    )
    out = out.dropna(subset=["ma_value"]).copy()
    if out.empty:
        return out
    out["window"] = window
    return out


def build_contract_gap_series(
    price_df: pd.DataFrame,
    *,
    base_timeframe: str,
    overlay_row: dict[str, Any] | None,
) -> pd.DataFrame:
    out = build_contract_overlay_series(
        price_df,
        base_timeframe=base_timeframe,
        overlay_row=overlay_row,
    )
    if out.empty:
        return out
    out["gap_pct"] = out["close"] / out["ma_value"] - 1.0
    out["is_latest"] = False
    out.loc[out.index[-1], "is_latest"] = True
    return out


def build_monthly_gap_series(price_df: pd.DataFrame, monthly_optimal_row: pd.Series | None) -> pd.DataFrame:
    if price_df.empty:
        return pd.DataFrame()
    window = 0
    if monthly_optimal_row is not None:
        raw_window = monthly_optimal_row.get("ma_window")
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


def _chart_date_axis(
    frame: pd.DataFrame,
    *,
    title: str = "날짜",
    x_domain: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> tuple[pd.DataFrame, alt.X]:
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"]).copy()
    if out.empty:
        return out, alt.X("date:T", title=title)
    dates = out["date"].sort_values().dropna()
    gap_days = dates.diff().dt.days.dropna()
    median_gap = float(gap_days.median()) if not gap_days.empty else 1.0
    # Use discrete axis only for daily-like spacing to remove weekend gaps.
    if median_gap <= 3.5:
        span_days = max(1, int((out["date"].max() - out["date"].min()).days))
        fmt = "%Y-%m" if span_days >= 540 else "%Y-%m-%d"
        out["date_label"] = out["date"].dt.strftime(fmt)
        order = out.sort_values("date")["date_label"].drop_duplicates().tolist()
        x = alt.X(
            "date_label:N",
            title=title,
            sort=order,
            axis=alt.Axis(labelOverlap=True),
        )
        return out, x
    x_kwargs: dict[str, Any] = {"title": title, "axis": date_axis_for_chart(out)}
    scale = _date_scale_for_chart(x_domain)
    if scale is not None:
        x_kwargs["scale"] = scale
    return out, alt.X("date:T", **x_kwargs)


def _interactive_brush() -> alt.Parameter:
    return alt.selection_interval(
        encodings=["x"],
        mark=alt.BrushConfig(
            fill="#f97316",
            fillOpacity=0.12,
            stroke="#f97316",
            strokeWidth=2,
        ),
    )


def _candlestick_body_size(chart_df: pd.DataFrame) -> int:
    if chart_df.empty or "date" not in chart_df.columns:
        return 6
    dates = pd.to_datetime(chart_df["date"], errors="coerce").dropna().sort_values()
    if len(dates) < 2:
        return 6
    gap_days = dates.diff().dt.days.dropna()
    median_gap = float(gap_days.median()) if not gap_days.empty else 7.0
    count = int(len(dates))
    if median_gap >= 25:
        return 8 if count <= 90 else 7
    if median_gap >= 5:
        if count >= 110:
            return 4
        if count >= 80:
            return 5
        return 6
    if count >= 140:
        return 2
    if count >= 100:
        return 3
    return 4


def candlestick_chart(
    df: pd.DataFrame,
    title: str,
    x_domain: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    *,
    overlay_specs: list[dict[str, Any]] | None = None,
    brush: alt.Parameter | None = None,
) -> alt.Chart:
    if df.empty:
        return alt.Chart(pd.DataFrame({"date": [], "close": []})).mark_line()
    chart_df = df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        if col in chart_df.columns:
            chart_df[col] = pd.to_numeric(chart_df[col], errors="coerce")
    chart_df = chart_df.dropna(subset=["date", "open", "high", "low", "close"]).copy()
    chart_df, x_field = _chart_date_axis(chart_df, title="날짜", x_domain=x_domain)
    if chart_df.empty:
        return alt.Chart(pd.DataFrame({"date": [], "close": []})).mark_line()
    chart_df["상승"] = chart_df["close"] >= chart_df["open"]
    chart_df["body_low"] = chart_df[["open", "close"]].min(axis=1)
    chart_df["body_high"] = chart_df[["open", "close"]].max(axis=1)
    y_kwargs: dict[str, Any] = {"title": "가격", "scale": alt.Scale(zero=False, nice=True)}
    base = alt.Chart(chart_df).encode(
        x=x_field,
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
    wick = base.mark_rule().encode(y=alt.Y("low:Q", **y_kwargs), y2="high:Q", color=color)
    body = base.mark_bar(size=_candlestick_body_size(chart_df)).encode(y=alt.Y("body_low:Q", **y_kwargs), y2="body_high:Q", color=color)
    layers = wick + body
    if "ma_overlay" in chart_df.columns and not chart_df["ma_overlay"].dropna().empty:
        ma_color = chart_df["ma_color"].dropna().iloc[0] if "ma_color" in chart_df.columns and not chart_df["ma_color"].dropna().empty else "#f59e0b"
        ma_label = chart_df["ma_label"].dropna().iloc[0] if "ma_label" in chart_df.columns and not chart_df["ma_label"].dropna().empty else "이평선"
        ma_line = alt.Chart(chart_df).mark_line(color=ma_color, strokeWidth=2.0).encode(
            x=x_field,
            y=alt.Y("ma_overlay:Q", **y_kwargs),
            tooltip=[
                alt.Tooltip("date:T", title="날짜"),
                alt.Tooltip("ma_overlay:Q", title=ma_label, format=",.0f"),
            ],
        )
        layers = layers + ma_line
    for spec in overlay_specs or []:
        column = str(spec.get("column") or "").strip()
        if not column or column not in chart_df.columns or chart_df[column].dropna().empty:
            continue
        label = str(spec.get("label") or column)
        color = str(spec.get("color") or "#111827")
        overlay_line = alt.Chart(chart_df).mark_line(color=color, strokeWidth=2.0).encode(
            x=x_field,
            y=alt.Y(f"{column}:Q", **y_kwargs),
            tooltip=[
                alt.Tooltip("date:T", title="날짜"),
                alt.Tooltip(f"{column}:Q", title=label, format=",.0f"),
            ],
        )
        layers = layers + overlay_line
    if brush is not None:
        layers = layers.transform_filter(brush)
    chart = layers.properties(height=300)
    if str(title or "").strip():
        chart = chart.properties(title=title)
    return chart


def _contract_timeframe_short_label(timeframe: str | None) -> str:
    mapping = {"weekly": "주", "monthly": "월", "daily": "일"}
    return mapping.get(str(timeframe or "").strip().lower(), "")


def _contract_side_color(side: str) -> str:
    return "#059669" if str(side).strip().lower() == "buy" else "#dc2626"


def _row_contract_ma_price(row: pd.Series | dict[str, Any], side: str) -> float | None:
    value = _safe_float(row.get(f"v2_{side}_ma"), float("nan"))
    if pd.notna(value) and value != 0:
        return float(value)
    return None


def _contract_price_level_lines(
    code: str,
    *,
    row: pd.Series | dict[str, Any],
    current_price: float | None,
    buy_price: float | None,
) -> list[dict[str, Any]]:
    contract = v2_mode_contract_context(row)
    levels = build_contract_price_level_map(
        code,
        current_price=current_price if current_price is not None and not pd.isna(current_price) else None,
        buy_price=buy_price,
        buy_stop_pct=DEFAULT_FIXED_STOP_LOSS,
        ma_stop_pct=DEFAULT_MA_STOP_PCT,
        buy_timeframe=contract.get("buy_timeframe"),
        buy_window=contract.get("buy_window"),
        sell_timeframe=contract.get("sell_timeframe"),
        sell_window=contract.get("sell_window"),
        buy_ma_price_override=_row_contract_ma_price(row, "buy"),
        sell_ma_price_override=_row_contract_ma_price(row, "sell"),
    )
    lines: list[dict[str, Any]] = []
    for side in ("buy", "sell"):
        timeframe = str(levels.get(f"{side}_timeframe") or "").strip().lower()
        window = levels.get(f"{side}_window")
        ma_price = levels.get(f"{side}_contract_ma_price")
        stop_price = levels.get(f"{side}_contract_stop_price")
        if not timeframe or window is None or ma_price is None or pd.isna(ma_price):
            continue
        short_label = _contract_timeframe_short_label(timeframe)
        side_label = "매수" if side == "buy" else "매도"
        color = _contract_side_color(side)
        lines.append(
            {
                "label": f"{side_label}이평가 ({short_label}{int(window)})",
                "left_label": f"{side_label}이평가 ({short_label}{int(window)})",
                "right_label": f"{float(ma_price):,.0f}원",
                "price": float(ma_price),
                "x": 0.44,
                "x2": 0.56,
                "left_tx": 0.32,
                "right_tx": 0.68,
                "color": color,
                "dash": "solid",
            }
        )
        if stop_price is not None and not pd.isna(stop_price):
            lines.append(
                {
                    "label": f"{side_label}이평손절가",
                    "left_label": f"{side_label}이평손절가",
                    "right_label": f"{float(stop_price):,.0f}원",
                    "price": float(stop_price),
                    "x": 0.44,
                    "x2": 0.56,
                    "left_tx": 0.32,
                    "right_tx": 0.68,
                    "color": color,
                    "dash": "dashed",
                }
            )
    return lines


def _build_contract_gap_summary(
    code: str,
    *,
    row: pd.Series | dict[str, Any],
    current_price: float | None,
) -> str:
    if current_price is None or pd.isna(current_price):
        return ""
    contract = v2_mode_contract_context(row)
    levels = build_contract_price_level_map(
        code,
        current_price=float(current_price),
        buy_timeframe=contract.get("buy_timeframe"),
        buy_window=contract.get("buy_window"),
        sell_timeframe=contract.get("sell_timeframe"),
        sell_window=contract.get("sell_window"),
        buy_ma_price_override=_row_contract_ma_price(row, "buy"),
        sell_ma_price_override=_row_contract_ma_price(row, "sell"),
    )
    parts: list[str] = []
    for side in ("buy", "sell"):
        timeframe = str(levels.get(f"{side}_timeframe") or "").strip().lower()
        window = levels.get(f"{side}_window")
        dist = levels.get(f"{side}_contract_dist")
        if not timeframe or window is None or dist is None or pd.isna(dist):
            continue
        timeframe_prefix = _contract_timeframe_short_label(timeframe)
        side_label = "매수" if side == "buy" else "매도"
        color = _contract_side_color(side)
        parts.append(
            f"<span style='color:{color}; font-weight:600;'>{side_label} {timeframe_prefix}{int(window)} {float(dist):+.2%}</span>"
        )
    return " / ".join(parts)


def build_price_level_rows(
    code: str,
    *,
    current_price: float | None,
    buy_price: float | None,
    row: pd.Series | dict[str, Any] | None = None,
) -> pd.DataFrame:
    levels = build_price_level_map(code, buy_price=buy_price, buy_stop_pct=DEFAULT_FIXED_STOP_LOSS, ma_stop_pct=DEFAULT_MA_STOP_PCT)
    rows: list[dict[str, Any]] = []

    def add_row(label: str, price: float | None, color: str, dash: str, *, window: int | None = None, suffix: str = "") -> None:
        if price is None or pd.isna(price):
            return
        window_text = f" ({int(window)}{suffix})" if window is not None and suffix else ""
        rows.append(
            {
                "label": f"{label}{window_text}",
                "left_label": f"{label}{window_text}",
                "right_label": f"{price:,.0f}원",
                "price": float(price),
                "x": 0.44,
                "x2": 0.56,
                "left_tx": 0.32,
                "right_tx": 0.68,
                "color": color,
                "dash": dash,
            }
        )

    add_row("기준가", current_price, "#2563eb", "solid")
    add_row("매수가", levels["buy_price"], "#111827", "solid")
    add_row("매수손절가", levels["buy_stop_price"], "#dc2626", "dashed")
    if row is not None:
        rows.extend(_contract_price_level_lines(code, row=row, current_price=current_price, buy_price=buy_price))
    else:
        add_row("주이평가", levels["weekly_ma_price"], "#059669", "solid", window=levels["weekly_window"], suffix="주")
        add_row("주이평손절가", levels["weekly_ma_stop_price"], "#059669", "dashed")
        add_row("월이평가", levels["monthly_ma_price"], "#7c3aed", "solid", window=levels["monthly_window"], suffix="월")
        add_row("월이평손절가", levels["monthly_ma_stop_price"], "#7c3aed", "dashed")
    level_df = pd.DataFrame(rows)
    if level_df.empty:
        return level_df

    ranked = level_df.sort_values("price", ascending=False).reset_index()
    reference_price = float(max(ranked["price"].max(), 1.0))
    cluster_gap = max(reference_price * 0.015, 60.0)
    cluster_slot = 0
    prev_price: float | None = None
    left_positions: list[float] = []
    right_positions: list[float] = []
    for _, row in ranked.iterrows():
        price = float(row["price"])
        if prev_price is not None and abs(prev_price - price) < cluster_gap:
            cluster_slot = min(cluster_slot + 1, 2)
        else:
            cluster_slot = 0
        left_positions.append(0.32 - cluster_slot * 0.07)
        right_positions.append(0.68 + cluster_slot * 0.07)
        prev_price = price
    ranked["label_y"] = ranked["price"]
    ranked["left_tx_adj"] = left_positions
    ranked["right_tx_adj"] = right_positions
    level_df = level_df.merge(
        ranked[["index", "label_y", "left_tx_adj", "right_tx_adj"]],
        left_index=True,
        right_on="index",
        how="left",
    ).drop(columns=["index"])
    level_df["left_tx"] = level_df["left_tx_adj"]
    level_df["right_tx"] = level_df["right_tx_adj"]
    level_df = level_df.drop(columns=["left_tx_adj", "right_tx_adj"])
    return level_df


def price_level_map_chart(level_df: pd.DataFrame) -> alt.Chart:
    if level_df.empty:
        return alt.Chart(pd.DataFrame({"price": [], "x": []})).mark_rule()
    domain_min = float(min(level_df["price"].min(), level_df["label_y"].min()))
    domain_max = float(max(level_df["price"].max(), level_df["label_y"].max()))
    reference_price = float(max(domain_max, 1.0))
    domain_pad = max((domain_max - domain_min) * 0.10, reference_price * 0.08, 150.0)
    y_scale = alt.Scale(domain=[max(0.0, domain_min - domain_pad), domain_max + domain_pad], nice=False)
    rules = alt.Chart(level_df).mark_rule(strokeWidth=2).encode(
        x=alt.X("x:Q", axis=None, scale=alt.Scale(domain=[0, 1.2])),
        x2="x2:Q",
        y=alt.Y("price:Q", title="가격", scale=y_scale),
        color=alt.Color("color:N", scale=None, legend=None),
        strokeDash=alt.StrokeDash("dash:N", legend=None, scale=alt.Scale(domain=["solid", "dashed"], range=[[1, 0], [6, 4]])),
        tooltip=[alt.Tooltip("label:N", title="기준"), alt.Tooltip("price:Q", title="가격", format=",.0f")],
    )
    points = alt.Chart(level_df).mark_point(filled=True, size=70).encode(
        x=alt.X("x2:Q", axis=None, scale=alt.Scale(domain=[0, 1.2])),
        y=alt.Y("price:Q", scale=y_scale),
        color=alt.Color("color:N", scale=None, legend=None),
    )
    labels = alt.Chart(level_df).mark_text(align="left", dx=6, baseline="middle", fontSize=11).encode(
        x=alt.X("right_tx:Q", axis=None, scale=alt.Scale(domain=[0, 1.2])),
        y=alt.Y("label_y:Q", scale=y_scale),
        text="right_label:N",
        color=alt.Color("color:N", scale=None, legend=None),
    )
    left_labels = alt.Chart(level_df).mark_text(align="right", dx=-6, baseline="middle", fontSize=11).encode(
        x=alt.X("left_tx:Q", axis=None, scale=alt.Scale(domain=[0, 1.2])),
        y=alt.Y("label_y:Q", scale=y_scale),
        text="left_label:N",
        color=alt.Color("color:N", scale=None, legend=None),
    )
    return (rules + points + left_labels + labels).properties(height=260)


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
    brush: alt.Parameter | None = None,
) -> alt.Chart:
    chart_df = df[["date", column]].dropna().rename(columns={column: "value"})
    chart_df, x_field = _chart_date_axis(chart_df, title="날짜", x_domain=x_domain)
    if chart_df.empty:
        return alt.Chart(pd.DataFrame({"date": [], "value": []})).mark_line()
    chart = alt.Chart(chart_df).mark_line(color=color).encode(
        x=x_field,
        y=alt.Y("value:Q", title=title, scale=alt.Scale(zero=zero_baseline, nice=True)),
        tooltip=[alt.Tooltip("date:T", title="날짜"), alt.Tooltip("value:Q", title=title, format=",.2f")],
    )
    if brush is not None:
        chart = chart.transform_filter(brush)
    return chart.properties(height=150)


def percent_line_chart(
    df: pd.DataFrame,
    column: str,
    title: str,
    color: str,
    x_domain: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    *,
    brush: alt.Parameter | None = None,
) -> alt.Chart:
    chart_df = df[["date", column]].dropna().rename(columns={column: "value"})
    if chart_df.empty:
        return alt.Chart(pd.DataFrame({"date": [], "value": []})).mark_line()
    chart_df, x_field = _chart_date_axis(chart_df, title="날짜", x_domain=x_domain)
    if chart_df.empty:
        return alt.Chart(pd.DataFrame({"date": [], "value": []})).mark_line()
    base = alt.Chart(chart_df).encode(
        x=x_field,
        y=alt.Y("value:Q", title=title, axis=alt.Axis(format=".0%")),
        tooltip=[alt.Tooltip("date:T", title="날짜"), alt.Tooltip("value:Q", title=title, format=".2%")],
    )
    zero = alt.Chart(pd.DataFrame({"value": [0.0]})).mark_rule(color="#cbd5e1", strokeDash=[4, 4]).encode(y="value:Q")
    line = base.mark_line(color=color, strokeWidth=2.0)
    latest = base.transform_filter("datum.is_latest === true").mark_point(color=color, filled=True, size=90)
    if brush is not None:
        line = line.transform_filter(brush)
        latest = latest.transform_filter(brush)
    return (zero + line + latest).properties(height=155)


def overview_brush_chart(df: pd.DataFrame, brush: alt.Parameter, title: str = "가로축 범위") -> alt.Chart:
    chart_df = df[["date", "close"]].dropna().copy()
    if chart_df.empty:
        return alt.Chart(pd.DataFrame({"date": [], "close": []})).mark_line()
    chart_df["close"] = pd.to_numeric(chart_df["close"], errors="coerce")
    chart_df = chart_df.dropna(subset=["close"])
    area = alt.Chart(chart_df).mark_area(color="#e2e8f0", line={"color": "#94a3b8"}, opacity=0.9).encode(
        x=alt.X("date:T", title="날짜", axis=date_axis_for_chart(chart_df)),
        y=alt.Y("close:Q", title=None, axis=None, scale=alt.Scale(zero=False, nice=True)),
        tooltip=[alt.Tooltip("date:T", title="날짜"), alt.Tooltip("close:Q", title="종가", format=",.0f")],
    )
    return area.add_params(brush).properties(height=70, title=title)


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
        "순위",
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
        "언급수",
        "소스수",
        "언어수",
        "키워드수",
        "연결수",
        "건수",
        "횟수",
        "초",
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


def apply_f5_full_refresh_contract() -> str:
    session_key = "_ns_f5_full_refresh_contract_applied"
    if bool(st.session_state.get(session_key)):
        return str(st.session_state.get(session_key))
    # Contract: a fresh browser session gets a new refresh token so
    # stale-prone file-backed caches selectively reload without nuking
    # every global cache entry.
    st.session_state[session_key] = datetime.now(SEOUL_TZ).isoformat()
    return str(st.session_state[session_key])


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


def _parse_status_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _schedule_action_label(action: Any) -> str:
    mapping = {
        "krx_reconcile": "07:00 KRX 보조 갱신",
        "intraday_full_refresh_fast_alert": "30분 전종목 갱신",
        "eod_refresh_summary": "20:10 장후 EOD",
    }
    return mapping.get(str(action or "").strip(), str(action or "").strip() or "운영 스케줄")


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
    schedule_state = _read_json(SCHEDULE_STATE_PATH)
    schedule_run_at = _parse_status_timestamp(schedule_state.get("last_run_at"))
    schedule_action = _schedule_action_label(schedule_state.get("last_action"))
    progress_finished_at = _parse_status_timestamp(progress.get("finished_at")) if progress else None
    progress_updated_at = _parse_status_timestamp(progress.get("updated_at")) if progress else None
    progress_reference_at = progress_finished_at or progress_updated_at

    def _schedule_card() -> str:
        captions = []
        if schedule_run_at is not None:
            captions.append(f"마지막 완료 {schedule_run_at.strftime('%m-%d %H:%M')}")
        captions.append(schedule_action)
        return (
            "<div class='ns-status-card idle'>"
            "<div class='ns-status-head'><div class='ns-status-label'>Status</div>"
            "<div class='ns-status-pill'>Run</div></div>"
            f"<div class='ns-status-action'>{html.escape(schedule_action)}</div>"
            f"<div class='ns-status-caption'>{html.escape(' · '.join(captions))}</div>"
            "</div>"
        )

    if not progress:
        if schedule_run_at is not None:
            return _schedule_card()
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
    if schedule_run_at is not None and (progress_reference_at is None or schedule_run_at > progress_reference_at):
        return _schedule_card()
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
    latest_dates = runtime_latest_dates(data)
    strategy_id = str(cfg.get("strategy_id", "earnings_pti_v2"))
    trend_mode = str(cfg.get("trend_mode", "optimal_ma_v2"))
    monthly_buy = _safe_float(cfg.get("monthly_buy_threshold"), 0.0)
    weekly_sell = _safe_float(cfg.get("weekly_sell_threshold"), -0.05)
    last_decision = data["decision"].sort_values("date").iloc[-1] if not data["decision"].empty else None
    regime = market_state_label(str(last_decision.get("market_regime", "unknown"))) if last_decision is not None else "-"
    exposure = _safe_float(last_decision.get("exposure"), float("nan")) if last_decision is not None else float("nan")
    target_positions = _safe_int(last_decision.get("target_positions"), 0) if last_decision is not None else 0
    latest_signal_date = str(pd.to_datetime(data["signals_fast"]["date"], errors="coerce").max().date()) if not data["signals_fast"].empty else "-"
    krx_stale = str(latest_dates.get("krx_raw_stale", "unknown")) == "yes"
    krx_lag_days = str(latest_dates.get("krx_raw_lag_days", "-"))

    st.subheader("전략보드")
    cols = st.columns(3)
    with cols[0]:
        st.markdown("**전략 기준**")
        st.markdown(
            "\n".join(
                [
                    f"- 실행 기본형: `월봉매수 / 주봉매도 / buy_{monthly_buy:.0%}__sell_{weekly_sell:.0%}`",
                    f"- strategy_id: `{strategy_id}`",
                    f"- trend_mode: `{trend_mode}`",
                    f"- fast 최신일: `{latest_signal_date}`",
                    f"- KRX 원천 최신일: `{latest_dates.get('krx_raw_latest', '-')}`",
                    f"- price_panel 최신일: `{latest_dates.get('price_latest', '-')}`",
                    (
                        f"- KRX 보조 지연: `+{krx_lag_days}일` (price_panel 대비)"
                        if krx_stale
                        else "- KRX 보조 지연: `없음`"
                    ),
                    "- UI 새로고침 계약: `F5` 시 관련 캐시만 다시 읽고 파일 원본 기준으로 재구성합니다.",
                    "- 변경 후 점검 계약: `python -m py_compile streamlit_app.py` + 의사결정 상세차트 렌더 확인 후 반영합니다.",
                ]
            )
        )
    with cols[1]:
        st.markdown("**운영 스케줄**")
        st.markdown(
            "\n".join(
                [
                    "- `06:00` 글로벌 트렌드 수집(직전 24시간)",
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
    st.markdown("**종목 브리핑 갱신 정책**")
    st.markdown("\n".join(build_briefing_policy_rows()))
    st.markdown("**최종 의사결정 매핑**")
    mapping_cols = st.columns(5)
    mapping_specs = [
        ("BUY", ["미보유", "월봉 신규 상향돌파", "주봉 정상", "재무 통과", "주가 위치 양호"]),
        ("BUY_WATCH", ["미보유", "월봉 유지상방 또는 신규 상향돌파", "주봉 경계 또는 가격 부담", "추가 확인 후 진입"]),
        ("HOLD", ["보유", "월봉 유지상방", "주봉 정상", "기본 보유 유지"]),
        ("SELL_WATCH", ["보유", "월봉은 유지상방", "주봉 매도경계", "소액매도 우선 검토"]),
        ("SELL", ["보유", "주봉 매도트리거 또는 월봉 하향 전환", "손절/재무 훼손 포함", "청산 우선"]),
    ]
    for col, (title, lines) in zip(mapping_cols, mapping_specs):
        with col:
            st.markdown(f"**{signal_label(title)}**")
            st.markdown("\n".join([f"- {line}" for line in lines]))

    st.markdown("**수동 작업**")
    action_cols = st.columns(2)
    with action_cols[0]:
        if st.button("저장값으로 일일 최신판단 재계산", use_container_width=True, key="ops_daily_latest_refresh"):
            launch_pipeline_job(
                cfg,
                "저장값으로 일일 최신판단 재계산",
                daily_latest=True,
                job_feedback_label="일일 최신판단 재계산",
            )
            st.rerun()
    with action_cols[1]:
        if st.button("최적 MA 업데이트", use_container_width=True, key="ops_refresh_optimal_ma"):
            launch_pipeline_job(
                cfg,
                "최적 MA 업데이트 + 최신판단 반영",
                refresh_optimal_ma=True,
                daily_latest=True,
                job_feedback_label="최적 MA 업데이트",
            )
            st.rerun()
    st.caption("최적 MA 기준표는 수동 버튼을 눌렀을 때만 갱신됩니다. 운영 중에는 고정된 snapshot을 사용하고, 가격·매크로·재무가 바뀔 때만 최신 판단이 다시 계산됩니다.")


def render_operations_page(data: dict[str, Any]) -> None:
    render_page_heading("전략보드", kicker="Operations", subtitle="V2 전략 기준, 운영 스케줄, 현재 운용 상태를 확인합니다.")
    render_operation_panel(data)
    st.markdown("<div class='ns-section-divider'></div>", unsafe_allow_html=True)
    with st.expander("V2 전략 정리", expanded=True):
        render_strategy_logic(load_default_config(data["meta"]))
        render_term_notes()
    with st.expander("데이터 최신 상태", expanded=False):
        latest_dates = runtime_latest_dates(data)
        stale_caption = ""
        if str(latest_dates.get("krx_raw_stale", "unknown")) == "yes":
            stale_caption = f" · KRX 보조 지연 +{latest_dates.get('krx_raw_lag_days', '-')}일"
        st.caption(
            f"KRX 원천 `{latest_dates.get('krx_raw_latest', '-')}` · "
            f"price_panel `{latest_dates.get('price_latest', '-')}` · "
            f"feature `{latest_dates.get('feature_latest', '-')}`"
            f"{stale_caption}"
        )
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
    latest_dates = runtime_latest_dates(data)
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

    def _count_flag(*keys: str) -> int:
        for key in keys:
            if key in signal_df.columns:
                series = pd.Series(signal_df[key], index=signal_df.index)
                return int(series.fillna(False).astype(bool).sum())
        return 0

    def _decision_item(label: str, count: int) -> str:
        cls = "active" if count > 0 else "inactive"
        return f"<span class='ns-decision-item {cls}'>{html.escape(label)} {count}</span>"

    latest_refresh = str(latest_dates.get("price_latest", "-") or latest_date)
    feature_latest = str(latest_dates.get("feature_latest", "-") or "-")
    month_cross_count = _count_flag("v2_month_buy_cross", "v2_buy_cross")
    month_maintain_count = _count_flag("v2_month_above_maintain", "v2_buy_above_maintain")
    week_watch_count = _count_flag("v2_week_sell_watch", "v2_sell_watch")
    week_sell_count = _count_flag("v2_week_sell_trigger", "v2_sell_trigger")
    return [
        {
            "label": "분석일자 / 실행일자",
            "value": f"분석 {latest_date} / 실행 {execution_date}",
            "caption": f"주가 {latest_refresh} · feature {feature_latest} · 장중fast {fast_latest_date}",
        },
        {
            "label": "시장 상태",
            "value": regime_label,
            "caption": f"운용강도 {intensity_label} · 노출 {exposure:.2f} · 목표 {target_positions}개",
        },
        {
            "label": "오늘 액션",
            "value_html": " · ".join(
                [
                    _decision_item("매도", sell_count),
                    _decision_item("소액매도", reduce_count),
                ]
            ),
            "caption_html": _decision_item("보유", hold_count),
            "detail_html": " · ".join(
                [
                    _decision_item("매수", buy_count),
                    _decision_item("관심", watch_count),
                ]
            ),
        },
        {
            "label": "V2 트리거",
            "value_html": " · ".join(
                [
                    _decision_item("월돌파", month_cross_count),
                    _decision_item("월유지", month_maintain_count),
                ]
            ),
            "caption_html": " · ".join(
                [
                    _decision_item("주경계", week_watch_count),
                    _decision_item("주매도", week_sell_count),
                ]
            ),
        },
    ]


def _parse_hhmm(text: str) -> tuple[int, int]:
    raw = str(text or "").strip()
    hour_text, minute_text = raw.split(":", 1)
    return int(hour_text), int(minute_text)


def briefing_policy_display(policy_key: str) -> str:
    policy = BRIEFING_UPDATE_POLICY.get(str(policy_key), {})
    return str(policy.get("display") or "-")


def briefing_policy_refresh_token(policy_key: str, *, now: datetime | None = None) -> str:
    policy = BRIEFING_UPDATE_POLICY.get(str(policy_key), {})
    mode = str(policy.get("mode") or "")
    current = now.astimezone(SEOUL_TZ) if now is not None else datetime.now(SEOUL_TZ)
    if mode == "daily_once":
        start_hour, start_minute = _parse_hhmm(str(policy.get("start") or "07:00"))
        start_clock = time(start_hour, start_minute)
        anchor_date = current.date() if current.timetz().replace(tzinfo=None) >= start_clock else (current.date() - timedelta(days=1))
        return f"{policy_key}:{anchor_date.isoformat()}:{start_hour:02d}{start_minute:02d}"
    if mode == "window_hourly":
        start_hour, start_minute = _parse_hhmm(str(policy.get("start") or "07:00"))
        end_hour, end_minute = _parse_hhmm(str(policy.get("end") or "22:00"))
        current_clock = current.timetz().replace(tzinfo=None)
        start_clock = time(start_hour, start_minute)
        end_clock = time(end_hour, end_minute)
        if current_clock < start_clock:
            anchor_date = current.date() - timedelta(days=1)
            slot_hour, slot_minute = end_hour, end_minute
        elif current_clock >= end_clock:
            anchor_date = current.date()
            slot_hour, slot_minute = end_hour, end_minute
        else:
            anchor_date = current.date()
            slot_hour, slot_minute = current.hour, 0
        return f"{policy_key}:{anchor_date.isoformat()}:{slot_hour:02d}{slot_minute:02d}"
    return f"{policy_key}:static"


def build_briefing_policy_rows() -> list[str]:
    ordered_keys = ["company_info", "news", "general_disclosure", "financial_disclosure"]
    rows: list[str] = []
    for key in ordered_keys:
        policy = BRIEFING_UPDATE_POLICY.get(key, {})
        label = str(policy.get("label") or key)
        rows.append(f"- {label}: `{briefing_policy_display(key)}`")
    return rows


def _summary_card_html(card: dict[str, str]) -> str:
    label = html.escape(str(card["label"]))
    if "value_html" in card:
        value = str(card["value_html"]).replace("\n", "<br>")
    else:
        value = html.escape(str(card["value"])).replace("\n", "<br>")
    if "caption_html" in card:
        caption = str(card["caption_html"]).replace("\n", "<br>")
    else:
        caption = html.escape(str(card["caption"])).replace("\n", "<br>")
    return (
        "<div class='ns-card'>"
        f"<div class='ns-card-label'>{label}</div>"
        f"<div class='ns-card-value'>{value}</div>"
        f"<div class='ns-card-caption'>{caption}</div>"
        "</div>"
    )


def render_cards(cards: list[dict[str, str]]) -> None:
    ratios = [1.35, 0.95, 1.15] if len(cards) == 3 else [1.0] * len(cards)
    cols = st.columns(ratios)
    for col, card in zip(cols, cards):
        with col:
            st.markdown(_summary_card_html(card), unsafe_allow_html=True)


def render_card_stack(cards: list[dict[str, str]]) -> None:
    stack_html = "<div class='ns-card-stack'>" + "".join(_summary_card_html(card) for card in cards) + "</div>"
    st.markdown(stack_html, unsafe_allow_html=True)


def _summary_row_html(card: dict[str, str]) -> str:
    label = html.escape(str(card["label"]))
    if "value_html" in card:
        value = str(card["value_html"]).replace("\n", "<br>")
    else:
        value = html.escape(str(card["value"])).replace("\n", "<br>")
    if "caption_html" in card:
        caption = str(card["caption_html"]).replace("\n", "<br>")
    else:
        caption = html.escape(str(card["caption"])).replace("\n", "<br>")
    return (
        "<div class='ns-summary-row'>"
        f"<div class='ns-summary-label'>{label}</div>"
        f"<div class='ns-summary-value'>{value}</div>"
        f"<div class='ns-summary-caption'>{caption}</div>"
        "</div>"
    )


def render_summary_board(cards: list[dict[str, str]]) -> None:
    if len(cards) >= 4:
        update_card, market_card, action_card, trigger_card = cards[:4]

        def _section_html(card: dict[str, str], extra_class: str = "") -> str:
            label = html.escape(str(card["label"]))
            if "value_html" in card:
                value = str(card["value_html"]).replace("\n", "<br>")
            else:
                value = html.escape(str(card["value"])).replace("\n", "<br>")
            if "caption_html" in card:
                caption = str(card["caption_html"]).replace("\n", "<br>")
            else:
                caption = html.escape(str(card["caption"])).replace("\n", "<br>")
            if "detail_html" in card:
                detail = str(card["detail_html"]).replace("\n", "<br>")
            else:
                detail = html.escape(str(card.get("detail", ""))).replace("\n", "<br>")
            detail_html = f"<div class='ns-summary-detail'>{detail}</div>" if detail else ""
            return (
                f"<div class='{extra_class}'>"
                f"<div class='ns-summary-label'>{label}</div>"
                f"<div class='ns-summary-value'>{value}</div>"
                f"<div class='ns-summary-caption'>{caption}</div>"
                f"{detail_html}"
                "</div>"
            )

        board_html = (
            "<div class='ns-summary-board'>"
            + _section_html(update_card, "ns-overview-top")
            + "<div class='ns-summary-divider'></div>"
            + "<div class='ns-overview-grid'>"
            + _section_html(market_card, "ns-overview-cell")
            + _section_html(action_card, "ns-overview-cell")
            + "</div>"
            + "<div class='ns-summary-divider'></div>"
            + _section_html(trigger_card, "ns-overview-foot")
            + "</div>"
        )
    else:
        board_html = "<div class='ns-summary-board'>" + "".join(_summary_row_html(card) for card in cards) + "</div>"
    st.markdown(board_html, unsafe_allow_html=True)


def build_decision_stage_guide_sections() -> list[dict[str, Any]]:
    return [
        {
            "title": "장중",
            "caption": "시초/장중 흐름 확인 후 대응",
            "execution_window": True,
            "items": [
                ("BUY", "미보유 · 시초 확인 후 분할매수"),
                ("BUY_WATCH", "미보유 · 강도 좋으면 소액 진입"),
                ("HOLD", "보유 · 방어선 이탈 전 유지"),
                ("SELL_WATCH", "보유 · 약세 확대 시 소액매도"),
                ("SELL", "보유 · 매도선 이탈 시 청산 우선"),
            ],
        },
        {
            "title": "장후",
            "caption": "종가 확정 후 익일 계획 정리",
            "execution_window": False,
            "items": [
                ("BUY", "미보유 · 신규 상향돌파 확인"),
                ("BUY_WATCH", "미보유 · 근접/유지 구간"),
                ("HOLD", "보유 · 매수선 위 유지"),
                ("SELL_WATCH", "보유 · 매도선 근접"),
                ("SELL", "보유 · 하향돌파 또는 월봉 훼손"),
            ],
        },
    ]


def render_decision_stage_guide_panel(*, execution_window: bool) -> None:
    tone_map = {
        "BUY": "buy",
        "BUY_WATCH": "watch",
        "WATCH": "watch",
        "HOLD": "hold",
        "SELL_WATCH": "watch",
        "SELL": "sell",
    }
    section_html: list[str] = []
    for section in build_decision_stage_guide_sections():
        section_mode = bool(section.get("execution_window"))
        active = section_mode == bool(execution_window)
        status_html = "<div class='ns-stage-guide-status'>현재 적용</div>" if active else ""
        item_html = "".join(
            (
                "<div class='ns-stage-guide-item'>"
                f"<div class='ns-stage-guide-pill {tone_map.get(signal_key, 'watch')}'>{html.escape(signal_label(signal_key, execution_window=section_mode))}</div>"
                f"<div class='ns-stage-guide-copy'>{html.escape(description)}</div>"
                "</div>"
            )
            for signal_key, description in section.get("items", [])
        )
        section_html.append(
            (
                f"<div class='ns-stage-guide-section{' active' if active else ''}'>"
                "<div class='ns-stage-guide-head'>"
                f"<div class='ns-stage-guide-headline'>{html.escape(str(section.get('title') or ''))}</div>"
                f"{status_html}"
                "</div>"
                f"<div class='ns-stage-guide-caption'>{html.escape(str(section.get('caption') or ''))}</div>"
                f"<div class='ns-stage-guide-list'>{item_html}</div>"
                "</div>"
            )
        )
    st.markdown(
        (
            "<div class='ns-stage-guide-card'>"
            "<div class='ns-stage-guide-top'>"
            "<div class='ns-stage-guide-title'>단계별 기준</div>"
            "<div class='ns-stage-guide-kicker'>계약 기준</div>"
            "</div>"
            f"<div class='ns-stage-guide-stack'>{''.join(section_html)}</div>"
            "<div class='ns-stage-guide-note'>새로고침 계약: `F5` 시 관련 캐시만 다시 읽고 파일 원본 기준으로 재구성합니다.<br/>변경 후 점검 계약: `python -m py_compile streamlit_app.py`와 의사결정 상세차트 렌더 확인을 통과한 변경만 반영합니다.</div>"
            "</div>"
        ),
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


def _clean_text(value: Any) -> str:
    text = "" if _is_missing_scalar(value) else str(value)
    return " ".join(text.replace("\r", " ").replace("\n", " ").split()).strip()


def _fmt_macro_value(label: str, value: Any) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "-"
    label_text = str(label)
    if label_text in {"KOSPI", "VIX*", "미국 10년 금리", "한국 10년 금리"}:
        return f"{float(number):,.2f}"
    if label_text == "USD/KRW":
        return f"{float(number):,.0f}"
    return _format_large_number(number)


def render_panel_card(title: str, lines: list[str], *, kicker: str = "", note: str = "") -> None:
    body_html = "".join(f"<div class='ns-panel-line'>{html.escape(str(line))}</div>" for line in lines if str(line).strip())
    header_html = (
        "<div class='ns-panel-head'>"
        f"<div class='ns-panel-title'>{html.escape(title)}</div>"
        f"<div class='ns-panel-kicker'>{html.escape(kicker)}</div>"
        "</div>"
        if kicker
        else f"<div class='ns-panel-title'>{html.escape(title)}</div>"
    )
    note_html = f"<div class='ns-panel-note'>{html.escape(note)}</div>" if note else ""
    st.markdown(
        (
            "<div class='ns-panel-card'>"
            f"{header_html}"
            f"{body_html}"
            f"{note_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _format_compact_date(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    try:
        return str(pd.to_datetime(text, errors="raise").date())
    except Exception:
        try:
            dt = parsedate_to_datetime(text)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone(timedelta(hours=9)))
            return dt.date().isoformat()
        except Exception:
            return text


def _extract_news_source(description: str, fallback_title: str = "") -> str:
    desc_text = str(description or "")
    matches = re.findall(r"<font[^>]*>([^<]+)</font>", desc_text, flags=re.IGNORECASE)
    if matches:
        return _clean_text(matches[-1])
    title_text = _clean_text(fallback_title)
    if " - " in title_text:
        return _clean_text(title_text.rsplit(" - ", 1)[-1])
    return ""


def _clean_html_text(value: Any) -> str:
    text = "" if _is_missing_scalar(value) else html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text, flags=re.IGNORECASE)
    return _clean_text(text)


def _normalize_match_text(value: Any) -> str:
    text = _clean_html_text(value)
    text = re.sub(r"\s+", "", text)
    return text.lower()


def _normalize_title_key(value: Any) -> str:
    text = _clean_text(value).lower()
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w가-힣]", "", text)


def _company_alias_tokens(name: str) -> set[str]:
    base = _clean_text(name)
    if not base:
        return set()
    compact = re.sub(r"\s+", "", base).lower()
    tokens = {compact}
    for suffix in ("지주", "홀딩스", "주식회사"):
        if compact.endswith(suffix) and len(compact) > len(suffix) + 1:
            tokens.add(compact[: -len(suffix)])
    return {token for token in tokens if len(token) >= 2}


def _sort_link_rows_by_date_desc(rows: list[dict[str, str]], *, limit: int | None = None) -> list[dict[str, str]]:
    def _sort_key(row: dict[str, str]) -> tuple[pd.Timestamp, str]:
        date_text = _clean_text(row.get("date"))
        ts = pd.to_datetime(date_text, errors="coerce")
        if pd.isna(ts):
            ts = pd.Timestamp.min
        return ts, str(row.get("title") or "")

    sorted_rows = sorted(rows, key=_sort_key, reverse=True)
    if limit is not None:
        return sorted_rows[:limit]
    return sorted_rows


def _is_relevant_news_title(title: str, *, code: str, name: str) -> bool:
    norm_title = _normalize_match_text(title)
    if not norm_title:
        return False
    alias_tokens = _company_alias_tokens(name)
    if alias_tokens:
        return any(token in norm_title for token in alias_tokens)
    norm_code = str(code or "").strip().zfill(6)
    return bool(norm_code and norm_code in norm_title)


@st.cache_data(show_spinner=False)
def load_recent_news_rows(code: str, name: str, _policy_token: str, *, limit: int = 3) -> list[dict[str, str]]:
    norm_code = str(code or "").strip().zfill(6)
    norm_name = _clean_text(name)
    queries: list[str] = []
    if norm_name and norm_code:
        queries.append(f"{norm_name} {norm_code} when:14d")
    if norm_name:
        queries.append(f"{norm_name} when:14d")
    if norm_code:
        queries.append(f"{norm_code} when:14d")

    rows: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    for query_text in queries:
        try:
            response = requests.get(
                GOOGLE_NEWS_RSS_SEARCH_URL.format(query=quote(query_text)),
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except Exception:
            continue

        for item in root.findall("./channel/item"):
            raw_title = _clean_text(item.findtext("title"))
            raw_link = _clean_text(item.findtext("link"))
            raw_date = _format_compact_date(item.findtext("pubDate"))
            source = _extract_news_source(item.findtext("description", ""), fallback_title=raw_title)
            title = raw_title
            if source and raw_title.endswith(f" - {source}"):
                title = raw_title[: -(len(source) + 3)].strip()
            title = re.sub(r"\s*[\-|｜|]+\s*$", "", title).strip()
            if not _is_relevant_news_title(title, code=norm_code, name=norm_name):
                continue
            if not title or not raw_link:
                continue
            title_key = _normalize_title_key(title)
            if not title_key or title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            rows.append(
                {
                    "title": title,
                    "date": raw_date,
                    "url": raw_link,
                    "meta": source or "Google News",
                }
            )
    return _sort_link_rows_by_date_desc(rows, limit=limit)


def _resolve_dart_corp_code(code: str, fundamental_df: pd.DataFrame) -> str:
    if not fundamental_df.empty and "법인코드" in fundamental_df.columns:
        corp_series = fundamental_df["법인코드"].dropna().astype(str).str.strip()
        corp_series = corp_series[corp_series != ""]
        if not corp_series.empty:
            return corp_series.iloc[-1].zfill(8)
    corp_df = _read_csv(DART_CORP_CODES_PATH)
    if corp_df.empty or "stock_code" not in corp_df.columns or "corp_code" not in corp_df.columns:
        return ""
    corp_df["stock_code"] = corp_df["stock_code"].astype(str).str.zfill(6)
    matched = corp_df.loc[corp_df["stock_code"] == str(code or "").zfill(6), "corp_code"].dropna().astype(str).str.strip()
    if matched.empty:
        return ""
    return matched.iloc[-1].zfill(8)


def _is_periodic_financial_disclosure(title: str) -> bool:
    title_text = _clean_text(title)
    keywords = (
        "사업보고서",
        "반기보고서",
        "분기보고서",
        "감사보고서",
        "연결감사보고서",
        "감사전재무제표미제출신고",
    )
    return any(keyword in title_text for keyword in keywords)


@st.cache_data(show_spinner=False)
def load_recent_general_disclosure_rows(code: str, corp_code: str, _policy_token: str, *, limit: int = 3) -> list[dict[str, str]]:
    norm_code = str(code or "").strip().zfill(6)
    norm_corp_code = str(corp_code or "").strip().zfill(8)
    if not norm_corp_code:
        return []

    end_date = datetime.now(timezone(timedelta(hours=9))).date()
    start_date = end_date - timedelta(days=180)
    payload = {
        "currentPage": "1",
        "maxResults": str(max(limit * 6, 18)),
        "maxLinks": "10",
        "sort": "date",
        "series": "desc",
        "textCrpCik": norm_corp_code,
        "pageGubun": "corp",
        "textCrpNm": "",
        "startDate": start_date.strftime("%Y%m%d"),
        "endDate": end_date.strftime("%Y%m%d"),
        "finalReport": "recent",
    }
    try:
        response = requests.post(
            DART_COMPANY_SEARCH_URL,
            data=payload,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://dart.fss.or.kr/dsab001/main.do"},
            timeout=15,
        )
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    rows: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    for tr in soup.select("tbody#tbody tr"):
        cells = tr.find_all("td")
        report_link = tr.find("a", href=re.compile(r"/dsaf001/main\.do\?rcpNo=\d+"))
        if len(cells) < 5 or report_link is None:
            continue
        title = _clean_text(report_link.get_text(" ", strip=True))
        if not title or _is_periodic_financial_disclosure(title):
            continue
        title_key = _normalize_title_key(title)
        if not title_key or title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        href = str(report_link.get("href") or "").strip()
        url = f"https://dart.fss.or.kr{href}" if href.startswith("/") else href
        presenter = _clean_text(cells[3].get_text(" ", strip=True)) if len(cells) > 3 else ""
        badge = _clean_text(cells[5].get_text(" ", strip=True)) if len(cells) > 5 else ""
        meta_parts = [part for part in [presenter, badge] if part]
        rows.append(
            {
                "title": title,
                "date": _format_compact_date(cells[4].get_text(" ", strip=True)),
                "url": url,
                "meta": " / ".join(dict.fromkeys(meta_parts)) or f"DART {norm_code}",
            }
        )
    return _sort_link_rows_by_date_desc(rows, limit=limit)


def render_link_panel(title: str, rows: list[dict[str, str]], *, empty_text: str, note: str = "", kicker: str = "") -> None:
    if rows:
        item_html = []
        for row in rows:
            item_html.append(
                (
                    "<div class='ns-link-item'>"
                    "<div class='ns-link-head'>"
                    f"<a class='ns-link-title' href='{html.escape(str(row.get('url') or ''))}' target='_blank' rel='noopener noreferrer'>{html.escape(str(row.get('title') or '-'))}</a>"
                    f"<div class='ns-link-date'>{html.escape(str(row.get('date') or ''))}</div>"
                    "</div>"
                    f"<div class='ns-link-meta'>{html.escape(str(row.get('meta') or ''))}</div>"
                    "</div>"
                )
            )
        body_html = "<div class='ns-link-list'>" + "".join(item_html) + "</div>"
    else:
        body_html = f"<div class='ns-link-meta'>{html.escape(empty_text)}</div>"
    note_html = f"<div class='ns-link-note'>{html.escape(note)}</div>" if note else ""
    kicker_html = f"<div class='ns-link-card-kicker'>{html.escape(kicker)}</div>" if kicker else ""
    st.markdown(
        (
            "<div class='ns-link-card'>"
            "<div class='ns-link-card-head'>"
            f"<div class='ns-link-card-title'>{html.escape(title)}</div>"
            f"{kicker_html}"
            "</div>"
            f"{body_html}"
            f"{note_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def load_company_brief_snapshot(code: str, _policy_token: str) -> dict[str, str]:
    norm = str(code or "").strip().zfill(6)
    if not norm:
        return {}
    try:
        response = requests.get(
            FNGUIDE_SNAPSHOT_XML_URL.format(code=norm),
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        text = response.content.decode("cp949", errors="ignore")
        root = ET.fromstring(text)
        node = root.find(".//business_summary")
        consensus = root.find(".//consensus")
        if node is None and consensus is None:
            return {}
        summaries = [_clean_text(child.text) for child in node.findall("summary")] if node is not None else []
        summaries = [item for item in summaries if item]
        return {
            "source_date": _clean_text(node.findtext("date")) if node is not None else "",
            "tagline": _clean_text(node.findtext("title_1")) if node is not None else "",
            "headline": _clean_text(node.findtext("title")) if node is not None else "",
            "summary_main": summaries[0] if summaries else "",
            "summary_recent": summaries[1] if len(summaries) > 1 else "",
            "edit_date": _clean_text(node.findtext("edit_date")) if node is not None else "",
            "consensus_date": _clean_text(consensus.findtext("date")) if consensus is not None else "",
            "consensus_score": _clean_text(consensus.findtext("opinion")) if consensus is not None else "",
            "consensus_target_price": _clean_text(consensus.findtext("target_price")) if consensus is not None else "",
            "consensus_eps": _clean_text(consensus.findtext("eps")) if consensus is not None else "",
            "consensus_per": _clean_text(consensus.findtext("per")) if consensus is not None else "",
            "consensus_org_count": _clean_text(consensus.findtext("presume_organ_count")) if consensus is not None else "",
        }
    except Exception:
        return {}


def build_recent_disclosure_rows(fundamental_df: pd.DataFrame, *, limit: int = 3) -> list[dict[str, str]]:
    if fundamental_df.empty:
        return []
    frame = fundamental_df.copy()
    frame["공시일"] = pd.to_datetime(frame["공시일"], errors="coerce")
    frame = frame.dropna(subset=["공시일"]).sort_values("공시일", ascending=False)
    frame = frame.drop_duplicates(subset=["접수번호"], keep="first")
    rows: list[dict[str, str]] = []
    for _, row in frame.head(limit).iterrows():
        rcept_no = str(row.get("접수번호") or "").strip()
        if not rcept_no:
            continue
        op_margin_value = pd.to_numeric(pd.Series([row.get("분기영업이익률")]), errors="coerce").iloc[0]
        op_margin_text = "-" if pd.isna(op_margin_value) else f"{float(op_margin_value):.1%}"
        rows.append(
            {
                "date": str(pd.to_datetime(row["공시일"]).date()),
                "label": f"{row.get('분기', '-')} 실적 공시",
                "metric": (
                    f"매출 {_format_large_number(row.get('분기매출액'))} / "
                    f"영업이익률 {op_margin_text}"
                ),
                "url": DART_DISCLOSURE_URL.format(rcept_no=rcept_no),
            }
        )
    return _sort_link_rows_by_date_desc(rows, limit=limit)


def render_financial_panel(detail_row: pd.Series, fundamental_df: pd.DataFrame) -> None:
    st.markdown("<div class='ns-detail-block-title'>재무</div>", unsafe_allow_html=True)
    if fundamental_df.empty:
        op_margin = pd.to_numeric(pd.Series([detail_row.get("op_margin_pti")]), errors="coerce").iloc[0]
        net_margin = pd.to_numeric(pd.Series([detail_row.get("net_margin_pti")]), errors="coerce").iloc[0]
        op_qoq = pd.to_numeric(pd.Series([detail_row.get("op_income_qoq_pti")]), errors="coerce").iloc[0]
        op_ttm = pd.to_numeric(pd.Series([detail_row.get("op_income_q_ttm")]), errors="coerce").iloc[0]
        basis_quarter = str(detail_row.get("근거 기준 분기") or "-").strip()
        basis_date = str(detail_row.get("기준 공시일") or "-").strip()
        if all(pd.isna(value) for value in [op_margin, net_margin, op_qoq, op_ttm]):
            st.info("선택한 종목의 재무 데이터가 없습니다.")
            return
        lines: list[str] = []
        if basis_quarter != "-" or basis_date != "-":
            lines.append(f"{basis_quarter} · {basis_date}")
        lines.append(f"영업이익률 {'-' if pd.isna(op_margin) else f'{_safe_float(op_margin):.1%}'}")
        lines.append(f"순이익률 {'-' if pd.isna(net_margin) else f'{_safe_float(net_margin):.1%}'}")
        lines.append(f"영업이익 QoQ {'-' if pd.isna(op_qoq) else _format_large_number(op_qoq)}")
        lines.append(f"최근4Q 영업 {'-' if pd.isna(op_ttm) else _format_large_number(op_ttm)}")
        render_panel_card("재무 스냅샷", lines, kicker="feature snapshot", note="원천 분기 재무는 없어 latest feature 기준으로 표시합니다.")
        return

    latest_fund = fundamental_df.iloc[-1]
    financial_blocks = build_financial_blocks(detail_row, fundamental_df)
    block_cols = st.columns(2)
    for idx, block in enumerate(financial_blocks):
        with block_cols[idx % 2]:
            render_panel_card(
                str(block["title"]),
                [line for line in str(block["body"]).splitlines() if line.strip()],
                note=str(block.get("note") or "").strip(),
            )

    metric_cards = [
        {"title": "최근 분기 매출", "value": _format_large_number(latest_fund.get("분기매출액")), "caption": str(detail_row.get("근거 기준 분기") or "-")},
        {"title": "최근 분기 영업이익", "value": _format_large_number(latest_fund.get("분기영업이익")), "caption": str(detail_row.get("기준 공시일") or "-")},
        {"title": "최근 분기 당기순이익", "value": _format_large_number(latest_fund.get("분기당기순이익")), "caption": "원천 분기 기준"},
        {"title": "최근 분기 영업이익률", "value": "-" if pd.isna(latest_fund.get("분기영업이익률")) else f"{_safe_float(latest_fund.get('분기영업이익률')):.2%}", "caption": "원천 분기 기준"},
    ]
    metric_cols = st.columns(2)
    for idx, item in enumerate(metric_cards):
        with metric_cols[idx % 2]:
            render_panel_card(item["title"], [item["value"]], kicker=item["caption"])

    raw_fund_view = fundamental_df[["분기", "공시일", "분기매출액", "분기영업이익", "분기당기순이익", "분기영업이익률"]].tail(8).sort_values("공시일", ascending=False).copy()
    raw_fund_view["공시일"] = pd.to_datetime(raw_fund_view["공시일"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("-")
    with st.expander("원천 분기 재무", expanded=False):
        render_table(raw_fund_view, height=220)


def render_macro_panel(detail_row: pd.Series, macro_df: pd.DataFrame) -> None:
    st.markdown("<div class='ns-detail-block-title'>공통 매크로</div>", unsafe_allow_html=True)
    if macro_df.empty:
        st.info("공통 매크로 데이터가 없습니다.")
        return

    macro_snapshot = current_macro_snapshot(macro_df)
    latest_date = "-"
    if "date" in macro_df.columns and not macro_df["date"].dropna().empty:
        latest_date = str(pd.to_datetime(macro_df["date"], errors="coerce").dropna().max().date())

    top_cards = [
        {
            "title": "시장 상태",
            "lines": [
                f"{market_state_label(detail_row.get('market_regime'))} · 운용강도 {operating_intensity_label(detail_row.get('market_exposure'))}",
                f"최신일 {latest_date}",
            ],
            "kicker": "전략 공통 해석",
        }
    ]
    if not macro_snapshot.empty:
        for _, row in macro_snapshot.iterrows():
            top_cards.append(
                {
                    "title": str(row["지표"]),
                    "lines": [_fmt_macro_value(row["지표"], row["값"])],
                    "kicker": f"기준일 {row['최신일']}",
                }
            )

    macro_cols = st.columns(2)
    for idx, card in enumerate(top_cards[:6]):
        with macro_cols[idx % 2]:
            render_panel_card(card["title"], card["lines"], kicker=card["kicker"])

    recent_macro = macro_df.sort_values("date").tail(120)
    with st.expander("매크로 추이", expanded=False):
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


def render_company_brief(detail_row: pd.Series, fundamental_df: pd.DataFrame) -> None:
    st.markdown("<div class='ns-detail-block-title'>종목 브리핑</div>", unsafe_allow_html=True)
    code = _coalesce_text(detail_row.get("code"), default="").zfill(6)
    company_name = _coalesce_text(detail_row.get("name"), code, default=code)
    company_policy_label = briefing_policy_display("company_info")
    news_policy_label = briefing_policy_display("news")
    general_policy_label = briefing_policy_display("general_disclosure")
    financial_policy_label = briefing_policy_display("financial_disclosure")
    brief = load_company_brief_snapshot(code, briefing_policy_refresh_token("company_info"))
    disclosures = build_recent_disclosure_rows(fundamental_df, limit=3)
    general_disclosures = load_recent_general_disclosure_rows(
        code,
        _resolve_dart_corp_code(code, fundamental_df),
        briefing_policy_refresh_token("general_disclosure"),
        limit=3,
    )
    industry = _coalesce_text(detail_row.get("industry"), default="-")
    title = _coalesce_text(brief.get("tagline"), default=f"{industry} 업종 상장사")
    subtitle = _coalesce_text(brief.get("headline"), default=f"{company_name} 사업 개요")
    main_summary = _coalesce_text(brief.get("summary_main"), default="사업 개요 데이터가 아직 없습니다.")
    recent_summary = _coalesce_text(brief.get("summary_recent"), default="")
    source_text = _coalesce_text(brief.get("edit_date"), brief.get("source_date"), default="")
    consensus_date = _format_compact_date(brief.get("consensus_date"))
    consensus_score = _clean_text(brief.get("consensus_score"))
    consensus_target_price = _clean_text(brief.get("consensus_target_price"))
    consensus_eps = _clean_text(brief.get("consensus_eps"))
    consensus_per = _clean_text(brief.get("consensus_per"))
    consensus_org_count = _clean_text(brief.get("consensus_org_count"))

    market_cap = _format_large_number(detail_row.get("latest_market_cap"))
    close_value = pd.to_numeric(pd.Series([detail_row.get("latest_close")]), errors="coerce").iloc[0]
    close_text = "-" if pd.isna(close_value) else f"{float(close_value):,.0f}원"
    brief_meta = " / ".join([industry, f"시총 {market_cap}", f"종가 {close_text}"])
    source_chip_html = f"<div class='ns-brief-chip'>기준 {html.escape(source_text)}</div>" if source_text else ""
    update_chip_html = f"<div class='ns-brief-chip'>갱신 {html.escape(company_policy_label)}</div>"
    recent_summary_html = (
        f"<div class='ns-brief-body'>{html.escape(recent_summary)}</div>"
        if recent_summary
        else ""
    )
    consensus_lines: list[str] = []
    if consensus_score:
        consensus_lines.append(f"투자의견 {consensus_score} / 5.0")
    if consensus_target_price:
        target_price_text = consensus_target_price
        if not target_price_text.endswith("원"):
            target_price_text = f"{target_price_text}원"
        consensus_lines.append(f"목표가 {target_price_text}")
    if consensus_org_count:
        consensus_lines.append(f"기관 수 {consensus_org_count}")
    elif consensus_eps:
        consensus_lines.append(f"EPS {consensus_eps}")
    if consensus_per:
        consensus_lines.append(f"PER {consensus_per}배")

    def _rough_line_units(text: str, width: int) -> int:
        raw = str(text or "").strip()
        if not raw:
            return 0
        return max(1, (len(raw) + width - 1) // width)

    brief_units = (
        1
        + _rough_line_units(title, 24)
        + _rough_line_units(subtitle, 28)
        + _rough_line_units(main_summary, 52)
        + _rough_line_units(recent_summary, 56)
    )
    consensus_units = max(2, len(consensus_lines) + 1)
    disclosure_units = max(2, len(general_disclosures) + 1) + max(2, len(disclosures) + 1)
    news_limit = min(14, max(6, brief_units + consensus_units + disclosure_units - 6))
    news_rows = load_recent_news_rows(code, company_name, briefing_policy_refresh_token("news"), limit=news_limit)

    left, right = st.columns([1.2, 0.9])
    with left:
        st.markdown(
            (
                "<div class='ns-brief-wrap'>"
                "<div class='ns-brief-head'>"
                "<div>"
                f"<div class='ns-brief-title'>{html.escape(str(title))}</div>"
                f"<div class='ns-brief-subtitle'>{html.escape(str(subtitle))}</div>"
                "</div>"
                "<div class='ns-brief-chip-stack'>"
                f"{source_chip_html}"
                f"{update_chip_html}"
                "</div>"
                "</div>"
                f"<div class='ns-brief-body'>{html.escape(main_summary)}</div>"
                f"{recent_summary_html}"
                f"<div class='ns-brief-meta'>{html.escape(brief_meta)}</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        render_panel_card(
            "애널리스트 컨센서스",
            consensus_lines if consensus_lines else ["집계된 투자의견이 없습니다."],
            kicker=f"갱신 {company_policy_label}",
            note=(
                f"기준 {consensus_date} · FnGuide 컨센서스"
                if consensus_date
                else "FnGuide 컨센서스 기준 집계 없음"
            ),
        )
        render_link_panel(
            "일반 공시",
            general_disclosures,
            empty_text="표시 가능한 일반 공시가 없습니다.",
            note="DART 회사별검색 최근 180일 기준이며 정기 재무보고서는 제외합니다.",
            kicker=general_policy_label,
        )
        render_link_panel(
            "재무 공시",
            [
                {
                    "title": str(item.get("label") or "-"),
                    "date": str(item.get("date") or ""),
                    "url": str(item.get("url") or ""),
                    "meta": str(item.get("metric") or ""),
                }
                for item in disclosures
            ],
            empty_text="표시 가능한 재무 공시가 없습니다.",
            note="재무 원천 데이터의 DART 접수번호를 연결합니다.",
            kicker=financial_policy_label,
        )

    with right:
        render_link_panel(
            "최근 기사",
            news_rows,
            empty_text="표시 가능한 최근 기사가 없습니다.",
            note="Google News RSS 최근 14일 검색 결과 기준입니다. 기사 수는 왼쪽 브리핑·공시 섹션 높이에 맞춰 자동 확장합니다.",
            kicker=news_policy_label,
        )

def render_strategy_logic(cfg: dict[str, Any]) -> None:
    st.markdown(
        f"""
### 전략 로직 상세

1. **V2 기본안**
   - 현재 실행 기본형은 **월봉매수 / 주봉매도 / buy_0%__sell_-5%** 입니다.
   - 최적 MA 표시는 종목별 계약을 반영해 **매수/매도 기준이 월봉·주봉 중 다를 수 있습니다.**
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
    session_refresh_token = data.get("session_refresh_token", "")

    selected_code = str(selected_row["code"]).zfill(6)
    version_tokens = data["version_tokens"]
    price_df = load_price_history(selected_code, version_tokens["price"], session_refresh_token)
    fundamental_df = load_fundamental(selected_code, version_tokens["fundamental"], session_refresh_token)
    macro_df = load_macro(version_tokens["macro"], session_refresh_token)
    manual_position_row = manual_positions[manual_positions["code"] == selected_code].iloc[-1] if not manual_positions.empty and (manual_positions["code"] == selected_code).any() else None
    fast_position_row = fast_state[fast_state["code"] == selected_code].iloc[-1] if not fast_state.empty and (fast_state["code"] == selected_code).any() else None
    base_signal = str(selected_row.get("display_signal") or "").upper()
    preserve_base_axes = base_signal == "NO_SIGNAL"
    detail_row = refresh_row_live_v2_timing(
        selected_row.copy(),
        price_token=version_tokens["price"],
        optimal_ma_token=version_tokens["optimal_ma"],
        cfg=load_default_config(data["meta"]),
        session_refresh_token=session_refresh_token,
    )
    if preserve_base_axes:
        detail_row["display_signal"] = selected_row.get("display_signal", "NO_SIGNAL")
        detail_row["display_signal_ko"] = selected_row.get("display_signal_ko", "신호없음")
    else:
        detail_row["display_signal"] = classify_signal(detail_row, load_default_config(data["meta"]))
        detail_row["display_signal_ko"] = signal_label(detail_row.get("display_signal"), execution_window=is_execution_window())
    if decision_df is not None and not decision_df.empty:
        last = decision_df.sort_values("date").iloc[-1]
        detail_row["market_regime"] = str(last.get("market_regime", "unknown"))
        detail_row["market_exposure"] = _safe_float(last.get("exposure"), 1.0)
    if preserve_base_axes:
        for key in ["최적 MA 축", "주가 위치 축", "재무 축", "매크로 축", "실행 요약"]:
            if str(selected_row.get(key) or "").strip():
                detail_row[key] = selected_row.get(key)
        if not str(detail_row.get("실행 요약") or "").strip():
            detail_row["실행 요약"] = str(selected_row.get("active_execution_guide") or "최신 전략 신호 없음")
    else:
        detail_row["최적 MA 축"] = format_v2_ma_axis_summary(detail_row)
        detail_row["주가 위치 축"] = format_price_axis_summary(detail_row)
        detail_row["재무 축"] = format_financial_axis_summary(detail_row)
        detail_row["매크로 축"] = format_macro_axis_summary(detail_row)
        detail_row["실행 요약"] = compact_execution_guide(detail_row, execution_window=is_execution_window())

    current_price = None
    current_basis = "-"
    price_snapshot_row = latest_price[latest_price["code"] == selected_code].head(1)
    snapshot_date = pd.NaT
    if not price_snapshot_row.empty:
        snapshot_date = pd.to_datetime(
            price_snapshot_row.iloc[0].get("latest_price_date", price_snapshot_row.iloc[0].get("date")),
            errors="coerce",
        )
    live_quotes = data.get("live_quotes", pd.DataFrame())
    if isinstance(live_quotes, pd.DataFrame) and not live_quotes.empty:
        live = live_quotes.copy()
        live["code"] = live["code"].astype(str).str.zfill(6)
        live = live[live["code"] == selected_code].copy()
        if not live.empty:
            live["date"] = pd.to_datetime(live.get("date"), errors="coerce")
            live["quote_time"] = pd.to_datetime(live.get("quote_time"), errors="coerce")
            live["close"] = pd.to_numeric(live.get("close"), errors="coerce")
            live = live[live["close"] > 0].sort_values(["date", "quote_time"], kind="stable")
            if not live.empty:
                live_row = live.iloc[-1]
                live_date = pd.to_datetime(live_row.get("date"), errors="coerce")
                if pd.isna(snapshot_date) or (pd.notna(live_date) and live_date >= snapshot_date):
                    live_close = _safe_float(live_row.get("close"), float("nan"))
                    if pd.notna(live_close) and live_close > 0:
                        current_price = live_close
                        current_basis = format_intraday_basis(live_row.get("date"), live_row.get("quote_time"))
    if current_price is None and not price_snapshot_row.empty:
        current_price = _safe_float(price_snapshot_row.iloc[0].get("latest_close", price_snapshot_row.iloc[0].get("close")), float("nan"))
        current_basis = format_eod_basis(price_snapshot_row.iloc[0].get("latest_price_date", price_snapshot_row.iloc[0].get("date")))
    elif current_price is None and not price_df.empty:
        last = price_df.iloc[-1]
        current_price = _safe_float(last["close"], float("nan"))
        current_basis = format_eod_basis(last["date"])

    left, right = st.columns([1.7, 1.1])
    with left:
        control_left, control_right = st.columns([1.1, 1.9], gap="medium")
        with control_left:
            timeframe = st.radio("차트 기준", ["월봉", "주봉", "일봉"], horizontal=True, key=f"chart_timeframe_{selected_code}")
        tf_key = {"일봉": "daily", "주봉": "weekly", "월봉": "monthly"}[timeframe]
        buy_chart_row, sell_chart_row = _contract_chart_rows(detail_row)
        chart_contract_row = _primary_contract_chart_row(tf_key, buy_chart_row, sell_chart_row)
        overlay_rows = [row for row in (buy_chart_row, sell_chart_row) if row is not None]
        bars = resample_ohlcv(price_df, timeframe, chart_contract_row).tail(180 if timeframe == "일봉" else 120)
        bars, overlay_specs = attach_contract_overlays(
            bars,
            price_df,
            timeframe=tf_key,
            overlay_rows=overlay_rows,
            primary_row=chart_contract_row,
        )
        bars_view = bars.copy()
        chart_domain: tuple[pd.Timestamp, pd.Timestamp] | None = None
        if not bars.empty:
            slider_dates = pd.to_datetime(bars["date"]).dropna().sort_values().tolist()
            slider_format = "%Y-%m" if timeframe == "월봉" else "%Y-%m-%d"
            slider_streamlit_format = "YYYY-MM" if timeframe == "월봉" else "YYYY-MM-DD"
            with control_right:
                if len(slider_dates) >= 2:
                    slider_key = (
                        f"chart_range_date_v5_{selected_code}_{timeframe}_"
                        f"{pd.Timestamp(slider_dates[0]).strftime(slider_format)}_"
                        f"{pd.Timestamp(slider_dates[-1]).strftime(slider_format)}_"
                        f"{len(slider_dates)}"
                    )
                    slider_min = pd.Timestamp(slider_dates[0]).to_pydatetime()
                    slider_max = pd.Timestamp(slider_dates[-1]).to_pydatetime()
                    default_range = (slider_min, slider_max)
                    existing_range = st.session_state.get(slider_key)
                    range_is_valid = False
                    if isinstance(existing_range, (tuple, list)) and len(existing_range) == 2:
                        try:
                            left_candidate = pd.Timestamp(existing_range[0]).to_pydatetime()
                            right_candidate = pd.Timestamp(existing_range[1]).to_pydatetime()
                            range_is_valid = slider_min <= left_candidate <= right_candidate <= slider_max
                        except Exception:
                            range_is_valid = False
                    if not range_is_valid:
                        st.session_state.pop(slider_key, None)
                    slider_kwargs: dict[str, Any] = {}
                    if slider_key not in st.session_state:
                        slider_kwargs["value"] = default_range
                    selected_range = st.slider(
                        "가로축 범위",
                        min_value=slider_min,
                        max_value=slider_max,
                        format=slider_streamlit_format,
                        key=slider_key,
                        **slider_kwargs,
                    )
                    if isinstance(selected_range, (tuple, list)) and len(selected_range) == 2:
                        try:
                            selected_start = pd.Timestamp(selected_range[0]).normalize()
                            selected_end = pd.Timestamp(selected_range[1]).normalize()
                        except Exception:
                            selected_start = pd.Timestamp(slider_min).normalize()
                            selected_end = pd.Timestamp(slider_max).normalize()
                    else:
                        selected_start = pd.Timestamp(slider_min).normalize()
                        selected_end = pd.Timestamp(slider_max).normalize()
                else:
                    st.caption("가로축 범위")
                    st.write(pd.Timestamp(slider_dates[0]).strftime(slider_format))
                    selected_start = pd.Timestamp(slider_dates[0]).normalize()
                    selected_end = pd.Timestamp(slider_dates[-1]).normalize()
            bars_view = bars[
                (pd.to_datetime(bars["date"]) >= selected_start) & (pd.to_datetime(bars["date"]) <= selected_end)
            ].copy()
            if bars_view.empty:
                bars_view = bars.tail(1).copy()
            chart_domain = (pd.to_datetime(bars_view["date"]).min(), pd.to_datetime(bars_view["date"]).max())

        gap_source_row = chart_contract_row or buy_chart_row or sell_chart_row
        gap_df = build_contract_gap_series(price_df, base_timeframe=tf_key, overlay_row=gap_source_row)
        if timeframe == "월봉":
            gap_df = gap_df.tail(len(bars) if not bars.empty else 120)
        else:
            gap_df = gap_df.tail(104)
        gap_title = str(gap_source_row.get("ma_label")) + " 이격률" if gap_source_row is not None else f"{timeframe} 이격률"
        gap_color = str(gap_source_row.get("ma_color") or "#7c3aed") if gap_source_row is not None else "#7c3aed"
        gap_view = gap_df.copy()
        if not gap_df.empty and chart_domain is not None:
            gap_view = gap_df[
                (pd.to_datetime(gap_df["date"]) >= chart_domain[0]) & (pd.to_datetime(gap_df["date"]) <= chart_domain[1])
            ].copy()

        if not bars_view.empty:
            latest_gap_text = _build_contract_gap_summary(
                selected_code,
                row=detail_row,
                current_price=current_price if current_price is not None and not pd.isna(current_price) else None,
            )
            title_left, title_right = st.columns([1.5, 1.0], gap="small")
            with title_left:
                st.markdown(
                    f"##### {html.escape(str(selected_row['name']))} ({html.escape(selected_code)}) · {html.escape(timeframe)}",
                    unsafe_allow_html=True,
                )
            with title_right:
                if latest_gap_text:
                    st.markdown(
                        f"<div style='text-align:right; font-size:0.9rem; margin-top:0.35rem;'>{latest_gap_text}</div>",
                        unsafe_allow_html=True,
                    )
            chart_blocks: list[alt.Chart] = [
                candlestick_chart(
                    bars_view,
                    "",
                    x_domain=chart_domain,
                    overlay_specs=overlay_specs,
                )
            ]
            if not gap_view.empty:
                chart_blocks.append(
                    percent_line_chart(
                        gap_view,
                        "gap_pct",
                        gap_title,
                        gap_color,
                        x_domain=chart_domain,
                    )
                )
            chart_blocks.append(line_chart(bars_view, "volume", "거래량", "#7c3aed", x_domain=chart_domain))
            composed_chart = alt.vconcat(*chart_blocks).resolve_scale(color="independent")
            chart_key = (
                f"detail_chart_{selected_code}_{timeframe}_"
                f"{pd.Timestamp(selected_start).strftime('%Y%m%d')}_"
                f"{pd.Timestamp(selected_end).strftime('%Y%m%d')}"
            )
            st.altair_chart(composed_chart, use_container_width=True, key=chart_key)

    with right:
        if decision_df is not None and not decision_df.empty:
            last = decision_df.sort_values("date").iloc[-1]
            st.caption(
                f"시장 상태: {market_state_label(str(last.get('market_regime', 'unknown')))} / "
                f"운용강도 {operating_intensity_label(_safe_float(last.get('exposure'), 1.0))}"
            )
        if preserve_base_axes:
            st.caption("전종목 탐색 종목입니다. 최신 전략 신호가 없어 상세 4축은 저장된 탐색 기준으로 표시합니다.")
        if preserve_base_axes:
            price_execution_guide = str(selected_row.get("active_execution_guide") or "최신 전략 신호 없음")
        else:
            price_execution_guide = build_price_execution_guide(
                detail_row,
                current_price=current_price if current_price is not None and not pd.isna(current_price) else None,
                current_basis=current_basis,
                execution_window=is_execution_window(),
                position_row=manual_position_row if manual_position_row is not None else fast_position_row,
            )
        if current_price is not None and not pd.isna(current_price):
            price_title = "기준가"
            price_value = f"{_safe_float(current_price):,.0f}"
            price_caption = f"기준일 {html.escape(str(current_basis))}"
        else:
            price_title = "기준가"
            price_value = "-"
            price_caption = "-"

        st.markdown(
            f"""
            <div class="ns-summary-head">
              <div class="ns-summary-title">현재 신호 요약</div>
              <div class="ns-summary-meta">
                <span class="ns-summary-chip signal">{html.escape(str(detail_row["display_signal_ko"]))}</span>
                <span class="ns-summary-chip price">{html.escape(price_title)} {html.escape(price_value)}</span>
                <span class="ns-summary-note">{html.escape(price_caption)}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        level_buy_price = None
        if manual_position_row is not None:
            level_buy_price = _non_nan_float(manual_position_row.get("avg_price")) or _non_nan_float(manual_position_row.get("entry_price"))
        elif fast_position_row is not None:
            level_buy_price = _non_nan_float(fast_position_row.get("avg_price")) or _non_nan_float(fast_position_row.get("entry_price"))
        level_chart = build_price_level_rows(
            selected_code,
            current_price=current_price if current_price is not None and not pd.isna(current_price) else None,
            buy_price=level_buy_price,
            row=detail_row,
        )
        if not level_chart.empty:
            st.markdown("##### 가격 기준 맵")
            level_chart_key = (
                f"price_level_map_{selected_code}_{timeframe}_"
                f"{pd.Timestamp(selected_start).strftime('%Y%m%d')}_"
                f"{pd.Timestamp(selected_end).strftime('%Y%m%d')}"
            )
            st.altair_chart(price_level_map_chart(level_chart), use_container_width=True, key=level_chart_key)

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
                if title == "최적 MA":
                    klass = "ns-axis-line"
                    body_html = _format_ma_axis_line_html(line)
                else:
                    klass = "ns-axis-line" if idx == 0 else "ns-axis-line subtle"
                    body_html = html.escape(line)
                line_html.append(f"<div class='{klass}'>{body_html}</div>")
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

    info_left, info_right = st.columns([1.05, 0.95], gap="large")
    with info_left:
        render_financial_panel(detail_row, fundamental_df)
    with info_right:
        render_macro_panel(detail_row, macro_df)

    st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)
    render_company_brief(detail_row, fundamental_df)


def render_today_decision(
    signal_df: pd.DataFrame,
    decision_df: pd.DataFrame,
    data: dict[str, Any],
    cfg: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> None:
    st.write(decision_text(signal_df, decision_df))
    execution_window = is_execution_window()
    summary_cards = build_cards(signal_df, decision_df, data)
    top_left, top_right = st.columns([0.88, 1.42], gap="medium")
    with top_left:
        render_summary_board(summary_cards)
    with top_right:
        render_decision_stage_guide_panel(execution_window=execution_window)
    st.markdown("<div class='ns-section-divider'></div>", unsafe_allow_html=True)
    if signal_df.empty:
        st.markdown("<div class='ns-section-head'><div class='ns-section-title'>의사결정 표</div></div>", unsafe_allow_html=True)
        st.markdown("<div class='ns-section-note'>최적 MA·주가 위치·재무 기준으로 압축 정리했습니다. 매수·매도 기준은 종목별로 월봉/주봉이 다를 수 있습니다.</div>", unsafe_allow_html=True)
        st.info("최신 전략 신호가 없습니다.")
        return

    if context is None:
        signal_df, context = enrich_signal_display(signal_df, data)
        signal_df = finalize_signal_axes(signal_df, data=data, context=context, decision_df=decision_df)

    st.markdown(
        f"<div class='ns-section-head'><div class='ns-section-title'>의사결정 표</div><div class='ns-section-count'>({len(signal_df)}건)</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='ns-section-note'>최적 MA·주가 위치·재무 기준으로 압축 정리했습니다. 매수·매도 기준은 종목별로 월봉/주봉이 다를 수 있습니다.</div>",
        unsafe_allow_html=True,
    )
    view_df = signal_df[
        [
            "display_signal_ko",
            "code",
            "name",
            "industry",
            "latest_close",
            "latest_volume",
            "is_real_holding",
            "근거 기준 분기",
            "기준 공시일",
            "최적 MA 축",
            "주가 위치 축",
            "재무 축",
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
    # Keep cache benefits for interactive reruns, but force periodic refresh
    # so browser refresh reflects the latest pipeline outputs without manual clear.
    refresh_bucket = int(datetime.now(SEOUL_TZ).timestamp() // 5)
    payload = build_strategy_report_payload(
        data["version_tokens"]["output"],
        data["version_tokens"]["price"],
        data["version_tokens"]["fundamental"],
        data["version_tokens"]["optimal_ma"],
        _file_stamp(MANUAL_POSITIONS_PATH),
        is_execution_window(),
        refresh_bucket,
        data.get("session_refresh_token", ""),
    )
    cfg = payload["cfg"]
    signal_df = payload["signal_df"]
    decision_df = payload["decision_df"]
    render_page_heading(
        "의사결정",
        kicker="Today",
    )
    show_flash()
    render_today_decision(signal_df, decision_df, data, cfg, context=payload["context"])


def render_universe_analysis(data: dict[str, Any]) -> None:
    cfg = load_default_config(data["meta"])
    decision_df = select_decision_snapshot(data)
    session_refresh_token = data.get("session_refresh_token", "")
    feature_latest = load_feature_latest_snapshot(data["version_tokens"]["output"], session_refresh_token)
    latest_price = load_price_latest_snapshot(data["version_tokens"]["price"], session_refresh_token)
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

    optimal_ma_snapshot = load_optimal_ma_timeframe_snapshot(data["version_tokens"]["optimal_ma"], session_refresh_token)
    if not optimal_ma_snapshot.empty:
        optimal_ma_snapshot = optimal_ma_snapshot.copy()
        optimal_ma_snapshot["code"] = optimal_ma_snapshot["code"].astype(str).str.zfill(6)
        merge_cols = [col for col in optimal_ma_snapshot.columns if col != "code" and col not in signal_df.columns]
        if merge_cols:
            signal_df = signal_df.merge(optimal_ma_snapshot[["code"] + merge_cols], on="code", how="left")

    best_mode_contract = load_best_mode_contract_snapshot(data["version_tokens"]["optimal_ma"], session_refresh_token)
    if not best_mode_contract.empty:
        signal_df = merge_best_mode_contract(signal_df, best_mode_contract)
    signal_df = normalize_v2_mode_contract_frame(signal_df)

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
        "v2_contract_mode",
        "v2_buy_timeframe",
        "v2_sell_timeframe",
        "v2_buy_window",
        "v2_sell_window",
        "v2_month_window",
        "v2_month_period_dist",
        "v2_week_window",
        "v2_week_period_dist",
        "v2_buy_period_dist",
        "v2_sell_period_dist",
        "v2_month_buy_ready",
        "v2_month_buy_cross",
        "v2_month_sell_cross",
        "v2_month_above_maintain",
        "v2_week_sell_trigger",
        "v2_week_sell_watch",
        "v2_buy_ready",
        "v2_buy_cross",
        "v2_buy_above_maintain",
        "v2_sell_trigger",
        "v2_sell_watch",
        "op_margin_pti",
        "net_margin_pti",
        "op_income_qoq_pti",
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
    manual_positions = load_manual_positions_snapshot(data["version_tokens"]["output"], _file_stamp(MANUAL_POSITIONS_PATH))
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
    render_pool["최적 MA"] = render_pool.apply(_optimal_ma_table_text, axis=1)
    render_pool["리스크"] = render_pool["risk_flag"].map(prettify_risk_flag).fillna("위험없음") if "risk_flag" in render_pool.columns else "위험없음"

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
    render_pool, context = enrich_signal_display(render_pool, data)
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
    session_refresh_token = data.get("session_refresh_token", "")
    latest_price = load_price_latest_snapshot(data["version_tokens"]["price"], session_refresh_token)
    manual_positions = load_manual_positions_snapshot(data["version_tokens"]["output"], _file_stamp(MANUAL_POSITIONS_PATH))
    fast_positions = load_fast_position_state(data["version_tokens"]["output"])
    signal_df = merge_latest_signal_sources(data["signals"], data.get("signals_fast", pd.DataFrame()))
    cfg = load_default_config(data["meta"])

    signal_lookup = pd.DataFrame()
    if not signal_df.empty:
        relevant_codes: set[str] = set()
        if not manual_positions.empty:
            relevant_codes |= set(manual_positions["code"].astype(str).str.zfill(6))
        if not fast_positions.empty:
            relevant_codes |= set(fast_positions["code"].astype(str).str.zfill(6))
        signal_df = signal_df.copy()
        signal_df["code"] = signal_df["code"].astype(str).str.zfill(6)
        if relevant_codes:
            signal_df = signal_df[signal_df["code"].isin(relevant_codes)].copy()
        signal_df["is_real_holding"] = signal_df["code"].isin(set(manual_positions["code"].astype(str).str.zfill(6))) if not manual_positions.empty else False
        signal_df = refresh_signal_df_live_v2_timing(
            signal_df,
            price_token=data["version_tokens"]["price"],
            optimal_ma_token=data["version_tokens"]["optimal_ma"],
            cfg=cfg,
            session_refresh_token=session_refresh_token,
        )
        signal_df = merge_best_mode_contract(
            signal_df,
            load_best_mode_contract_snapshot(data["version_tokens"]["optimal_ma"], session_refresh_token),
        )
        signal_df = normalize_v2_mode_contract_frame(signal_df)
        signal_df = _apply_display_signal_fields(signal_df, cfg, execution_window=is_execution_window())
        signal_df["V2 타이밍"] = signal_df.apply(lambda row: format_v2_timing_summary(row), axis=1)
        signal_df["리스크"] = signal_df["risk_flag"].map(prettify_risk_flag).fillna("위험없음") if "risk_flag" in signal_df.columns else "위험없음"
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


def render_global_trends(data: dict[str, Any]) -> None:
    render_page_heading("글로벌 데일리 트렌드", kicker="Trend", subtitle="매일 06:00 기준 직전 24시간 키워드를 수집하고, 30일 롤링 점수로 정렬합니다.")
    snapshot = data.get("trend_snapshot", {}) if isinstance(data.get("trend_snapshot"), dict) else {}
    scores = data.get("trend_scores", pd.DataFrame()).copy()
    links = data.get("trend_links", pd.DataFrame()).copy()
    exposure = data.get("trend_holding_exposure", pd.DataFrame()).copy()
    status = data.get("trend_status", pd.DataFrame()).copy()
    classification_log = data.get("trend_classification_log", pd.DataFrame()).copy()
    taxonomy = data.get("trend_taxonomy", pd.DataFrame()).copy()
    aliases = data.get("trend_aliases", pd.DataFrame()).copy()

    if scores.empty and not snapshot:
        st.warning("트렌드 수집 결과가 없습니다. `python -m new_strategy.run_trend_pipeline --execute-once` 실행 후 확인할 수 있습니다.")
        show_last_command_output()
        return

    def _fmt_float_2_or_3(value: Any) -> str:
        number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(number):
            return "-"
        txt3 = f"{float(number):,.3f}"
        return f"{float(number):,.2f}" if txt3.endswith("0") else txt3

    keyword_label_map: dict[str, str] = {}
    if not aliases.empty and {"canonical_keyword", "alias", "lang"}.issubset(aliases.columns):
        aliases["canonical_keyword"] = aliases["canonical_keyword"].astype(str).str.strip().str.lower()
        aliases["alias"] = aliases["alias"].astype(str).str.strip()
        aliases["lang"] = aliases["lang"].astype(str).str.strip().str.lower()
        aliases["priority"] = pd.to_numeric(aliases.get("priority"), errors="coerce").fillna(999)
        ko_alias = (
            aliases[(aliases["lang"] == "ko") & (aliases["alias"] != "")]
            .sort_values(["canonical_keyword", "priority"])
            .drop_duplicates(subset=["canonical_keyword"], keep="first")
        )
        keyword_label_map = {str(r["canonical_keyword"]): str(r["alias"]) for r in ko_alias.to_dict("records")}

    def _keyword_display(keyword: Any) -> str:
        canonical = str(keyword or "").strip()
        if not canonical:
            return "-"
        ko = keyword_label_map.get(canonical.lower(), "").strip()
        if ko and ko.lower() != canonical.lower():
            return f"{canonical} ({ko})"
        return canonical

    def _keyword_list_display(text: Any, top_n: int = 3) -> str:
        values = [x.strip() for x in str(text or "").split(",") if x.strip()]
        if not values:
            return "-"
        return ", ".join(_keyword_display(v) for v in values[:top_n])

    def _shorten_text(text: Any, max_len: int = 26) -> str:
        value = str(text or "").strip()
        if len(value) <= max_len:
            return value
        return f"{value[:max_len-3]}..."

    if not scores.empty:
        scores["as_of_date_dt"] = pd.to_datetime(scores.get("as_of_date"), errors="coerce")
        scores["as_of_date"] = scores["as_of_date_dt"].dt.strftime("%Y-%m-%d")
        for col in ["trend_score", "mention_count", "source_count", "lang_count", "burst_z"]:
            if col in scores.columns:
                scores[col] = pd.to_numeric(scores[col], errors="coerce")

    as_of_date = str(snapshot.get("as_of_date") or "")
    if not as_of_date and not scores.empty:
        as_of_date = str(scores["as_of_date"].dropna().max() or "")
    latest_dt = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(latest_dt) and not scores.empty:
        latest_dt = pd.to_datetime(scores["as_of_date_dt"], errors="coerce").dropna().max()
        as_of_date = latest_dt.strftime("%Y-%m-%d") if pd.notna(latest_dt) else as_of_date

    latest_scores = (
        scores[scores["as_of_date_dt"] == latest_dt].copy()
        if (not scores.empty and pd.notna(latest_dt))
        else pd.DataFrame()
    )
    latest_scores = latest_scores.sort_values(["trend_score", "mention_count"], ascending=[False, False])
    if not latest_scores.empty:
        latest_scores["키워드"] = latest_scores["canonical_keyword"].map(_keyword_display)

    active_days = 0
    if not scores.empty:
        daily_mentions = (
            scores.groupby("as_of_date_dt", as_index=False)["mention_count"].sum().sort_values("as_of_date_dt")
        )
        active_days = int((pd.to_numeric(daily_mentions["mention_count"], errors="coerce").fillna(0) > 0).sum())

    summary = snapshot.get("summary", {}) if isinstance(snapshot.get("summary"), dict) else {}
    status_latest_row: dict[str, Any] = {}
    if not status.empty:
        try:
            _status_ord = status.copy()
            _status_ord["run_at"] = pd.to_datetime(_status_ord.get("run_at"), errors="coerce")
            _status_ord = _status_ord.sort_values("run_at", ascending=False)
            if len(_status_ord):
                status_latest_row = _status_ord.iloc[0].to_dict()
        except Exception:
            status_latest_row = status.iloc[0].to_dict()
    mentions_today = _safe_int(summary.get("mentions_today"), int(pd.to_numeric(latest_scores.get("mention_count"), errors="coerce").sum()) if not latest_scores.empty else 0)
    keywords_with_mentions = _safe_int(summary.get("keywords_with_mentions"), int((pd.to_numeric(latest_scores.get("mention_count"), errors="coerce") > 0).sum()) if not latest_scores.empty else 0)
    unique_sources = _safe_int(summary.get("unique_sources_today"), int(pd.to_numeric(latest_scores.get("source_count"), errors="coerce").sum()) if not latest_scores.empty else 0)
    independent_root_count = _safe_int(summary.get("independent_source_root_count_today"), -1)
    min_source_roots_contract = _safe_int(summary.get("min_source_roots_contract"), 2)
    target_source_roots_contract = _safe_int(summary.get("target_source_roots_contract"), 3)
    representativeness = str(summary.get("representativeness") or "").strip().lower()
    independent_roots_today = summary.get("independent_source_roots_today", [])
    if isinstance(independent_roots_today, str):
        independent_roots_today = [x.strip() for x in independent_roots_today.split(",") if x.strip()]
    elif isinstance(independent_roots_today, list):
        independent_roots_today = [str(x).strip() for x in independent_roots_today if str(x).strip()]
    else:
        independent_roots_today = []
    if independent_root_count < 0 and "source_root_count_today" in status_latest_row:
        status_root = pd.to_numeric(pd.Series([status_latest_row.get("source_root_count_today")]), errors="coerce").iloc[0]
        if pd.notna(status_root):
            independent_root_count = int(status_root)
    if not independent_roots_today and "source_roots_today" in status_latest_row:
        roots_text = str(status_latest_row.get("source_roots_today") or "").strip()
        independent_roots_today = [x.strip() for x in roots_text.split(",") if x.strip()]
    if independent_root_count < 0:
        independent_root_count = 0

    weights = snapshot.get("weights", {}) if isinstance(snapshot.get("weights"), dict) else {}
    kpi_cards = [
        ("기준일", as_of_date or "-"),
        ("뉴스 언급", f"{mentions_today:,}"),
        ("활성 키워드", f"{keywords_with_mentions:,}"),
        ("고유 소스", f"{unique_sources:,}"),
        ("독립 루트", f"{independent_root_count:,}"),
        ("30일 활성일", f"{active_days}일"),
    ]
    st.markdown(
        """
        <style>
        .st-key-trend_manual_refresh_now,
        .st-key-trend_manual_refresh_now [data-testid="stButton"] {
          margin-top: 0 !important;
          padding-top: 0 !important;
        }
        .st-key-trend_manual_refresh_now button,
        .st-key-trend_manual_refresh_now div[data-testid="stButton"] button,
        .st-key-trend_manual_refresh_now [data-baseweb="button"] {
          min-height: 66px !important;
          height: 66px !important;
          max-height: 66px !important;
          border: 1px solid #d8dee9 !important;
          border-radius: 10px !important;
          background: #f8fafc !important;
          color: #0f172a !important;
          font-size: 22px !important;
          font-weight: 700 !important;
          line-height: 1.1 !important;
          margin-top: 0 !important;
          padding: 0 12px !important;
          display: flex !important;
          align-items: center !important;
          justify-content: center !important;
        }
        .st-key-trend_manual_refresh_now button:hover,
        .st-key-trend_manual_refresh_now div[data-testid="stButton"] button:hover,
        .st-key-trend_manual_refresh_now [data-baseweb="button"]:hover {
          background: #f1f5f9 !important;
          border-color: #94a3b8 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    kpi_cols = st.columns(len(kpi_cards) + 1)
    with kpi_cols[0]:
        if st.button("지금 업데이트", key="trend_manual_refresh_now", use_container_width=True, help="클릭 시 현재 시각 기준으로 트렌드 즉시 수집"):
            clicked_at = datetime.now(SEOUL_TZ)
            try:
                with st.spinner(f"트렌드 수집 실행 중... ({clicked_at.strftime('%Y-%m-%d %H:%M:%S')})"):
                    result = run_trend_collect_now(run_at=clicked_at, timeout_seconds=900)
                output_text = "\n".join([str(result.stdout or "").strip(), str(result.stderr or "").strip()]).strip()
                st.session_state["last_command_output"] = output_text
                if int(result.returncode) == 0:
                    set_flash(f"트렌드 수동 업데이트 완료 ({clicked_at.strftime('%Y-%m-%d %H:%M:%S')})", level="success")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    set_flash("트렌드 수동 업데이트 실패: 실행 로그를 확인해 주세요.", level="error")
                    st.rerun()
            except subprocess.TimeoutExpired:
                set_flash("트렌드 수동 업데이트 시간 초과(900초). 네트워크 상태를 확인해 주세요.", level="error")
                st.rerun()
            except Exception as exc:
                set_flash(f"트렌드 수동 업데이트 실패: {type(exc).__name__}", level="error")
                st.rerun()
    for col, (label, value) in zip(kpi_cols[1:], kpi_cards):
        with col:
            st.markdown(
                (
                    "<div style='padding:8px 12px;border:1px solid #d8dee9;border-radius:10px;"
                    "background:#f8fafc;min-height:66px;'>"
                    f"<div style='font-size:12px;color:#667085;font-weight:600;'>{label}</div>"
                    f"<div style='font-size:24px;color:#0f172a;font-weight:700;line-height:1.1;margin-top:4px;'>{value}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
    if weights:
        weight_defs = [
            ("급등강도", "burst_z", "burst_score", 20),
            ("소스다양성", "source_diversity", "source_diversity_score", 20),
            ("언급량", "volume", "volume_score", 15),
            ("지속성", "persistence", "persistence_score", 15),
            ("언어합의", "cross_lang_consensus", "cross_lang_consensus_score", 15),
            ("신선도", "freshness", "freshness_score", 15),
        ]
        st.caption(
            "점수 가중치 "
            + " / ".join(
                f"{ko}({en}) {weights.get(weight_key, default):.0f}"
                for ko, en, weight_key, default in weight_defs
            )
        )
    roots_text = ", ".join(independent_roots_today) if independent_roots_today else "-"
    if independent_root_count < max(1, min_source_roots_contract):
        root_status_text = (
            f"독립루트 부족: {independent_root_count}개 "
            f"(최소 {max(1, min_source_roots_contract)} / 목표 {max(1, target_source_roots_contract)}) · {roots_text}"
        )
        root_status_color = "#8a5a00"
    else:
        tier_label = {"high": "높음", "medium": "중간", "low": "낮음"}.get(representativeness, "-")
        root_status_text = (
            f"독립루트 {independent_root_count}개 "
            f"(최소 {max(1, min_source_roots_contract)} / 목표 {max(1, target_source_roots_contract)}, {tier_label}) · {roots_text}"
        )
        root_status_color = "#334155"
    if active_days < 7:
        st.warning("현재는 누적 히스토리가 충분하지 않아 점수 추이가 급격한 형태로 보일 수 있습니다. 매일 06:00 수집이 쌓이면 안정됩니다.")
    title_col, status_col = st.columns([3.4, 2.6])
    with title_col:
        st.subheader("Top 키워드 점수 추이 (최근 30일)")
    with status_col:
        st.markdown(
            (
                "<div style='text-align:right;padding-top:12px;font-size:0.86rem;"
                f"color:{root_status_color};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
                f"{root_status_text}"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    if scores.empty or latest_scores.empty or pd.isna(latest_dt):
        st.caption("점수 추이 데이터가 없습니다.")
    else:
        label_col, control_col, summary_col = st.columns([0.95, 0.75, 4.3])
        with label_col:
            st.markdown("<div style='padding-top:8px;font-weight:600;'>추이 표시 키워드 수</div>", unsafe_allow_html=True)
        with control_col:
            top_k = st.selectbox(
                "추이 표시 키워드 수",
                [5, 8, 10, 12, 15],
                index=2,
                key="trend_topk_timeseries",
                label_visibility="collapsed",
            )
        with summary_col:
            trend_meta_placeholder = st.empty()
        window_start = (latest_dt - pd.Timedelta(days=29)).normalize()
        window_end = latest_dt.normalize()
        date_index = pd.date_range(window_start, window_end, freq="D")
        axis_values = [d.strftime("%Y-%m-%d") for d in date_index]
        window_scores = scores[(scores["as_of_date_dt"] >= window_start) & (scores["as_of_date_dt"] <= window_end)].copy()
        if "rank_in_day" in window_scores.columns:
            window_scores["rank_in_day"] = pd.to_numeric(window_scores["rank_in_day"], errors="coerce")
        else:
            window_scores["rank_in_day"] = (
                pd.to_numeric(window_scores.get("trend_score"), errors="coerce")
                .groupby(window_scores["as_of_date_dt"])
                .rank(method="dense", ascending=False)
            )
        selected_keywords = latest_scores["canonical_keyword"].astype(str).head(int(top_k)).tolist()
        if not selected_keywords:
            selected_keywords = latest_scores["canonical_keyword"].astype(str).head(int(top_k)).tolist()
        base = pd.MultiIndex.from_product(
            [selected_keywords, date_index],
            names=["canonical_keyword", "as_of_date_dt"],
        ).to_frame(index=False)

        hist = window_scores[window_scores["canonical_keyword"].astype(str).isin(selected_keywords)].copy()
        hist = hist[["canonical_keyword", "as_of_date_dt", "trend_score", "mention_count", "source_count", "rank_in_day"]].copy()
        hist["as_of_date_dt"] = pd.to_datetime(hist["as_of_date_dt"], errors="coerce").dt.normalize()
        hist["trend_score"] = pd.to_numeric(hist["trend_score"], errors="coerce")
        hist["mention_count"] = pd.to_numeric(hist["mention_count"], errors="coerce")
        hist["source_count"] = pd.to_numeric(hist["source_count"], errors="coerce")
        hist["rank_in_day"] = pd.to_numeric(hist["rank_in_day"], errors="coerce")
        hist = hist.dropna(subset=["canonical_keyword", "as_of_date_dt"]).copy()
        hist = hist[(hist["as_of_date_dt"] >= window_start) & (hist["as_of_date_dt"] <= window_end)].copy()

        trend_hist = base.merge(hist, on=["canonical_keyword", "as_of_date_dt"], how="left")
        trend_hist["trend_score"] = pd.to_numeric(trend_hist["trend_score"], errors="coerce").fillna(0.0)
        trend_hist["mention_count"] = trend_hist["mention_count"].fillna(0.0)
        trend_hist["source_count"] = trend_hist["source_count"].fillna(0.0)
        trend_hist["rank_in_day"] = pd.to_numeric(trend_hist["rank_in_day"], errors="coerce")
        trend_hist["in_top_n"] = trend_hist["rank_in_day"].le(int(top_k)).fillna(False)
        trend_hist["순위상태"] = np.where(trend_hist["in_top_n"], f"Top{int(top_k)} 내", f"Top{int(top_k)} 밖")
        trend_hist = trend_hist.sort_values(["canonical_keyword", "as_of_date_dt"]).copy()
        trend_hist["_state_block"] = trend_hist.groupby("canonical_keyword")["in_top_n"].transform(
            lambda s: s.ne(s.shift()).cumsum()
        )
        trend_hist["outside_segment"] = np.where(
            ~trend_hist["in_top_n"],
            trend_hist["canonical_keyword"].astype(str) + "_" + trend_hist["_state_block"].astype(str),
            "",
        )
        trend_hist["inside_segment"] = np.where(
            trend_hist["in_top_n"],
            trend_hist["canonical_keyword"].astype(str) + "_" + trend_hist["_state_block"].astype(str),
            "",
        )
        trend_hist["date_label"] = pd.to_datetime(trend_hist["as_of_date_dt"], errors="coerce").dt.strftime("%Y-%m-%d")
        trend_hist["키워드"] = trend_hist["canonical_keyword"].map(_keyword_display)
        trend_hist["키워드"] = trend_hist["키워드"].map(lambda x: _shorten_text(x, 32))
        legend_keyword_order: list[str] = []
        for canonical in selected_keywords:
            label = _shorten_text(_keyword_display(canonical), 32)
            if label and label not in legend_keyword_order:
                legend_keyword_order.append(label)
        axis_days = int(len(date_index))
        mention_days = int(
            trend_hist.groupby("as_of_date_dt", as_index=False)["mention_count"].sum()["mention_count"].gt(0).sum()
        )
        visible_days = int(trend_hist.groupby("as_of_date_dt")["in_top_n"].apply(lambda s: s.any()).sum())
        trend_meta_placeholder.markdown(
            (
                "<div style='padding-top:6px;color:#6b7280;font-size:0.88rem;'>"
                f"차트 구간 {window_start.date()} ~ {window_end.date()} / 표시 일수 {axis_days}일 / 언급 발생일 {mention_days}일 / Top{int(top_k)} 표시일 {visible_days}일"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        legend_select = alt.selection_point(fields=["키워드"], bind="legend", on="click", clear="dblclick")

        # Trend chart contract (docs/TREND_CHART_CONTRACT_2026-04-12.md):
        # - Two line types only: TopN solid, outside-TopN dashed.
        # - Continuous timeline: every adjacent day pair is rendered exactly once.
        seg_src = trend_hist.sort_values(["canonical_keyword", "as_of_date_dt"]).copy()
        seg_src["prev_date"] = seg_src.groupby("canonical_keyword")["as_of_date_dt"].shift(1)
        seg_src["prev_score"] = seg_src.groupby("canonical_keyword")["trend_score"].shift(1)
        segment_df = seg_src.dropna(subset=["prev_date", "prev_score"]).copy()
        segment_df["line_style"] = np.where(segment_df["in_top_n"].fillna(False), "solid", "dashed")
        segment_df["segment_id"] = segment_df["canonical_keyword"].astype(str) + "_" + segment_df.index.astype(str)

        seg_start = segment_df.copy()
        seg_start["date_value"] = seg_start["prev_date"]
        seg_start["score_value"] = seg_start["prev_score"]
        seg_start["point_order"] = 0

        seg_end = segment_df.copy()
        seg_end["date_value"] = seg_end["as_of_date_dt"]
        seg_end["score_value"] = seg_end["trend_score"]
        seg_end["point_order"] = 1

        segment_points = pd.concat([seg_start, seg_end], ignore_index=True)
        segment_points["date_label"] = pd.to_datetime(segment_points["date_value"], errors="coerce").dt.strftime("%Y-%m-%d")

        axis_def = alt.Axis(
            labelAngle=90,
            labelOverlap=False,
            labelColor="#334155",
            titleColor="#334155",
            labelFontSize=10,
        )
        color_scale = alt.Scale(
            domain=legend_keyword_order,
            range=[
                "#2563EB",
                "#DC2626",
                "#16A34A",
                "#F59E0B",
                "#7C3AED",
                "#0D9488",
                "#DB2777",
                "#EA580C",
                "#0891B2",
                "#84CC16",
                "#4F46E5",
                "#E11D48",
            ]
        )
        x_enc = alt.X("date_label:N", title="날짜", sort=axis_values, axis=axis_def)
        line_base = alt.Chart(segment_points).encode(
            x=x_enc,
            y=alt.Y("score_value:Q", title="트렌드점수", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("키워드:N", title="키워드", scale=color_scale),
            detail=alt.Detail("segment_id:N"),
            order=alt.Order("point_order:Q"),
            tooltip=[
                alt.Tooltip("date_label:N", title="날짜"),
                alt.Tooltip("키워드:N", title="키워드"),
                alt.Tooltip("score_value:Q", title="점수", format=".3f"),
                alt.Tooltip("rank_in_day:Q", title="일자순위", format=".0f"),
                alt.Tooltip("순위상태:N", title="표시구분"),
                alt.Tooltip("mention_count:Q", title="언급수", format=",.0f"),
                alt.Tooltip("source_count:Q", title="소스수", format=",.0f"),
            ],
        )

        inside_line = (
            line_base.transform_filter("datum.line_style == 'solid'")
            .mark_line()
            .encode(
                opacity=alt.condition(legend_select, alt.value(1.0), alt.value(0.06)),
                size=alt.condition(legend_select, alt.value(2.2), alt.value(0.8)),
            )
        )
        outside_line = (
            line_base.transform_filter("datum.line_style == 'dashed'")
            .mark_line(strokeDash=[6, 4])
            .encode(
                opacity=alt.condition(legend_select, alt.value(0.9), alt.value(0.05)),
                size=alt.condition(legend_select, alt.value(1.6), alt.value(0.7)),
            )
        )
        point_layer = (
            alt.Chart(trend_hist)
            .mark_point(size=16, filled=True)
            .encode(
                x=x_enc,
                y=alt.Y("trend_score:Q", title="트렌드점수", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("키워드:N", title="키워드", scale=color_scale),
                opacity=alt.condition(legend_select, alt.value(0.95), alt.value(0.05)),
                size=alt.condition(legend_select, alt.value(28), alt.value(8)),
                tooltip=[
                    alt.Tooltip("date_label:N", title="날짜"),
                    alt.Tooltip("키워드:N", title="키워드"),
                    alt.Tooltip("trend_score:Q", title="점수", format=".3f"),
                    alt.Tooltip("rank_in_day:Q", title="일자순위", format=".0f"),
                    alt.Tooltip("순위상태:N", title="표시구분"),
                ],
            )
        )
        chart = (inside_line + outside_line + point_layer).add_params(legend_select).properties(height=460)
        st.altair_chart(chart, use_container_width=True)

    st.subheader("카테고리별 상위 키워드")
    if latest_scores.empty:
        st.caption("기준일 점수 데이터가 없습니다.")
    else:
        categories = sorted([c for c in latest_scores["category_l1"].dropna().astype(str).unique().tolist() if c.strip()])
        category_col, count_col = st.columns([2, 1])
        with category_col:
            selected_category = st.selectbox("카테고리", ["전체"] + categories, index=0, key="trend_category_select")
        with count_col:
            top_n = st.selectbox("표시 건수", [10, 20, 30, 50, 100], index=0, key="trend_top_n_select")
        view = latest_scores.copy()
        if selected_category != "전체":
            view = view[view["category_l1"].astype(str) == selected_category].copy()
        available_count = int(len(view))
        if int(top_n) > available_count:
            st.caption(f"현재 조건에서 표시 가능한 키워드는 {available_count}개입니다.")

        keyword_industry_map: dict[str, str] = {}
        keyword_strength_map: dict[str, str] = {}
        keyword_confidence_map: dict[str, str] = {}
        if not links.empty and {"canonical_keyword", "industry_name"}.issubset(links.columns):
            link_view = links.copy()
            link_view["canonical_keyword"] = link_view["canonical_keyword"].astype(str).str.strip().str.lower()
            link_view["industry_name"] = link_view["industry_name"].astype(str).str.strip()
            link_view["relation_strength"] = pd.to_numeric(link_view.get("relation_strength"), errors="coerce").fillna(0.0)
            link_view["confidence"] = pd.to_numeric(link_view.get("confidence"), errors="coerce").fillna(0.0)
            link_view = link_view[(link_view["canonical_keyword"] != "") & (link_view["industry_name"] != "")]
            if not link_view.empty:
                link_view = link_view.sort_values(["canonical_keyword", "relation_strength", "confidence"], ascending=[True, False, False])
                keyword_industry_map = (
                    link_view.groupby("canonical_keyword")["industry_name"]
                    .apply(lambda s: ", ".join([str(v) for v in pd.Series(s).drop_duplicates().head(2).tolist()]) if len(s) else "-")
                    .to_dict()
                )
                best_links = link_view.drop_duplicates(subset=["canonical_keyword"], keep="first")
                keyword_strength_map = {
                    str(r["canonical_keyword"]): _fmt_float_2_or_3(r.get("relation_strength"))
                    for r in best_links.to_dict("records")
                }
                keyword_confidence_map = {
                    str(r["canonical_keyword"]): _fmt_float_2_or_3(r.get("confidence"))
                    for r in best_links.to_dict("records")
                }

        view = view.sort_values(["trend_score", "mention_count"], ascending=[False, False]).head(int(top_n)).reset_index(drop=True)
        view.insert(0, "순위", np.arange(1, len(view) + 1))
        canon_keys = view["canonical_keyword"].astype(str).str.lower()
        view["연관업종(상위2)"] = canon_keys.map(keyword_industry_map).fillna("-")
        view["연관강도"] = canon_keys.map(keyword_strength_map).fillna("-")
        view["신뢰도"] = canon_keys.map(keyword_confidence_map).fillna("-")
        view["키워드"] = view["키워드"].map(lambda x: _shorten_text(x, 34))
        view["연관업종(상위2)"] = view["연관업종(상위2)"].map(lambda x: _shorten_text(x, 28))
        view["순위"] = pd.to_numeric(view["순위"], errors="coerce").fillna(0).astype(int)
        view["언급수"] = pd.to_numeric(view["mention_count"], errors="coerce").fillna(0).astype(int)
        view["소스수"] = pd.to_numeric(view["source_count"], errors="coerce").fillna(0).astype(int)
        view["언어수"] = pd.to_numeric(view["lang_count"], errors="coerce").fillna(0).astype(int)
        view["트렌드점수"] = view["trend_score"].map(_fmt_float_2_or_3)
        render_table(
            view[
                [
                    "순위",
                    "키워드",
                    "category_l1",
                    "연관업종(상위2)",
                    "연관강도",
                    "신뢰도",
                    "트렌드점수",
                    "언급수",
                    "소스수",
                    "언어수",
                ]
            ].rename(columns={"category_l1": "대분류"})
        )

    st.subheader("신규 등록 키워드")
    promoted_view = pd.DataFrame()
    if not classification_log.empty and "action" in classification_log.columns:
        log_df = classification_log.copy()
        log_df["action"] = log_df["action"].astype(str).str.strip().str.lower()
        log_df = log_df[log_df["action"] == "auto_promoted_taxonomy"].copy()
        if not log_df.empty:
            log_df["observed_at_dt"] = pd.to_datetime(log_df.get("observed_at"), errors="coerce")
            token_series = (
                log_df["token"]
                if "token" in log_df.columns
                else pd.Series([""] * len(log_df), index=log_df.index, dtype=str)
            )
            log_df["canonical_keyword"] = token_series.astype(str).str.strip().str.lower()
            log_df["등록시각"] = log_df["observed_at_dt"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("-")
            note_series = (
                log_df["note"]
                if "note" in log_df.columns
                else pd.Series([""] * len(log_df), index=log_df.index, dtype=str)
            ).astype(str)
            log_df["언급수"] = (
                note_series.str.extract(r"count[=_](\d+)", expand=False).fillna("0").astype(int)
            )
            log_df["소스수"] = (
                note_series.str.extract(r"sources?[=_](\d+)", expand=False).fillna("0").astype(int)
            )
            log_df["추정신뢰도"] = pd.to_numeric(
                note_series.str.extract(r"confidence[=_]([0-9.]+)", expand=False),
                errors="coerce",
            )
            log_df["추정신뢰도"] = log_df["추정신뢰도"].map(_fmt_float_2_or_3).fillna("-")
            if not taxonomy.empty and "canonical_keyword" in taxonomy.columns:
                tx = taxonomy.copy()
                tx["canonical_keyword"] = tx["canonical_keyword"].astype(str).str.strip().str.lower()
                tx_cols = [c for c in ["canonical_keyword", "category_l1", "category_l2", "status"] if c in tx.columns]
                log_df = log_df.merge(tx[tx_cols], on="canonical_keyword", how="left")
            log_df["키워드"] = log_df["canonical_keyword"].map(_keyword_display)
            promoted_view = (
                log_df.sort_values("observed_at_dt", ascending=False)
                .drop_duplicates(subset=["canonical_keyword"], keep="first")
                .head(50)
                .copy()
            )
            if "category_l1" in promoted_view.columns:
                promoted_view["category_l1"] = promoted_view["category_l1"].fillna("-")
            if "category_l2" in promoted_view.columns:
                promoted_view["category_l2"] = promoted_view["category_l2"].fillna("-")
            if "status" in promoted_view.columns:
                promoted_view["status"] = promoted_view["status"].fillna("-")
            render_table(
                promoted_view[
                    [c for c in ["등록시각", "키워드", "category_l1", "category_l2", "status", "언급수", "소스수", "추정신뢰도"] if c in promoted_view.columns]
                ].rename(
                    columns={
                        "category_l1": "대분류",
                        "category_l2": "소분류",
                        "status": "상태",
                    }
                )
            )
    if promoted_view.empty:
        st.caption("아직 자동 등록된 신규 키워드가 없습니다.")

    st.subheader("보유종목 노출")
    if exposure.empty:
        st.caption("보유종목 노출 데이터가 없습니다.")
    else:
        for col in ["quantity", "exposure_score", "link_count"]:
            if col in exposure.columns:
                exposure[col] = pd.to_numeric(exposure[col], errors="coerce")
        view_exposure = exposure.sort_values("exposure_score", ascending=False).copy()
        view_exposure["수량"] = pd.to_numeric(view_exposure["quantity"], errors="coerce").fillna(0).astype(int)
        view_exposure["노출점수"] = view_exposure["exposure_score"].map(_fmt_float_2_or_3)
        view_exposure["연결수"] = pd.to_numeric(view_exposure["link_count"], errors="coerce").fillna(0).astype(int)
        view_exposure["대표키워드(상위2)"] = view_exposure["top_keywords"].map(lambda x: _shorten_text(_keyword_list_display(x, top_n=2), 34))
        render_table(
            view_exposure[
                [
                    "code",
                    "name",
                    "industry",
                    "수량",
                    "노출점수",
                    "연결수",
                    "대표키워드(상위2)",
                ]
            ].rename(columns={"code": "종목코드", "name": "종목명", "industry": "업종"})
        )

    st.subheader("수집 상태")
    if status.empty:
        st.caption("수집 상태 로그가 없습니다.")
    else:
        status_view = status.copy()
        status_view["run_at"] = pd.to_datetime(status_view.get("run_at"), errors="coerce")
        root_fields_present = (
            pd.to_numeric(status_view.get("source_root_count_today"), errors="coerce").notna()
            if "source_root_count_today" in status_view.columns
            else pd.Series([False] * len(status_view), index=status_view.index)
        )
        status_view["_root_fields"] = root_fields_present.astype(int)
        status_view = status_view.sort_values(["_root_fields", "run_at"], ascending=[False, False])
        status_view["실행시각"] = status_view["run_at"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("-")
        for col in ["mentions_new_rows", "keywords_covered_today", "source_root_count_today", "error_count", "duration_seconds", "min_source_roots_contract", "target_source_roots_contract"]:
            if col in status_view.columns:
                status_view[col] = pd.to_numeric(status_view[col], errors="coerce").fillna(0).astype(int)
        if "source_root_contract_ok" in status_view.columns:
            status_view["source_root_contract_ok"] = pd.to_numeric(status_view["source_root_contract_ok"], errors="coerce").fillna(0).astype(int)
            status_view["루트계약"] = np.where(status_view["source_root_contract_ok"].gt(0), "충족", "미충족")
        if "representativeness" in status_view.columns:
            tier_map = {"high": "높음", "medium": "중간", "low": "낮음"}
            status_view["대표성"] = status_view["representativeness"].astype(str).str.lower().map(tier_map).fillna("-")
        columns = [
            "실행시각",
            "status",
            "mentions_new_rows",
            "keywords_covered_today",
            "source_root_count_today",
            "루트계약",
            "대표성",
            "error_count",
            "duration_seconds",
        ]
        columns = [c for c in columns if c in status_view.columns]
        render_table(
            status_view[columns].rename(
                columns={
                    "status": "상태",
                    "mentions_new_rows": "신규언급수",
                    "keywords_covered_today": "활성키워드수",
                    "source_root_count_today": "독립루트수",
                    "error_count": "오류건수",
                    "duration_seconds": "수행초",
                }
            )
        )
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
        if st.button("저장값으로 일일 최신판단 재계산", use_container_width=True):
            launch_pipeline_job(cfg, "일일 최신판단 재계산", daily_latest=True, job_feedback_label="일일 최신판단 재계산")
            st.rerun()
    with col3:
        if st.button("저장값으로 전체 재계산(연구용)", use_container_width=True):
            launch_pipeline_job(cfg, "전체 재계산(연구용)", job_feedback_label="전체 재계산(연구용)")
            st.rerun()
    if st.button("저장값으로 최신화 + fast alert", use_container_width=True):
        launch_pipeline_job(
            cfg,
            "주가/매크로/금 전체 증분 최신화와 fast alert",
            refresh_data=True,
            refresh_macro=True,
            refresh_gold=True,
            prefer_kiwoom_eod=True,
            fast_alerts=True,
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
    krx_value = str(latest_dates["krx_raw_latest"])
    if str(latest_dates.get("krx_raw_stale", "unknown")) == "yes":
        krx_value = f"{krx_value}\n지연 +{latest_dates.get('krx_raw_lag_days', '-')}일"
    st.sidebar.markdown('<div class="ns-sidebar-section-title">운영 요약</div>', unsafe_allow_html=True)
    rendered_at = datetime.now(SEOUL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    summary_items = [
        ("KRX 보조", krx_value),
        ("주가 EOD", str(latest_dates["price_latest"])),
        ("판단 feature", str(latest_dates["feature_latest"])),
        ("매크로", str(latest_dates["macro_latest"])),
        ("재무", str(latest_dates["fundamental_latest"])),
    ]
    item_html = "".join(
        [
            (
                "<div class='ns-sidebar-summary-item'>"
                f"<div class='ns-sidebar-summary-label'>{html.escape(label)}</div>"
                f"<div class='ns-sidebar-summary-value'>{html.escape(str(value)).replace(chr(10), '<br/>')}</div>"
                "</div>"
            )
            for label, value in summary_items
        ]
    )
    st.sidebar.markdown(
        "\n".join(
            [
                "<div class='ns-sidebar-summary'>",
                "<div class='ns-sidebar-summary-head'>",
                "<div class='ns-sidebar-summary-title'>데이터 최신 상태</div>",
                f"<div class='ns-sidebar-summary-time'>{html.escape(rendered_at)}</div>",
                "</div>",
                f"<div class='ns-sidebar-summary-grid'>{item_html}</div>",
                "<div class='ns-sidebar-summary-note'>KRX 보조는 07:00 전영업일 기준입니다.</div>",
                "</div>",
            ]
        ),
        unsafe_allow_html=True,
    )
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
    if st.sidebar.button("전체 증분 최신화 + 일일 최신판단", use_container_width=True, key="sidebar_refresh_daily_latest"):
        launch_pipeline_job(
            cfg,
            "주가/매크로/금 전체 증분 최신화와 일일 최신판단",
            refresh_data=True,
            refresh_macro=True,
            refresh_gold=True,
            prefer_kiwoom_eod=True,
            daily_latest=True,
            job_feedback_label="일일최신판단",
        )
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Strategy V2 Dashboard", layout="wide")
    inject_base_css()
    session_refresh_token = apply_f5_full_refresh_contract()
    version_tokens = build_version_tokens()
    data = load_output_data(version_tokens["output"], session_refresh_token)
    data["version_tokens"] = version_tokens
    data["session_refresh_token"] = session_refresh_token
    with st.sidebar:
        render_live_clock("sidebar_live_clock", compact=True)
    st.sidebar.markdown('<div class="ns-sidebar-title">V2 전략보드</div>', unsafe_allow_html=True)
    page = st.sidebar.radio(
        "화면 선택",
        ["의사결정", "전종목 분석", "보유/검증", "글로벌 트렌드", "전략보드"],
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
    elif page == "글로벌 트렌드":
        render_global_trends(data)
    else:
        render_operations_page(data)
    render_footer(data)


if __name__ == "__main__":
    main()


