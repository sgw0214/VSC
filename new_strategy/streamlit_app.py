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
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

APP_FILE = Path(__file__).resolve()
PROJECT_ROOT = APP_FILE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from new_strategy.earnings_signal_engine import EarningsStrategyConfig
from new_strategy.optimal_ma_overlay import (
    MA_RAW_PATH as OPTIMAL_MA_RAW_PATH,
    OVERLAY_SNAPSHOT_PATH as OPTIMAL_MA_SNAPSHOT_PATH,
    load_latest_optimal_ma_snapshot as _load_latest_optimal_ma_snapshot,
    optimal_ma_alignment,
    optimal_ma_soft_delta,
)
from new_strategy.paths import data_path, output_path

APP_DIR = output_path("strategy_v1")
UI_CONFIG_PATH = APP_DIR / "strategy_dashboard_config.json"
REFRESH_META_PATH = APP_DIR / "refresh_runtime_metadata.json"
FAST_ALERT_META_PATH = APP_DIR / "fast_alert_metadata.json"
PIPELINE_PROGRESS_PATH = APP_DIR / "dashboard_pipeline_progress.json"
PIPELINE_STDOUT_PATH = APP_DIR / "dashboard_pipeline_stdout.log"
PIPELINE_STDERR_PATH = APP_DIR / "dashboard_pipeline_stderr.log"

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
TAILSCALE_EXE_PATH = Path(r"C:\Program Files\Tailscale\tailscale.exe")
TRADE_LOG_PATH = APP_DIR / "trade_log.csv"
BRIDGE_DIR = APP_DIR / "telegram_bridge"
MANUAL_TRADES_PATH = BRIDGE_DIR / "manual_portfolio_trades.csv"
MANUAL_POSITIONS_PATH = BRIDGE_DIR / "manual_portfolio_positions.csv"

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
    "BUY_WATCH": "매수관심",
    "HOLD": "보유유지",
    "SELL_WATCH": "매도경고",
    "SELL": "매도",
}
SIGNAL_LABELS_POSTCLOSE = {
    "BUY": "익일매수후보",
    "BUY_WATCH": "익일매수관심",
    "HOLD": "익일보유관찰",
    "SELL_WATCH": "익일매도경고",
    "SELL": "익일매도후보",
}
SHORT_SIGNAL_LABELS_INTRADAY = {
    "BUY": "매수",
    "BUY_WATCH": "매수관심",
    "HOLD": "보유",
    "SELL_WATCH": "매도경고",
    "SELL": "매도",
}
SHORT_SIGNAL_LABELS_POSTCLOSE = {
    "BUY": "익일매수",
    "BUY_WATCH": "익일관심",
    "HOLD": "익일보유",
    "SELL_WATCH": "익일매도경고",
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
        "timing_break": "타이밍 훼손",
        "quality_drop": "품질 저하",
        "stop_loss": "손절 기준",
    }
    if not raw:
        return "-"
    return mapping.get(raw, raw.replace("_", " "))


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
            "BUY": "추격보다 가격 안정 구간에서 분할 진입합니다.",
            "BUY_WATCH": "강도와 거래대금 확인 후 장중 매수 승격 여부를 점검합니다.",
            "HOLD": "보유 유지. 손절선 또는 중기 추세 훼손 시 매도 전환을 우선 검토합니다.",
            "SELL_WATCH": "손절선 근접 또는 약세 지속 여부를 장중 재점검합니다.",
            "SELL": "실행 가능한 매도 신호입니다. 반등 대기보다 즉시 청산을 우선합니다.",
        }
    else:
        guide_map = {
            "BUY": "익일 시초 5~15분 대기 후 가격 안정 또는 첫 눌림 확인 뒤 분할 진입합니다.",
            "BUY_WATCH": "익일 시초 강도와 거래대금 확인 후 매수 후보 유지 여부를 재평가합니다.",
            "HOLD": "익일 시초 약세가 크지 않으면 보유 유지, 손절선 하향 이탈 시 매도를 우선합니다.",
            "SELL_WATCH": "익일 시초 5~15분 내 약세 지속 시 축소 또는 청산을 우선합니다.",
            "SELL": "익일 장 초반 유동성 구간에서 우선 정리하고 손절 훼손이 크면 지체 없이 청산합니다.",
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
    if position_row is not None and not position_row.empty and pd.notna(position_row.get("entry_price")):
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
            parts.append(f"시뮬레이션 진입가 {entry_price:,.0f}원")
        if levels["initial_stop"] is not None:
            parts.append(f"초기 손절가 {levels['initial_stop']:,.0f}원")
        if levels["breakeven_guard"] is not None:
            parts.append(f"원금 보호선 {levels['breakeven_guard']:,.0f}원")
        if levels["month_10_ma"] is not None:
            parts.append(f"월봉10 참고선 {levels['month_10_ma']:,.0f}원")
        if levels["effective_guard"] is not None:
            parts.append(f"현재 유효 방어선 {levels['effective_guard']:,.0f}원")
        parts.append("가격 방어는 초기 손절 → 원금 보호 순으로 관리하고, 월봉·주봉 정보는 보조 참고 지표로만 확인합니다.")

    return " / ".join(parts)



def run_text_command(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=10)
        return (completed.stdout or completed.stderr or "").strip()
    except Exception:
        return ""


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
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
[data-testid="stSidebar"] [data-testid="stMetric"] {
    min-height: 108px;
    padding: 10px 12px;
}
[data-testid="stMetric"] {
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 12px 16px;
    min-height: 132px;
}
[data-testid="stMetricLabel"] {font-size: 1rem !important;}
[data-testid="stMetricValue"] {
    font-size: 1.55rem !important;
    line-height: 1.25 !important;
    white-space: normal !important;
    word-break: keep-all !important;
}
.ns-card {
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 14px 16px;
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    min-height: 138px;
}
.ns-card-label {
    font-size: 0.92rem;
    color: #475569;
    margin-bottom: 8px;
    font-weight: 600;
}
.ns-card-value {
    font-size: 1.08rem;
    line-height: 1.42;
    font-weight: 700;
    color: #111827;
    white-space: normal;
    word-break: keep-all;
    overflow-wrap: anywhere;
}
.ns-card-caption {
    font-size: 0.82rem;
    line-height: 1.45;
    color: #475569;
    margin-top: 10px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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
</style>
        """,
        unsafe_allow_html=True,
    )


def render_live_clock(key: str, *, compact: bool = False) -> None:
    height = 66 if compact else 78
    padding = "8px 12px" if compact else "12px 16px"
    font_size = "0.95rem" if compact else "1.05rem"
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


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _file_mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


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
            _file_mtime(STRATEGY_META_PATH),
            _file_mtime(REFRESH_META_PATH),
            _file_mtime(FAST_ALERT_META_PATH),
            _file_mtime(SCHEDULE_STATE_PATH),
            _file_mtime(LIVE_QUOTES_PATH),
        ),
        "macro": _file_mtime(MACRO_DAILY_PATH),
        "fundamental": _file_mtime(FUNDAMENTAL_PATH),
        "price": _file_mtime(PRICE_PANEL_PATH),
        "optimal_ma": (
            _file_mtime(PRICE_PANEL_PATH),
            _file_mtime(OPTIMAL_MA_RAW_PATH),
            _file_mtime(OPTIMAL_MA_SNAPSHOT_PATH),
        ),
    }


@st.cache_data(show_spinner=False)
def load_latest_data_dates(_macro_token: Any, _fundamental_token: Any) -> dict[str, str]:
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
    alignment = str(row.get("optimal_ma_alignment") or "데이터 없음")
    line_price = _format_large_number(row.get("optimal_ma_line_price"))
    if timeframe == "-" or window <= 0:
        return "데이터 없음"
    return f"{timeframe}{window}<br>{alignment}<br>{line_price}원"


def _optimal_ma_detail_text(row: pd.Series) -> str:
    timeframe = str(row.get("optimal_ma_timeframe_ko") or "-")
    action_mode = str(row.get("optimal_ma_action_mode_ko") or "-")
    window = _safe_int(row.get("optimal_ma_window"), 0)
    alignment = str(row.get("optimal_ma_alignment") or "데이터 없음")
    delta = _optimal_ma_delta_text(_safe_float(row.get("optimal_ma_soft_delta"), 0.0))
    line_price = _format_large_number(row.get("optimal_ma_line_price"))
    basis_label = str(row.get("optimal_ma_basis_label") or "-")
    basis_price = _format_large_number(row.get("optimal_ma_basis_price"))
    rule_text = str(row.get("optimal_ma_rule_text") or "데이터 없음")
    if timeframe == "-" or window <= 0:
        return "최적 MA 데이터 없음"
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


@st.cache_data(show_spinner=False)
def load_output_data(_version_token: Any) -> dict[str, Any]:
    signal_fast = _read_csv(SIGNAL_FAST_LATEST_PATH)
    signal_full = _read_csv(SIGNAL_LATEST_PATH)
    decision_fast = _read_csv(DECISION_FAST_LATEST_PATH)
    decision_full = _read_csv(DECISION_DAILY_PATH)
    return {
        "signals": signal_fast if not signal_fast.empty else signal_full,
        "decision": decision_fast if not decision_fast.empty else decision_full.tail(1),
        "health": _read_csv(HEALTH_PATH),
        "eval": _read_csv(EVAL_PATH),
        "research": _read_csv(RESEARCH_PATH),
        "research_industry": _read_csv(RESEARCH_INDUSTRY_PATH),
        "rule_top": _read_csv(RULE_TOP_PATH),
        "rule_industry": _read_csv(RULE_INDUSTRY_PATH),
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
    if not PRICE_PANEL_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(PRICE_PANEL_PATH, usecols=["date", "code", "name", "close", "industry"], dtype={"code": str}, low_memory=False)
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["code", "date"])
    return df.groupby("code", as_index=False).tail(1).copy()


@st.cache_data(show_spinner=False)
def load_optimal_ma_latest_snapshot(_optimal_ma_token: Any) -> pd.DataFrame:
    df = _load_latest_optimal_ma_snapshot()
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.zfill(6)
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
    bridge_on = bool(run_text_command(["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*new_strategy.telegram_bridge_service*' } | Select-Object -First 1 ProcessId"]))
    schedule_on = bool(run_text_command(["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*new_strategy.run_market_schedule_service*' } | Select-Object -First 1 ProcessId"]))
    live_applied = "예" if data["fast_meta"].get("live_quotes_applied") else "아니오"
    return [
        f"- 스트림릿: ON",
        f"- 텔레그램 브리지: {'ON' if bridge_on else 'OFF'}",
        f"- 시장 스케줄: {'ON' if schedule_on else 'OFF'}",
        f"- 실시간 현재가 반영: {live_applied}",
    ]


def build_compact_price_guide(
    row: pd.Series,
    *,
    live_quotes: pd.DataFrame,
    latest_price: pd.DataFrame,
    fast_state: pd.DataFrame,
    execution_window: bool,
) -> tuple[str, str]:
    code = str(row.get("code", "")).zfill(6)
    current_price = None
    basis = "-"
    if execution_window and not live_quotes.empty:
        q = live_quotes[live_quotes["code"].astype(str).str.zfill(6) == code]
        if not q.empty:
            qrow = q.sort_values(["date", "quote_time"]).iloc[-1]
            current_price = _safe_float(qrow.get("close"), float("nan"))
            basis = str(qrow.get("quote_time") or qrow.get("date") or "-")
    if current_price is None or pd.isna(current_price):
        q = latest_price[latest_price["code"].astype(str).str.zfill(6) == code]
        if not q.empty:
            qrow = q.iloc[-1]
            current_price = _safe_float(qrow.get("close"), float("nan"))
            basis = format_eod_basis(qrow.get("date"))
    if current_price is None or pd.isna(current_price):
        return "-", "-"

    basis_text = f"{current_price:,.0f}원"
    signal = str(row.get("display_signal") or row.get("signal") or "").upper()
    pos = fast_state[fast_state["code"].astype(str).str.zfill(6) == code] if not fast_state.empty else pd.DataFrame()
    entry_price = None
    if not pos.empty and pd.notna(pos.iloc[-1].get("entry_price")):
        entry_price = float(pos.iloc[-1]["entry_price"])
    levels = compute_risk_levels(row, current_price=float(current_price), entry_price=entry_price)

    if signal in {"BUY", "BUY_WATCH"}:
        parts = [
            f"관찰 {current_price * 0.99:,.0f}~{current_price * 1.01:,.0f}원",
            f"추격금지 {current_price * 1.02:,.0f}원",
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
    if levels["month_10_ma"] is not None:
        parts.append(f"월봉10참고 {levels['month_10_ma']:,.0f}원")
    if not parts:
        parts.append("고정 가격 규칙 없음")
    return basis_text, " / ".join(parts)


def decision_price_header(view_df: pd.DataFrame) -> str:
    if view_df.empty or "가격 기준" not in view_df.columns:
        return "가격 기준"
    values = view_df["가격 기준"].astype(str).tolist()
    if not values:
        return "가격 기준"
    if all("(" not in value and ")" not in value for value in values):
        if "기준 공시일" in view_df.columns:
            pass
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
        return "가격 기준"
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
            "padding:0.55rem 0.45rem;border-radius:10px;text-align:center;"
            "line-height:1.25;border:1px solid #e5e7eb;'>"
            f"{html.escape(str(label))}</div>"
        )

    price_header = decision_price_header(view_df)
    widths = [0.88, 1.18, 1.02, 0.92, 1.15, 0.95, 1.18, 1.48, 1.28, 0.82]
    headers = ["의사결정", "종목", "업종/점수", "근거 기준", "최적 MA", price_header, "가격 규칙", "실행 가이드", "핵심 근거", "리스크"]
    header_cols = st.columns(widths, gap="small")
    for col, header in zip(header_cols, headers):
        with col:
            st.markdown(f"**{header}**")
    st.markdown(
        """
        <style>
        div[data-testid="stMarkdownContainer"] p.ns-cell {
          margin: 0;
          line-height: 1.45;
          font-size: 0.88rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    for _, row in view_df.iterrows():
        st.markdown("<div style='height:0.25rem;'></div>", unsafe_allow_html=True)
        cols = st.columns(widths, gap="small")
        with cols[0]:
            st.markdown(badge_html(str(row["의사결정"])), unsafe_allow_html=True)
        with cols[1]:
            st.markdown(
                f"<p class='ns-cell'><strong>{html.escape(str(row['종목코드']))}</strong><br>{html.escape(str(row['종목명']))}</p>",
                unsafe_allow_html=True,
            )
        with cols[2]:
            st.markdown(
                (
                    f"<p class='ns-cell'>{html.escape(str(row['업종']))}<br>"
                    f"점수 {_safe_float(row['확신점수']):.3f}"
                    f"<br>표시 {_safe_float(row['표시점수']):.3f}"
                    f"<br>최적MA {_optimal_ma_delta_text(_safe_float(row['최적MA 가점'], 0.0))}</p>"
                ),
                unsafe_allow_html=True,
            )
        with cols[3]:
            st.markdown(
                f"<p class='ns-cell'>{html.escape(str(row['근거 기준 분기']))}<br>{html.escape(str(row['기준 공시일']))}</p>",
                unsafe_allow_html=True,
            )
        with cols[4]:
            st.markdown(
                f"<p class='ns-cell'>{row['최적 MA']}</p>",
                unsafe_allow_html=True,
            )
        with cols[5]:
            st.markdown(
                f"<p class='ns-cell'>{html.escape(plain_text(str(row['가격 기준']).split('(', 1)[0].strip()))}</p>",
                unsafe_allow_html=True,
            )
        with cols[6]:
            st.markdown(
                f"<p class='ns-cell'>{plain_text(row['가격 규칙'], slash_to_break=True).replace(chr(10), '<br>')}</p>",
                unsafe_allow_html=True,
            )
        with cols[7]:
            st.markdown(
                f"<p class='ns-cell'>{plain_text(row['실행 가이드']).replace(chr(10), '<br>')}</p>",
                unsafe_allow_html=True,
            )
        with cols[8]:
            st.markdown(
                f"<p class='ns-cell'>{html.escape(str(row['근거 1']))}<br>{html.escape(str(row['근거 2']))}<br>{html.escape(str(row['근거 3']))}</p>",
                unsafe_allow_html=True,
            )
        with cols[9]:
            st.markdown(
                f"<p class='ns-cell'>{html.escape(prettify_risk_flag(row['리스크']))}</p>",
                unsafe_allow_html=True,
            )
        st.markdown("---")


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
def load_manual_trade_audit(_price_token: Any, _manual_token: Any, chat_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
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


def build_pipeline_cmd(cfg: dict[str, Any], *, send_alerts: bool = False, refresh_data: bool = False, refresh_macro: bool = False, refresh_gold: bool = False, fast_alerts: bool = False) -> list[str]:
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
    if fast_alerts:
        cmd.append("--fast-alerts")
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


def launch_pipeline_job(cfg: dict[str, Any], description: str, **kwargs: Any) -> bool:
    progress = read_pipeline_progress()
    if progress and str(progress.get("status")) == "running" and is_pid_running(_safe_int(progress.get("pid"), 0)):
        set_flash("이미 실행 중인 작업이 있습니다. 진행률을 먼저 확인하세요.", level="warning")
        return False
    cmd = build_pipeline_cmd(cfg, **kwargs)
    cmd.extend(["--progress-file", str(PIPELINE_PROGRESS_PATH)])
    PIPELINE_PROGRESS_PATH.write_text(
        json.dumps(
            {
                "pid": 0,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": "",
                "status": "starting",
                "percent": 0,
                "stage": "대기",
                "detail": description,
                "duration_seconds": 0,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    PIPELINE_STDOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PIPELINE_STDOUT_PATH.open("w", encoding="utf-8") as stdout_handle, PIPELINE_STDERR_PATH.open("w", encoding="utf-8") as stderr_handle:
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
    score = _safe_float(row.get("conviction_score"))
    risk_flag = "" if pd.isna(row.get("risk_flag")) else str(row.get("risk_flag")).strip()
    if signal == "BUY":
        return "BUY"
    if signal == "SELL":
        return "SELL"
    if signal == "WATCH":
        return "BUY_WATCH"
    if signal == "HOLD" and (risk_flag or score <= max(_safe_float(cfg.get("sell_threshold")), 0.35) + 0.12):
        return "SELL_WATCH"
    return "HOLD"


def prepare_signal_display(signal_df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    if signal_df.empty:
        return signal_df
    execution_window = is_execution_window()
    df = signal_df.copy()
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["display_signal"] = df.apply(lambda row: classify_signal(row, cfg), axis=1)
    df["display_signal_ko"] = df["display_signal"].map(lambda x: signal_label(x, execution_window=execution_window))
    df["active_execution_guide"] = df.apply(lambda row: resolve_action_guide(row, execution_window=execution_window), axis=1)
    df["signal_rank"] = df["display_signal"].map(SIGNAL_ORDER).fillna(99)
    return df.sort_values(["signal_rank", "conviction_score", "code"], ascending=[True, False, True]).reset_index(drop=True)


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


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if df.empty:
        return df
    frame = df.set_index("date").sort_index()
    if timeframe == "일봉":
        out = frame.reset_index()
        window = 20
        label = "일봉 20이평"
        color = "#f59e0b"
    elif timeframe == "주봉":
        out = (
            frame.resample("W-FRI")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "trading_value": "sum"})
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        window = 10
        label = "주봉 10이평"
        color = "#16a34a"
    else:
        grouped = frame.groupby(frame.index.to_period("M"))
        out = (
            grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "trading_value": "sum"})
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        out["date"] = out["date"].dt.to_timestamp(how="end").dt.normalize()
        window = 10
        label = "월봉 10이평"
        color = "#7c3aed"
    out["date"] = pd.to_datetime(out["date"])
    out["ma_overlay"] = out["close"].rolling(window, min_periods=max(5, int(window * 0.6))).mean()
    out["ma_label"] = label
    out["ma_color"] = color
    return out


def candlestick_chart(df: pd.DataFrame, title: str) -> alt.Chart:
    if df.empty:
        return alt.Chart(pd.DataFrame({"date": [], "close": []})).mark_line()
    chart_df = df.copy()
    chart_df["상승"] = chart_df["close"] >= chart_df["open"]
    base = alt.Chart(chart_df).encode(
        x=alt.X("date:T", title="날짜"),
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
    close_line = alt.Chart(chart_df).mark_line(color="#111827", opacity=0.25).encode(x="date:T", y="close:Q")
    layers = wick + body + close_line
    if "ma_overlay" in chart_df.columns and not chart_df["ma_overlay"].dropna().empty:
        ma_color = chart_df["ma_color"].dropna().iloc[0] if "ma_color" in chart_df.columns and not chart_df["ma_color"].dropna().empty else "#f59e0b"
        ma_label = chart_df["ma_label"].dropna().iloc[0] if "ma_label" in chart_df.columns and not chart_df["ma_label"].dropna().empty else "이평선"
        ma_line = alt.Chart(chart_df).mark_line(color=ma_color, strokeWidth=2.0).encode(
            x="date:T",
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


def line_chart(df: pd.DataFrame, column: str, title: str, color: str) -> alt.Chart:
    chart_df = df[["date", column]].dropna().rename(columns={column: "value"})
    return alt.Chart(chart_df).mark_line(color=color).encode(
        x=alt.X("date:T", title="날짜"),
        y=alt.Y("value:Q", title=title),
        tooltip=[alt.Tooltip("date:T", title="날짜"), alt.Tooltip("value:Q", title=title, format=",.2f")],
    ).properties(height=180)


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
        if not pd.api.types.is_numeric_dtype(out[col]):
            continue
        label = str(col)
        if any(token in label for token in ["수익률", "승률", "비중", "비율", "변동률"]):
            out[col] = out[col].map(lambda x: "-" if pd.isna(x) else f"{float(x) * 100:.2f}%")
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
    if not output and PIPELINE_STDERR_PATH.exists():
        stderr = PIPELINE_STDERR_PATH.read_text(encoding="utf-8", errors="replace").strip()
        stdout = PIPELINE_STDOUT_PATH.read_text(encoding="utf-8", errors="replace").strip() if PIPELINE_STDOUT_PATH.exists() else ""
        output = (stdout + "\n" + stderr).strip()
    if output:
        with st.expander("최근 실행 로그", expanded=False):
            st.code(output)


def render_pipeline_progress() -> None:
    progress = read_pipeline_progress()
    if not progress:
        return
    status = str(progress.get("status", ""))
    percent = max(0, min(100, _safe_int(progress.get("percent"), 0)))
    stage = str(progress.get("stage", "-"))
    detail = str(progress.get("detail", ""))
    updated_at = str(progress.get("updated_at", "-"))
    duration_seconds = _safe_int(progress.get("duration_seconds"), 0)
    duration_text = f"{duration_seconds // 60}분 {duration_seconds % 60}초" if duration_seconds > 0 else ""
    if status in {"starting", "running"}:
        st.sidebar.markdown("##### 실행 상태")
        st.sidebar.progress(percent / 100.0, text=f"{percent}%")
        st.sidebar.caption(f"{stage}")
        if detail:
            st.sidebar.caption(detail)
        if duration_text:
            st.sidebar.caption(f"경과: {duration_text}")
        st.sidebar.caption(f"업데이트: {updated_at}")
        components.html(
            """
            <script>
            setTimeout(function() {
              window.parent.location.reload();
            }, 5000);
            </script>
            """,
            height=0,
        )
    elif status == "failed":
        st.sidebar.markdown("##### 실행 상태")
        st.sidebar.error(f"{stage} ({percent}%)")
        if detail:
            st.sidebar.caption(detail)
        if duration_text:
            st.sidebar.caption(f"경과: {duration_text}")
        st.sidebar.caption(f"업데이트: {updated_at}")


def build_inventory(data: dict[str, Any]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    latest_dates = load_latest_data_dates(data["version_tokens"]["macro"], data["version_tokens"]["fundamental"])
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
                "데이터셋": "실시간 현재가",
                "행 수": len(live_quotes),
                "시작일": str(live_quotes["date"].min().date()),
                "최신일": str(live_quotes["date"].max().date()),
                "종목 수": live_quotes["code"].astype(str).str.zfill(6).nunique(),
                "설명": "키움 현재가 오버레이. 장중 fast alert용",
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
    counts = signal_df["display_signal"].value_counts().to_dict() if not signal_df.empty else {}
    refresh_meta = data["refresh_meta"]
    latest_refresh = refresh_meta.get("price_date_max") or refresh_meta.get("latest_price_date") or latest_date
    return [
        {
            "label": "분석일자 / 실행일자",
            "value": f"분석 {latest_date} / 실행 {execution_date}",
            "caption": f"주가 기준 {latest_refresh}",
        },
        {
            "label": "시장 상태",
            "value": regime,
            "caption": f"노출 {exposure:.2f} · 목표 {target_positions}개",
        },
        {
            "label": "현재 의사결정",
            "value": (
                f"{short_signal_label('BUY', execution_window=execution_window)} {counts.get('BUY', 0)}"
                f" / {short_signal_label('HOLD', execution_window=execution_window)} {counts.get('HOLD', 0)}"
            ),
            "caption": (
                f"{short_signal_label('BUY_WATCH', execution_window=execution_window)} {counts.get('BUY_WATCH', 0)} · "
                f"{short_signal_label('SELL_WATCH', execution_window=execution_window)} {counts.get('SELL_WATCH', 0)} · "
                f"{short_signal_label('SELL', execution_window=execution_window)} {counts.get('SELL', 0)}"
            ),
        },
    ]


def render_cards(cards: list[dict[str, str]]) -> None:
    ratios = [1.35, 0.95, 1.15] if len(cards) == 3 else [1.0] * len(cards)
    cols = st.columns(ratios)
    for col, card in zip(cols, cards):
        with col:
            label = html.escape(str(card["label"]))
            value = html.escape(str(card["value"])).replace("\n", "<br>")
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
        ("1. 원천 데이터", ["KRX 일별 주가", "키움 실시간 현재가", "DART 재무 공시", "매크로·금 데이터"]),
        ("2. 정제 레이어", ["price_panel.csv", "macro_daily.csv", "fundamental_quarterly_multi.csv", "장 종료 후 종가 기준 재정리"]),
        ("3. 전략 엔진", ["실적 중심 코어 엔진", "타이밍 보정", "리스크 게이트", "fast alert / full backtest"]),
        ("4. 전달 채널", ["Streamlit 대시보드", "텔레그램 브리지", "장중 30분 점검", "장마감 후 종가 업데이트"]),
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
    execution_window = is_execution_window()
    st.markdown(
        f"""
### 전략 로직 상세

1. **코어 엔진**
   - 최근 **{cfg['recent_filing_days']}일** 내 공시된 PTI* 재무를 사용합니다.
   - 영업이익, 순이익, 영업이익률, 순이익률, QoQ* 변화, 최근 4개 분기 누적 실적을 함께 평가합니다.
    - 비정상 가능성이 큰 분기는 예외 필터로 제외합니다.

2. **타이밍 보정**
   - 기존 전략의 중기 이평, 단기 과열, 변동성 조건을 기본 타이밍 필터로 사용합니다.
   - 월봉 **10이평**, 주봉 **10이평**, 일봉 **20이평**은 차트와 보조 검토 지표로 표시합니다.
   - 최적 MA(월/주)는 신호를 바로 뒤집지 않고, 일치 시 가점·불일치 시 경고로만 반영합니다.
   - 5일 수익률 상한: **{cfg['max_ret_5']:.2f}**
   - ATR* 비율 상한: **{cfg['max_atr_ratio']:.2f}**
   - 중기 이평 이격 상한: **{cfg['max_dist_ma_mid']:.2f}**
   - 최소 타이밍 점수: **{cfg['min_timing_score']:.2f}**

3. **리스크 엔진**
   - 고정 손절: **{cfg['fixed_stop_loss']:.0%}**
   - 최대 보유 종목 수: **{cfg['max_positions']}개**
   - 중립장 목표 비중: **{cfg['neutral_target_ratio']:.0%}**
   - 위험장 목표 비중: **{cfg['riskoff_target_ratio']:.0%}**

4. **의사결정 단계**
   - {signal_label('BUY', execution_window=execution_window)}: 점수 **{cfg['buy_threshold']:.2f}** 이상
   - {signal_label('BUY_WATCH', execution_window=execution_window)}: WATCH 중에서도 점수 **{cfg['pre_signal_threshold']:.2f}** 이상
   - {signal_label('HOLD', execution_window=execution_window)}: 기존 보유 유지
   - {signal_label('SELL_WATCH', execution_window=execution_window)}: HOLD이지만 위험 플래그 또는 점수 약화가 보이는 상태
   - {signal_label('SELL', execution_window=execution_window)}: 점수 **{cfg['sell_threshold']:.2f}** 이하 또는 손절/품질/타이밍 조건 훼손 시 청산
   - 장후에는 위 신호를 `즉시 실행`이 아니라 `익일 실행 계획`으로 해석합니다.

5. **운영 스케줄**
   - 장중 30분마다 키움 현재가 반영 후 fast alert
   - 장마감 전 1회 리스크 점검
   - 장 종료 후 EOD* 종가 기준 전체 최신화

6. **익일 실행 원칙**
   - {signal_label('BUY', execution_window=False)}: 다음 날 시초 과열 추격은 피하고, 초반 5~15분 가격 안정 또는 첫 눌림 확인 뒤 진입을 우선합니다.
   - {signal_label('SELL', execution_window=False)}: 다음 날 장 초반 유동성 구간에서 우선 점검하고, 손절 훼손이 크면 지체 없이 정리합니다.
   - {signal_label('BUY_WATCH', execution_window=False)} / {signal_label('SELL_WATCH', execution_window=False)}: 장중 확정 신호가 아니라 익일 우선 관찰 목록으로 해석합니다.

7. **최적 MA 보조지표**
   - `all_action_modes_returns_by_stock.csv`에서 종목별 월/주 최적 MA만 따로 선정합니다.
   - `일치`: 기존 신호와 최적 MA 방향이 같음
   - `불일치`: 기존 신호와 최적 MA 방향이 다름
   - 소프트 반영은 **표시점수 ±0.020**으로만 적용하고, 현재 실행 로직은 그대로 유지합니다.
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
    return (
        f"현재 시장 상태는 {regime}이며 노출 비중은 {exposure:.2f}입니다. "
        f"{signal_label('BUY', execution_window=execution_window)} {counts.get('BUY', 0)}건, {signal_label('BUY_WATCH', execution_window=execution_window)} {counts.get('BUY_WATCH', 0)}건, "
        f"{signal_label('HOLD', execution_window=execution_window)} {counts.get('HOLD', 0)}건, {signal_label('SELL_WATCH', execution_window=execution_window)} {counts.get('SELL_WATCH', 0)}건, "
        f"{signal_label('SELL', execution_window=execution_window)} {counts.get('SELL', 0)}건입니다."
    )


def render_today_decision(signal_df: pd.DataFrame, decision_df: pd.DataFrame, data: dict[str, Any], cfg: dict[str, Any]) -> None:
    st.subheader("오늘의 의사결정")
    st.write(decision_text(signal_df, decision_df))
    render_cards(build_cards(signal_df, decision_df, data))
    if signal_df.empty:
        st.info("최신 전략 신호가 없습니다.")
        return

    feature_latest = load_feature_latest_snapshot(data["version_tokens"]["output"])
    latest_price = load_price_latest_snapshot(data["version_tokens"]["price"])
    fast_state = load_fast_position_state(data["version_tokens"]["output"])
    optimal_ma_latest = load_optimal_ma_latest_snapshot(data["version_tokens"]["optimal_ma"])
    if not feature_latest.empty:
        quarter_info = feature_latest[["code", "fiscal_year_pti", "reprt_code_pti", "filing_date_pti"]].copy()
        quarter_info["근거 기준 분기"] = quarter_info.apply(
            lambda row: format_quarter_label(row.get("fiscal_year_pti"), row.get("reprt_code_pti")),
            axis=1,
        )
        quarter_info["기준 공시일"] = pd.to_datetime(
            quarter_info["filing_date_pti"], errors="coerce"
        ).dt.date.astype("string").fillna("-")
        signal_df = signal_df.merge(
            quarter_info[["code", "근거 기준 분기", "기준 공시일"]],
            on="code",
            how="left",
        )
    if not optimal_ma_latest.empty:
        signal_df = signal_df.merge(
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
    signal_df["optimal_ma_alignment"] = signal_df.apply(
        lambda row: _optimal_ma_alignment_text(row.get("display_signal"), row.get("optimal_ma_ok")),
        axis=1,
    )
    signal_df["optimal_ma_soft_delta"] = signal_df.apply(
        lambda row: optimal_ma_soft_delta(row.get("display_signal"), row.get("optimal_ma_ok")),
        axis=1,
    )
    signal_df["display_conviction_score"] = signal_df.apply(
        lambda row: _clip_score(_safe_float(row.get("conviction_score"), 0.0) + _safe_float(row.get("optimal_ma_soft_delta"), 0.0))
        if pd.notna(row.get("conviction_score"))
        else float("nan"),
        axis=1,
    )
    signal_df["최적 MA"] = signal_df.apply(_optimal_ma_compact_text, axis=1)
    signal_df["최적 MA 상세"] = signal_df.apply(_optimal_ma_detail_text, axis=1)

    execution_window = is_execution_window()
    price_guides = signal_df.apply(
        lambda row: build_compact_price_guide(
            row,
            live_quotes=data["live_quotes"],
            latest_price=latest_price,
            fast_state=fast_state,
            execution_window=execution_window,
        ),
        axis=1,
    )
    signal_df["가격 기준"] = [x[0] for x in price_guides]
    signal_df["가격 규칙"] = [x[1] for x in price_guides]

    view_df = signal_df[["display_signal_ko", "code", "name", "industry", "conviction_score", "display_conviction_score", "optimal_ma_soft_delta", "근거 기준 분기", "기준 공시일", "최적 MA", "가격 기준", "가격 규칙", "active_execution_guide", "reason_1", "reason_2", "reason_3", "risk_flag"]].rename(
        columns={
            "display_signal_ko": "의사결정",
            "code": "종목코드",
            "name": "종목명",
            "industry": "업종",
            "conviction_score": "확신점수",
            "display_conviction_score": "표시점수",
            "optimal_ma_soft_delta": "최적MA 가점",
            "근거 기준 분기": "근거 기준 분기",
            "기준 공시일": "기준 공시일",
            "active_execution_guide": "실행 가이드",
            "reason_1": "근거 1",
            "reason_2": "근거 2",
            "reason_3": "근거 3",
            "risk_flag": "리스크",
        }
    )
    render_decision_summary_table(view_df)

    st.markdown("##### 종목 선택")
    options = [(row["code"], f"{row['display_signal_ko']} · {row['code']} {row['name']}") for _, row in signal_df.iterrows()]
    if "selected_code" not in st.session_state and options:
        st.session_state["selected_code"] = options[0][0]
    if options and st.session_state.get("selected_code") not in [code for code, _ in options]:
        st.session_state["selected_code"] = options[0][0]

    button_cols = st.columns(min(4, max(1, len(options))))
    for idx, (code, label) in enumerate(options[:12]):
        with button_cols[idx % len(button_cols)]:
            if st.button(label, key=f"pick_{code}", use_container_width=True):
                st.session_state["selected_code"] = code

    selected_code = st.selectbox(
        "상세 분석 종목",
        [code for code, _ in options],
        index=[code for code, _ in options].index(st.session_state["selected_code"]),
        format_func=lambda x: next((label for code, label in options if code == x), x),
    )
    st.session_state["selected_code"] = selected_code

    selected_row = signal_df[signal_df["code"] == selected_code].iloc[0]
    version_tokens = data["version_tokens"]
    price_df = load_price_history(selected_code, version_tokens["price"])
    price_df, live_info = attach_live_quote(price_df, selected_code, data["live_quotes"])
    fundamental_df = load_fundamental(selected_code, version_tokens["fundamental"])
    macro_df = load_macro(version_tokens["macro"])
    position_row = fast_state[fast_state["code"] == selected_code].iloc[-1] if not fast_state.empty and (fast_state["code"] == selected_code).any() else None
    ma_snapshot = latest_ma_snapshot(price_df)

    left, right = st.columns([1.7, 1.1])
    with left:
        timeframe = st.radio("차트 기준", ["일봉", "주봉", "월봉"], horizontal=True, key="chart_timeframe")
        bars = resample_ohlcv(price_df, timeframe).tail(180 if timeframe == "일봉" else 120)
        st.altair_chart(candlestick_chart(bars, f"{selected_row['name']} ({selected_code}) · {timeframe}"), use_container_width=True)
        if not bars.empty:
            st.altair_chart(line_chart(bars, "volume", "거래량", "#7c3aed"), use_container_width=True)

    with right:
        current_price = None
        current_basis = "-"
        if live_info:
            current_price = _safe_float(live_info.get("close"), float("nan"))
            quote_time = live_info.get("quote_time")
            current_basis = str(quote_time) if quote_time else "장중 현재가"
        elif not price_df.empty:
            last = price_df.iloc[-1]
            current_price = _safe_float(last["close"], float("nan"))
            current_basis = format_eod_basis(last["date"])
        price_execution_guide = build_price_execution_guide(
            selected_row,
            current_price=current_price if current_price is not None and not pd.isna(current_price) else None,
            current_basis=current_basis,
            execution_window=is_execution_window(),
            position_row=position_row,
        )
        st.markdown("##### 현재 신호 요약")
        st.metric("의사결정", selected_row["display_signal_ko"])
        st.metric("확신 점수", f"{_safe_float(selected_row['conviction_score']):.3f}")
        if pd.notna(selected_row.get("display_conviction_score")):
            st.caption(
                f"최적 MA 소프트 반영: {_optimal_ma_delta_text(_safe_float(selected_row.get('optimal_ma_soft_delta'), 0.0))} "
                f"/ 표시점수 {_safe_float(selected_row.get('display_conviction_score')):.3f}"
            )
        st.markdown(
            f"<div class='ns-subtle'><strong>최적 MA</strong><br>{selected_row.get('최적 MA 상세', '최적 MA 데이터 없음')}</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"실행 가이드: {price_execution_guide}")
        if ma_snapshot:
            monthly_status = "상향" if pd.notna(ma_snapshot.get("monthly_ma10")) and pd.notna(ma_snapshot.get("daily_close")) and ma_snapshot["daily_close"] >= ma_snapshot["monthly_ma10"] else "하향"
            weekly_status = "상향" if pd.notna(ma_snapshot.get("weekly_ma10")) and pd.notna(ma_snapshot.get("daily_close")) and ma_snapshot["daily_close"] >= ma_snapshot["weekly_ma10"] else "하향"
            st.caption(
                "이평 상태: "
                f"월봉10 {_format_large_number(ma_snapshot.get('monthly_ma10'))}({monthly_status}) / "
                f"주봉10 {_format_large_number(ma_snapshot.get('weekly_ma10'))}({weekly_status}) / "
                f"일봉20 {_format_large_number(ma_snapshot.get('daily_ma20'))}"
            )
        if not fundamental_df.empty:
            latest_fund = fundamental_df.iloc[-1]
            st.caption(f"근거 기준 분기: {latest_fund['분기']} / 공시일 {pd.to_datetime(latest_fund['공시일']).date()}")
        st.caption(f"핵심 근거 1: {selected_row['reason_1']}")
        st.caption(f"핵심 근거 2: {selected_row['reason_2']}")
        st.caption(f"핵심 근거 3: {selected_row['reason_3']}")
        if pd.notna(selected_row["risk_flag"]):
            st.warning(f"리스크 플래그: {selected_row['risk_flag']}")
        if live_info:
            st.markdown("##### 현재가 오버레이")
            st.metric("현재가", f"{_safe_float(live_info.get('close')):,.0f}")
            st.caption(f"호가 시각: {live_info.get('quote_time', '-')}")
            st.caption(f"당일 변동률: {_safe_float(live_info.get('change_pct')):.2f}%")
        elif not price_df.empty:
            last = price_df.iloc[-1]
            st.metric("종가", f"{_safe_float(last['close']):,.0f}")
            st.caption(f"기준일: {pd.to_datetime(last['date']).date()}")

    tabs = st.tabs(["재무 데이터", "공통 매크로", "업데이트 메타"])
    with tabs[0]:
        if fundamental_df.empty:
            st.info("선택한 종목의 재무 데이터가 없습니다.")
        else:
            latest_fund = fundamental_df.iloc[-1]
            cards = st.columns(4)
            with cards[0]:
                st.metric("최근 분기 매출", _format_large_number(latest_fund.get("분기매출액")))
            with cards[1]:
                st.metric("최근 분기 영업이익", _format_large_number(latest_fund.get("분기영업이익")))
            with cards[2]:
                st.metric("최근 분기 당기순이익", _format_large_number(latest_fund.get("분기당기순이익")))
            with cards[3]:
                st.metric("최근 분기 영업이익률", f"{_safe_float(latest_fund.get('분기영업이익률')):.2%}")
            render_table(fundamental_df[["분기", "공시일", "분기매출액", "분기영업이익", "분기당기순이익", "분기영업이익률"]].tail(8).sort_values("공시일", ascending=False))
    with tabs[1]:
        macro_snapshot = current_macro_snapshot(macro_df)
        if not macro_snapshot.empty:
            render_table(macro_snapshot)
        recent_macro = macro_df.sort_values("date").tail(120)
        for metric, color in [("kospi", "#0f766e"), ("vix", "#dc2626"), ("usdkrw", "#1d4ed8")]:
            if metric in recent_macro.columns and not recent_macro[metric].dropna().empty:
                st.altair_chart(line_chart(recent_macro, metric, metric.upper(), color), use_container_width=True)
    with tabs[2]:
        st.write(
            {
                "주가 최신일": data["refresh_meta"].get("price_date_max") or data["refresh_meta"].get("latest_price_date"),
                "feature 최신일": data["refresh_meta"].get("feature_date_max"),
                "fast alert 최신일": data["fast_meta"].get("latest_signal_date"),
                "live_quotes 적용": bool(data["fast_meta"].get("live_quotes_applied")),
                "최근 작업": data["schedule_state"].get("last_action", "-"),
            }
        )


def render_strategy_report(data: dict[str, Any]) -> None:
    cfg = load_default_config(data["meta"])
    signal_df = prepare_signal_display(data["signals"], cfg)
    decision_df = data["decision"]
    st.title("정량 투자 전략 보고서")
    st.markdown(
        f"<span class='ns-badge'>오늘 날짜 {datetime.now(SEOUL_TZ).strftime('%Y-%m-%d')}</span>"
        f"<span class='ns-subtle'>현재 기준 의사결정, 전략 로직, 준비된 데이터, 시스템 구성을 한 화면에서 확인합니다.</span>",
        unsafe_allow_html=True,
    )
    show_flash()
    render_today_decision(signal_df, decision_df, data, cfg)
    st.markdown("---")
    st.subheader("전략 개요")
    render_strategy_logic(cfg)
    render_term_notes()
    st.markdown("---")
    st.subheader("준비된 데이터")
    inventory = build_inventory(data)
    render_table(inventory) if not inventory.empty else st.info("표시할 데이터 인벤토리가 없습니다.")
    st.markdown("---")
    st.subheader("시스템 아키텍처")
    render_architecture()


def interpret_row(row: pd.Series) -> str:
    diff = _safe_float(row.get("mean_diff"))
    win_diff = _safe_float(row.get("win_rate_diff"))
    direction = "유리" if diff > 0 else "불리"
    win_direction = "높게" if win_diff > 0 else "낮게"
    condition = _translate_condition(row.get("condition", "-"))
    target = _translate_target(row.get("target", "-"))
    return f"`{condition}` 조건은 {target} 기준으로 평균 수익률이 {direction}하며 승률도 {win_direction} 나타났습니다."


def build_runtime_health_table(data: dict[str, Any]) -> pd.DataFrame:
    latest_dates = load_latest_data_dates(data["version_tokens"]["macro"], data["version_tokens"]["fundamental"])
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
            "데이터셋": "실시간 현재가",
            "행 수": live_rows,
            "시작일": live_latest,
            "최신일": live_latest,
            "종목 수": live_codes,
            "설명": "키움 live_quotes.csv 최신 기준",
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
    st.title("데이터 상태")
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
    st.title("백테스트")
    if not data["eval"].empty:
        st.subheader("전략 성과 요약")
        render_table(data["eval"])
    st.info("백테스트 화면은 규칙 후보와 조건부 성과를 통해 의사결정 로직을 개선하기 위한 탐색용 화면입니다. 오늘의 의사결정과 직접 동일한 로직은 아닙니다.")
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


def render_post_audit(data: dict[str, Any]) -> None:
    st.title("사후검증")
    if MANUAL_TRADES_PATH.exists():
        manual_all = pd.read_csv(MANUAL_TRADES_PATH, dtype={"chat_id": str}, low_memory=False)
    else:
        manual_all = pd.DataFrame()
    if not manual_all.empty:
        chat_ids = [x for x in manual_all["chat_id"].astype(str).dropna().unique().tolist() if x]
        chat_ids = sorted(chat_ids)
        visible_chat_ids = [x for x in chat_ids if "_test" not in x.lower()]
        if visible_chat_ids:
            chat_ids = visible_chat_ids
        default_chat = chat_ids[-1]
        selected_chat = st.selectbox("실체결 검증 대상", chat_ids, index=chat_ids.index(default_chat))
        manual_token = MANUAL_TRADES_PATH.stat().st_mtime if MANUAL_TRADES_PATH.exists() else 0
        manual_audit, manual_detail = load_manual_trade_audit(data["version_tokens"]["price"], manual_token, selected_chat)
        st.subheader("텔레그램 실체결 기준 사후검증")
        st.caption("텔레그램으로 입력한 매수/매도 체결가를 기준으로, 해당일 최종종가와 1영업일 후·7영업일 후 종가 방향이 실제로 유리했는지 검증합니다.")
        if not manual_audit.empty:
            render_table(manual_audit)
        else:
            st.info("선택한 chat_id의 실체결 검증 데이터가 아직 충분하지 않습니다.")
        if not manual_detail.empty:
            st.subheader("실체결 상세 검증")
            render_table(manual_detail.head(100))
    else:
        st.info("텔레그램 실체결 기록이 아직 없습니다. 텔레그램에서 `매수 삼성전자 70000 10` 또는 `매도 005930 73000 5` 형식으로 기록하면 여기서 검증합니다.")

    timing_audit = load_signal_timing_audit(data["version_tokens"]["output"], data["version_tokens"]["price"])
    if not timing_audit.empty:
        st.subheader("신호일 종가 기준 사후검증")
        st.caption("종목 단위 신호가 발생한 날짜를 기준으로, 그날 정규장 종가와 1영업일 후·7영업일 후 정규장 종가 방향이 실제로 유리했는지 요약합니다.")
        st.caption("이 표는 실체결가가 아니라 신호 발생일 정규장 종가를 기준으로 한 연구용 검증입니다.")
        render_table(timing_audit)
    execution_audit, execution_detail = load_execution_timing_audit(data["version_tokens"]["output"], data["version_tokens"]["price"])
    if not execution_audit.empty:
        with st.expander("전략 시뮬레이션 체결 로그 기준 검증", expanded=False):
            st.caption("이 섹션은 전략 엔진의 내부 trade_log 기준입니다. 실제 텔레그램 실체결과는 별도입니다.")
            render_table(execution_audit)
            if not execution_detail.empty:
                render_table(execution_detail.head(50))


def render_settings(data: dict[str, Any]) -> None:
    st.title("전략 설정")
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
            launch_pipeline_job(cfg, "fast alert 재계산", fast_alerts=True)
            st.rerun()
    with col2:
        if st.button("저장값으로 전체 재계산", use_container_width=True):
            launch_pipeline_job(cfg, "전체 재계산")
            st.rerun()
    with col3:
        if st.button("저장값으로 최신화 + 알림", use_container_width=True):
            launch_pipeline_job(
                cfg,
                "주가/매크로/금 전체 증분 최신화와 알림 발송",
                refresh_data=True,
                refresh_macro=True,
                refresh_gold=True,
                fast_alerts=True,
                send_alerts=True,
            )
            st.rerun()
    show_df = pd.DataFrame([{"구분": spec["group"], "파라미터": spec["key"], "설정명": spec["label"], "값": cfg[spec["key"]], "설명": spec["help"]} for spec in CONFIG_SPECS])
    render_table(show_df)
    show_last_command_output()


def render_access_guide() -> None:
    st.title("접속 안내")
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
    latest_dates = load_latest_data_dates(data["version_tokens"]["macro"], data["version_tokens"]["fundamental"])
    live_latest = "-"
    if not data["live_quotes"].empty:
        live_dates = pd.to_datetime(data["live_quotes"]["date"], errors="coerce").dropna()
        if not live_dates.empty:
            live_latest = str(live_dates.max().date())
    st.sidebar.markdown("### 데이터 최신 상태")
    st.sidebar.markdown(
        "\n".join(
            [
                f"- **주가 최신일**: {latest_dates['price_latest']}",
                f"- **feature 최신일**: {latest_dates['feature_latest']}",
                f"- **매크로 최신일**: {latest_dates['macro_latest']}",
                f"- **재무 최신일**: {latest_dates['fundamental_latest']}",
                f"- **실시간 현재가 최신일**: {live_latest}",
            ]
        )
    )
    st.sidebar.markdown("### 서비스 상태")
    st.sidebar.markdown("\n".join(build_service_status(data)))
    st.sidebar.markdown("### 빠른 실행")
    cfg = load_default_config(data["meta"])
    if st.sidebar.button("전체 증분 최신화 + fast alert", use_container_width=True, key="sidebar_refresh_fast"):
        launch_pipeline_job(
            cfg,
            "주가/매크로/금 전체 증분 최신화와 fast alert",
            refresh_data=True,
            refresh_macro=True,
            refresh_gold=True,
            fast_alerts=True,
        )
        st.rerun()
    if st.sidebar.button("전체 증분 최신화 + 전체 재계산", use_container_width=True, key="sidebar_refresh_full"):
        launch_pipeline_job(
            cfg,
            "주가/매크로/금 전체 증분 최신화와 전체 재계산",
            refresh_data=True,
            refresh_macro=True,
            refresh_gold=True,
        )
        st.rerun()
    render_pipeline_progress()
    st.sidebar.caption("대시보드 주소: http://192.168.219.113:8501")


def main() -> None:
    st.set_page_config(page_title="new_strategy 대시보드", layout="wide")
    inject_base_css()
    version_tokens = build_version_tokens()
    data = load_output_data(version_tokens["output"])
    data["version_tokens"] = version_tokens
    with st.sidebar:
        render_live_clock("sidebar_live_clock", compact=True)
    st.sidebar.markdown("## 운영 패널")
    page = st.sidebar.radio("화면 선택", ["전략 보고서", "데이터 상태", "백테스트", "사후검증", "전략 설정", "접속 안내"], index=0)
    render_sidebar_panel(data)
    if page == "전략 보고서":
        render_strategy_report(data)
    elif page == "데이터 상태":
        render_data_health(data)
    elif page == "백테스트":
        render_backtest(data)
    elif page == "사후검증":
        render_post_audit(data)
    elif page == "전략 설정":
        render_settings(data)
    else:
        render_access_guide()
    render_footer(data)


if __name__ == "__main__":
    main()


