from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any, TextIO

import pandas as pd

from new_strategy.paths import data_path, output_path, strategy_output_path
from new_strategy.optimal_ma_overlay import (
    load_latest_optimal_ma_snapshot,
    optimal_ma_alignment,
    optimal_ma_soft_delta,
)
from new_strategy.telegram_bridge_memory import load_recent_unhandled
from new_strategy.telegram_bridge_portfolio import (
    ParsedTrade,
    manual_trade_history_text,
    normalize_code,
    portfolio_snapshot,
    portfolio_status_line,
    portfolio_summary_text,
    position_detail_line,
    record_manual_trade,
)


APP_DIR = strategy_output_path()
BRIDGE_DIR = APP_DIR / "telegram_bridge"
REPO_ROOT = Path(__file__).resolve().parent.parent
STREAMLIT_START_SCRIPT = REPO_ROOT / "new_strategy" / "run_streamlit_dashboard.ps1"
STREAMLIT_STOP_SCRIPT = REPO_ROOT / "new_strategy" / "stop_streamlit_dashboard.ps1"
PRICE_META_PATH = data_path("price_panel_meta.json")
FEATURE_META_PATH = data_path("feature_daily_meta.json")
REFRESH_META_PATH = APP_DIR / "refresh_runtime_metadata.json"
FAST_ALERT_META_PATH = APP_DIR / "fast_alert_metadata.json"
STRATEGY_META_PATH = APP_DIR / "strategy_metadata.json"
LIVE_QUOTES_PATH = data_path("live_quotes.csv")
FEATURE_DATA_PATH = data_path("feature_daily.pkl")
UNHANDLED_PATH = BRIDGE_DIR / "telegram_bridge_unhandled_log.csv"
NOTES_PATH = BRIDGE_DIR / "telegram_bridge_notes.csv"
BRIDGE_STATE_PATH = BRIDGE_DIR / "telegram_bridge_state.json"
FRAME_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
INTRADAY_RECALC_MINUTES = 30

EXCLUDED_SECURITIES = {
    "005390": {
        "name": "신성통상",
        "reason": "상장폐지 처리 종목",
        "scope": "일반 신호/장중 대응 대상에서 제외",
    }
}

NOISE_RE = re.compile(r"^[\s\W_]+$")
SHORT_NOISE_RE = re.compile(r"^[A-Za-z]{1,4}$")
CODE_RE = re.compile(r"\b([0-9A-Za-z]{4,6})\b")

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
SIGNAL_ORDER = {"BUY": 0, "BUY_WATCH": 1, "HOLD": 2, "WATCH": 3, "SELL_WATCH": 4, "SELL": 5}
EXIT_REASON_LABELS = {
    "timing_break": "타이밍 훼손",
    "stop_loss": "손절",
    "quality_drop": "품질 저하",
    "max_holding_days": "최대 보유일 도달",
    "signal_sell": "매도 신호 전환",
}
EXIT_REASON_DESCRIPTIONS = {
    "timing_break": "단기 타이밍 보조 조건이 깨져 청산했습니다.",
    "stop_loss": "손절 기준에 도달해 청산했습니다.",
    "quality_drop": "핵심 실적 또는 품질 조건이 약해져 청산했습니다.",
    "max_holding_days": "최대 보유 기간에 도달해 청산했습니다.",
    "signal_sell": "전략 신호가 매도로 전환되어 청산했습니다.",
}

RISK_FLAG_LABELS = {
    "macro_risk_off": "매크로 위험장",
    "high_volatility": "고변동성",
    "earnings_exception": "실적 예외",
    "weekly_sell_watch": "주봉 매도경계",
    "monthly_overheat": "월봉 과열",
    "timing_break": "타이밍 훼손",
    "quality_drop": "품질 저하",
    "stop_loss": "손절 기준",
}


@dataclass
class JobSpec:
    action: str
    summary: str
    command: list[str]
    require_confirm: bool = True


@dataclass
class LocalReply:
    text: str
    answered: bool


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_csv_cached(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    key = str(path)
    mtime = path.stat().st_mtime
    cached = FRAME_CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1].copy()
    df = pd.read_csv(path, low_memory=False, **kwargs)
    FRAME_CACHE[key] = (mtime, df)
    return df.copy()


def _fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):+.2%}"


def _fmt_num(value: Any, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):,.0f}{suffix}"


def _display_text(value: Any, default: str = "없음") -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _market_state_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    return {
        "risk_on": "정상구간",
        "neutral": "주의구간",
        "risk_off": "방어구간",
    }.get(text, text or "unknown")


def _operating_intensity_label(exposure: Any) -> str:
    try:
        value = float(exposure)
    except Exception:
        return "-"
    if value >= 0.95:
        return "100%"
    if value >= 0.55:
        return "70%"
    if value >= 0.25:
        return "40%"
    return f"{value:.0%}"


def _prettify_risk_flag(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = [RISK_FLAG_LABELS.get(part.strip(), part.strip().replace("_", " ")) for part in raw.split("|") if part.strip()]
    return " · ".join(parts)


def _count_signal(counts: dict[str, int], signal: str) -> int:
    signal = str(signal or "").upper()
    if signal == "BUY_WATCH":
        return int(counts.get("BUY_WATCH", 0)) + int(counts.get("WATCH", 0))
    return int(counts.get(signal, 0))


def _signal_distribution_text(counts: dict[str, int], *, execution_window: bool) -> str:
    return (
        f"{_signal_label('BUY', execution_window=execution_window)} {_count_signal(counts, 'BUY')} / "
        f"{_signal_label('BUY_WATCH', execution_window=execution_window)} {_count_signal(counts, 'BUY_WATCH')} / "
        f"{_signal_label('HOLD', execution_window=execution_window)} {_count_signal(counts, 'HOLD')} / "
        f"{_signal_label('SELL_WATCH', execution_window=execution_window)} {_count_signal(counts, 'SELL_WATCH')} / "
        f"{_signal_label('SELL', execution_window=execution_window)} {_count_signal(counts, 'SELL')}"
    )


def _v2_timing_summary_text(row: pd.Series | dict[str, Any]) -> str:
    month_window = pd.to_numeric(pd.Series([row.get("v2_month_window")]), errors="coerce").iloc[0]
    month_dist = pd.to_numeric(pd.Series([row.get("v2_month_period_dist")]), errors="coerce").iloc[0]
    week_window = pd.to_numeric(pd.Series([row.get("v2_week_window")]), errors="coerce").iloc[0]
    week_dist = pd.to_numeric(pd.Series([row.get("v2_week_period_dist")]), errors="coerce").iloc[0]
    month_ready = bool(row.get("v2_month_buy_ready", row.get("monthly_main_ok", False)))
    week_sell = bool(row.get("v2_week_sell_trigger", False))
    week_watch = bool(row.get("v2_week_sell_watch", False))

    parts: list[str] = []
    if pd.notna(month_window):
        month_state = "매수 준비" if month_ready else "매수 대기"
        month_suffix = f", {_fmt_pct(month_dist)}" if pd.notna(month_dist) else ""
        parts.append(f"월봉 {month_state}(최적 {int(float(month_window))}이평{month_suffix})")
    if pd.notna(week_window):
        if week_sell:
            week_state = "매도 트리거"
        elif week_watch:
            week_state = "매도 경계"
        else:
            week_state = "정상"
        week_suffix = f", {_fmt_pct(week_dist)}" if pd.notna(week_dist) else ""
        parts.append(f"주봉 {week_state}(최적 {int(float(week_window))}이평{week_suffix})")
    return " / ".join(parts) if parts else "V2 타이밍 데이터 없음"


def _v2_timing_detail_lines(row: pd.Series | dict[str, Any]) -> list[str]:
    month_window = pd.to_numeric(pd.Series([row.get("v2_month_window")]), errors="coerce").iloc[0]
    month_dist = pd.to_numeric(pd.Series([row.get("v2_month_period_dist")]), errors="coerce").iloc[0]
    week_window = pd.to_numeric(pd.Series([row.get("v2_week_window")]), errors="coerce").iloc[0]
    week_dist = pd.to_numeric(pd.Series([row.get("v2_week_period_dist")]), errors="coerce").iloc[0]
    month_ready = bool(row.get("v2_month_buy_ready", row.get("monthly_main_ok", False)))
    week_sell = bool(row.get("v2_week_sell_trigger", False))
    week_watch = bool(row.get("v2_week_sell_watch", False))

    lines: list[str] = []
    if pd.notna(month_window):
        month_state = "매수 준비" if month_ready else "매수 대기"
        month_dist_text = _fmt_pct(month_dist) if pd.notna(month_dist) else "n/a"
        lines.append(f"- V2 월봉 상태: {month_state} | 최적 월이평 {int(float(month_window))} | 기준 이격 {month_dist_text}")
    if pd.notna(week_window):
        if week_sell:
            week_state = "매도 트리거"
        elif week_watch:
            week_state = "매도 경계"
        else:
            week_state = "정상"
        week_dist_text = _fmt_pct(week_dist) if pd.notna(week_dist) else "n/a"
        lines.append(f"- V2 주봉 상태: {week_state} | 최적 주이평 {int(float(week_window))} | 기준 이격 {week_dist_text}")
    return lines


def _excluded_security_text(identifier: str) -> str:
    query = str(identifier or "").strip()
    norm = normalize_code(query)
    target = EXCLUDED_SECURITIES.get(norm)
    if target is None:
        for code, info in EXCLUDED_SECURITIES.items():
            if str(info.get("name") or "").strip() == query:
                target = info
                norm = code
                break
    if target is None:
        return ""
    return "\n".join(
        [
            f"{norm} {target['name']}은 현재 전략 조회 대상이 아닙니다.",
            f"- 사유: {target['reason']}",
            f"- 범위: {target['scope']}",
        ]
    )


def _out_of_universe_text(code: str, name: str) -> str:
    return "\n".join(
        [
            f"{code} {name}은 현재 전략 유니버스 밖입니다.",
            "- 가격 데이터는 남아 있지만 최신 전략 평가/장중 대응 대상에는 포함되지 않습니다.",
            "- 최근 signal 또는 feature 스냅샷에 없어 일반 종목 정보처럼 답하지 않습니다.",
        ]
    )


def _parse_stop_pct(value: Any) -> float | None:
    text = str(value or "").strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text) / 100.0
    except Exception:
        return None


def _risk_levels(row: pd.Series | dict[str, Any], *, current_price: float | None, entry_price: float | None = None) -> dict[str, float | None]:
    stop_pct = _parse_stop_pct(row.get("stop_rule"))
    month_10_ma = None if pd.isna(row.get("month_10_ma")) else float(row.get("month_10_ma"))
    week_10_ma = None if pd.isna(row.get("week_10_ma")) else float(row.get("week_10_ma"))
    day_20_ma = None if pd.isna(row.get("ma_day_20")) else float(row.get("ma_day_20"))

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


def _current_action_text(signal: Any, *, execution_window: bool) -> str:
    signal_text = str(signal or "").strip().upper()
    if execution_window:
        mapping = {
            "BUY": "분할 매수 검토",
            "BUY_WATCH": "관심 유지, 강하면 소액매수 검토",
            "WATCH": "관심 유지",
            "HOLD": "보유 유지",
            "SELL_WATCH": "비중축소 우선 검토",
            "SELL": "매도 우선",
        }
    else:
        mapping = {
            "BUY": "익일 매수 준비",
            "BUY_WATCH": "익일 관심 유지, 강하면 소액매수 검토",
            "WATCH": "익일 관심 유지",
            "HOLD": "익일보유 유지",
            "SELL_WATCH": "익일 비중축소 우선 검토",
            "SELL": "익일 매도 우선",
        }
    return mapping.get(signal_text, "다음 신호 확인")


def _next_review_text(*, execution_window: bool) -> str:
    if execution_window:
        return "다음 장중 재계산 또는 조건 변화 시"
    return "익일 시초 또는 다음 장초반 점검 시"


def _brief_reason_text(row: pd.Series | dict[str, Any]) -> str:
    reason_1 = _display_text(row.get("reason_1"), "")
    reason_2 = _display_text(row.get("reason_2"), "")
    risk_flag = _prettify_risk_flag(row.get("risk_flag"))
    parts = [text for text in [reason_1, reason_2, risk_flag] if text]
    if not parts:
        return "전략 신호 변화 없음"
    return " / ".join(parts[:2]) if len(parts) > 1 else parts[0]


def _intraday_change_text(*, current_price: float | None, previous_close: float | None) -> str:
    if current_price is None or previous_close is None or previous_close == 0:
        return "n/a"
    return _fmt_pct(current_price / previous_close - 1.0)


def _execution_state_lines() -> list[str]:
    schedule_state = _read_json(APP_DIR / "market_schedule_state.json")
    last_intraday = schedule_state.get("last_intraday_slot") or "-"
    return [
        "[실행 상태]",
        "- 07:00 KRX 보조 데이터 갱신",
        f"- 08:10부터 {INTRADAY_RECALC_MINUTES}분마다 전종목 갱신 + fast 계산",
        f"- 마지막 장중 계산 시각: {last_intraday}",
        "- 20:10 장후 EOD 수집 + 마감 요약",
    ]


def _fmt_state_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return text


def _bridge_state_lines() -> list[str]:
    state = _read_json(BRIDGE_STATE_PATH)
    return [
        "[브리지 최근 상태]",
        f"- 마지막 루프 시각: {_fmt_state_timestamp(state.get('last_loop_at'))}",
        f"- 마지막 입력 시각: {_fmt_state_timestamp(state.get('last_incoming_at'))}",
        f"- 마지막 출력 시각: {_fmt_state_timestamp(state.get('last_outgoing_at'))}",
        f"- 마지막 예외 시각: {_fmt_state_timestamp(state.get('last_error_at'))}",
        f"- 마지막 선제발송 시각: {_fmt_state_timestamp(state.get('last_early_session_brief_at'))}",
    ]


def _quarter_label(fiscal_year: Any, reprt_code: Any) -> str:
    if pd.isna(fiscal_year) or pd.isna(reprt_code):
        return "n/a"
    quarter_map = {"11013": "1Q", "11012": "2Q", "11014": "3Q", "11011": "4Q"}
    try:
        year_text = str(int(float(fiscal_year)))
    except Exception:
        year_text = str(fiscal_year)
    return f"{year_text}-{quarter_map.get(str(reprt_code), str(reprt_code))}"


def _price_action_guide(row: pd.Series | dict[str, Any], *, current_price: float | None, current_basis: str) -> str:
    execution_window = _is_execution_window()
    base_guide = _action_guide(row, execution_window=execution_window)
    if current_price is None or pd.isna(current_price):
        return base_guide
    signal = str(row.get("signal") or "").upper()
    parts = [base_guide, f"기준가 {float(current_price):,.0f}원({current_basis})"]
    entry_price = None if pd.isna(row.get("entry_price")) else float(row.get("entry_price")) if row.get("entry_price") is not None else None
    levels = _risk_levels(row, current_price=float(current_price), entry_price=entry_price)
    if signal in {"BUY", "WATCH"}:
        parts.append(f"관찰 구간 {float(current_price) * 0.99:,.0f}~{float(current_price) * 1.01:,.0f}원")
        parts.append(f"추격 금지 상단 {float(current_price) * 1.02:,.0f}원")
        if levels["initial_stop"] is not None:
            parts.append(f"진입 후 초기 손절가 {levels['initial_stop']:,.0f}원")
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


def _is_execution_window(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    current = now.time()
    return time(8, 0) <= current <= time(20, 0)


def _signal_label(signal: Any, *, execution_window: bool | None = None) -> str:
    label_map = SIGNAL_LABELS_INTRADAY if (execution_window if execution_window is not None else _is_execution_window()) else SIGNAL_LABELS_POSTCLOSE
    return label_map.get(str(signal).upper(), str(signal))


def _default_action_guide(signal: Any, *, execution_window: bool) -> str:
    signal = str(signal).upper()
    if execution_window:
        guide_map = {
            "BUY": "추격보다 가격 안정 구간에서 분할 매수를 우선합니다.",
            "BUY_WATCH": "관심 유지가 기본입니다. 장중 강도와 거래대금이 좋으면 소액매수까지 검토합니다.",
            "WATCH": "관심 유지가 기본입니다. 아직은 주문보다 초반 흐름 확인이 우선입니다.",
            "HOLD": "보유 유지가 기본입니다. 방어선 이탈 시 비중축소 또는 매도로 전환합니다.",
            "SELL_WATCH": "비중축소 검토가 우선입니다. 약세가 이어지면 절반정리 또는 매도로 강화합니다.",
            "SELL": "실행 가능한 매도 신호입니다. 반등 대기보다 정리를 우선합니다.",
        }
    else:
        guide_map = {
            "BUY": "익일 시초 5~15분 대기 후 가격 안정 또는 첫 눌림 확인 뒤 분할 진입합니다.",
            "BUY_WATCH": "익일 관심 유지가 기본입니다. 시초 강도가 좋으면 소액매수를 검토하고, 아니면 관찰 유지로 둡니다.",
            "WATCH": "익일 관심 유지가 기본입니다. 주문보다 장초반 흐름 확인이 우선입니다.",
            "HOLD": "익일 보유 유지가 기본입니다. 시초 약세가 크면 비중축소, 방어선 이탈이면 매도로 전환합니다.",
            "SELL_WATCH": "익일 비중축소 검토가 우선입니다. 장초반 약세면 절반정리 또는 축소를 먼저 봅니다.",
            "SELL": "익일 장 초반 유동성 구간에서 매도를 우선합니다. 약세가 크면 지체 없이 정리합니다.",
        }
    return guide_map.get(signal, "장 시작 후 신호를 다시 확인합니다.")


def _action_guide(row: pd.Series | dict[str, Any], *, execution_window: bool) -> str:
    key = "intraday_action_guide" if execution_window else "next_day_action_guide"
    value = str(row.get(key) or "").strip()
    if value:
        return value
    return _default_action_guide(row.get("signal", ""), execution_window=execution_window)


def _signal_sort_key(signal: Any) -> int:
    return SIGNAL_ORDER.get(str(signal).upper(), 99)


def _display_sell_threshold() -> float:
    meta = _read_json(STRATEGY_META_PATH)
    try:
        return float(meta.get("config", {}).get("sell_threshold", 0.35))
    except Exception:
        return 0.35


def _display_signal(signal: Any, conviction_score: Any, risk_flag: Any) -> str:
    signal_text = str(signal or "").upper()
    risk_text = "" if pd.isna(risk_flag) else str(risk_flag).strip()
    if signal_text in {"BUY", "BUY_WATCH", "SELL", "SELL_WATCH"}:
        return signal_text
    if signal_text == "WATCH":
        return "BUY_WATCH"
    if signal_text == "HOLD" and "weekly_sell_watch" in {part.strip().lower() for part in risk_text.split("|") if part.strip()}:
        return "SELL_WATCH"
    return "HOLD"


def _optimal_ma_delta_text(delta: float) -> str:
    if abs(delta) < 1e-12:
        return "0.000"
    return f"{delta:+.3f}"


def _optimal_ma_summary_lines(row: pd.Series | dict[str, Any], *, signal_value: Any) -> list[str]:
    timeframe = _display_text(row.get("optimal_ma_timeframe_ko"), "")
    window = row.get("optimal_ma_window")
    if not timeframe or pd.isna(window):
        return ["- 최적 MA: 데이터 없음"]
    action_mode = _display_text(row.get("optimal_ma_action_mode_ko"), "-")
    alignment = optimal_ma_alignment(signal_value, row.get("optimal_ma_ok"))
    delta = optimal_ma_soft_delta(signal_value, row.get("optimal_ma_ok"))
    line_price = _fmt_num(row.get("optimal_ma_line_price"), "원")
    basis_label = _display_text(row.get("optimal_ma_basis_label"), "-")
    basis_price = _fmt_num(row.get("optimal_ma_basis_price"), "원")
    rule_text = _display_text(row.get("optimal_ma_rule_text"), "데이터 없음")
    return [
        f"- 최적 MA: {timeframe} {int(float(window))}이평 · {action_mode}",
        f"- 최적 MA 상태: {alignment} ({_optimal_ma_delta_text(delta)})",
        f"- 최적 MA 판정가: {basis_label} {basis_price}",
        f"- 최적 MA 기준선: {line_price}",
        f"- 최적 MA 해석: {rule_text}",
    ]


def _latest_existing_path(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda item: item.stat().st_mtime)


def _read_signal_latest() -> pd.DataFrame:
    path = _latest_existing_path([APP_DIR / "signal_daily_fast_latest.csv", APP_DIR / "signal_daily_latest.csv"])
    if path is None:
        return pd.DataFrame()
    df = _read_csv_cached(path, dtype={"code": str})
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).map(normalize_code)
    return df


def _read_signal_lookup() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    candidates = [
        (APP_DIR / "signal_daily_fast_latest.csv", 0),
        (APP_DIR / "signal_daily_latest.csv", 1),
    ]
    for path, source_rank in candidates:
        if not path.exists():
            continue
        df = _read_csv_cached(path, dtype={"code": str})
        if df.empty:
            continue
        work = df.copy()
        work["code"] = work["code"].astype(str).map(normalize_code)
        work["_source_rank"] = source_rank
        if "date" in work.columns:
            work["date"] = pd.to_datetime(work["date"], errors="coerce")
        frames.append(work)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    sort_cols = ["_source_rank", "code"]
    ascending = [True, True]
    if "date" in combined.columns:
        sort_cols = ["date", "_source_rank", "code"]
        ascending = [False, True, True]
    combined = combined.sort_values(sort_cols, ascending=ascending, kind="stable")
    combined = combined.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    return combined.drop(columns=["_source_rank"], errors="ignore")


def _read_decision_latest() -> pd.DataFrame:
    path = _latest_existing_path([APP_DIR / "decision_report_fast_latest.csv", APP_DIR / "decision_report_daily.csv"])
    if path is None:
        return pd.DataFrame()
    return _read_csv_cached(path)


def _read_strategy_eval() -> pd.DataFrame:
    return _read_csv_cached(APP_DIR / "strategy_eval.csv")


def _read_trade_log() -> pd.DataFrame:
    df = _read_csv_cached(APP_DIR / "trade_log.csv", dtype={"code": str})
    if not df.empty:
        df["code"] = df["code"].astype(str).map(normalize_code)
    return df


def _read_fast_positions() -> pd.DataFrame:
    df = _read_csv_cached(APP_DIR / "fast_position_state.csv", dtype={"code": str})
    if not df.empty:
        df["code"] = df["code"].astype(str).map(normalize_code)
    return df


def _read_alert_log() -> pd.DataFrame:
    df = _read_csv_cached(APP_DIR / "alert_log.csv", dtype={"code": str})
    if not df.empty and "code" in df.columns:
        df["code"] = df["code"].astype(str).map(normalize_code)
    return df


def _read_price_snapshot() -> pd.DataFrame:
    snapshot_path = APP_DIR / "price_panel_latest_snapshot.csv"
    price_path = data_path("price_panel.csv")
    if snapshot_path.exists() and (not price_path.exists() or snapshot_path.stat().st_mtime >= price_path.stat().st_mtime):
        df = _read_csv_cached(snapshot_path, dtype={"code": str})
        if not df.empty and "industry" in df.columns:
            df["code"] = df["code"].astype(str).map(normalize_code)
            return df
    if not price_path.exists():
        return pd.DataFrame(columns=["code", "name", "close", "date"])
    df = pd.read_csv(price_path, usecols=["code", "name", "close", "date", "industry"], dtype={"code": str}, low_memory=False)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["code", "date"])
    latest = df.groupby("code", as_index=False).tail(1).copy()
    latest["code"] = latest["code"].astype(str).map(normalize_code)
    latest.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
    return latest


def _read_feature_snapshot() -> pd.DataFrame:
    snapshot_path = APP_DIR / "feature_latest_snapshot.csv"
    feature_path = FEATURE_DATA_PATH
    if snapshot_path.exists() and (not feature_path.exists() or snapshot_path.stat().st_mtime >= feature_path.stat().st_mtime):
        df = pd.read_pickle(snapshot_path)
        if not df.empty:
            df["code"] = df["code"].astype(str).map(normalize_code)
            return df
    if not feature_path.exists():
        return pd.DataFrame()
    df = pd.read_pickle(feature_path)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["code", "date"])
    latest = df.groupby("code", as_index=False).tail(1).copy()
    latest["code"] = latest["code"].astype(str).map(normalize_code)
    latest.to_pickle(snapshot_path)
    return latest


def _read_optimal_ma_snapshot() -> pd.DataFrame:
    df = load_latest_optimal_ma_snapshot()
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).map(normalize_code)
    return df


def _read_live_quotes() -> pd.DataFrame:
    if not LIVE_QUOTES_PATH.exists():
        return pd.DataFrame()
    df = _read_csv_cached(LIVE_QUOTES_PATH, dtype={"code": str})
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).map(normalize_code)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def _runtime_data_snapshot() -> dict[str, str]:
    price_meta = _read_json(PRICE_META_PATH)
    feature_meta = _read_json(FEATURE_META_PATH)
    refresh_meta = _read_json(REFRESH_META_PATH)
    fast_meta = _read_json(FAST_ALERT_META_PATH)
    macro_path = data_path("macro_daily.csv")
    macro_max = (
        refresh_meta.get("macro", {}).get("macro_bounds", {}).get("date_max")
        or refresh_meta.get("macro_daily", {}).get("bounds", {}).get("date_max")
        or refresh_meta.get("refresh_meta", {}).get("macro_daily", {}).get("bounds", {}).get("date_max")
        or ""
    )
    if not macro_max and macro_path.exists():
        try:
            macro_df = pd.read_csv(macro_path, usecols=["date"], low_memory=False)
            macro_dates = pd.to_datetime(macro_df["date"], errors="coerce").dropna()
            if not macro_dates.empty:
                macro_max = str(macro_dates.max().date())
        except Exception:
            macro_max = ""
    latest = {
        "price_date": str(price_meta.get("bounds", {}).get("date_max") or "-"),
        "feature_date": str(feature_meta.get("bounds", {}).get("date_max") or "-"),
        "macro_date": str(macro_max or "-"),
        "signal_date": str(fast_meta.get("latest_signal_date") or "-"),
        "live_quotes_applied": "예" if fast_meta.get("live_quotes_applied") else "아니오",
    }
    fund = _read_csv_cached(data_path("fundamental_quarterly_multi.csv"), dtype={"종목코드": str})
    if not fund.empty and "공시일" in fund.columns:
        fund_dates = pd.to_datetime(fund["공시일"], errors="coerce").dropna()
        latest["fundamental_date"] = str(fund_dates.max().date()) if not fund_dates.empty else "-"
    else:
        latest["fundamental_date"] = "-"

    live_quotes = _read_live_quotes()
    if not live_quotes.empty and "date" in live_quotes.columns:
        live_dates = live_quotes["date"].dropna()
        latest["live_quote_date"] = str(live_dates.max().date()) if not live_dates.empty else "-"
    else:
        latest["live_quote_date"] = "-"
    return latest


def _process_running(pattern: str) -> bool:
    cmd = (
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.CommandLine -like '*{pattern}*' }} | "
        "Select-Object -First 1 ProcessId"
    )
    try:
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=8)
        return bool(proc.stdout.strip())
    except Exception:
        return False


def _streamlit_running() -> bool:
    try:
        conn = socket.create_connection(("127.0.0.1", 8501), timeout=2)
        conn.close()
        return True
    except Exception:
        return False


def _service_status_lines() -> list[str]:
    return [
        f"- 텔레그램 브리지: {'ON' if _process_running('new_strategy.telegram_bridge_service') else 'OFF'}",
        f"- 시장 스케줄 서비스: {'ON' if _process_running('new_strategy.run_market_schedule_service') else 'OFF'}",
        f"- 스트림릿 대시보드: {'ON' if _streamlit_running() else 'OFF'}",
    ]


def _extract_metric_from_reasons(row: pd.Series, prefix: str) -> str:
    for col in ["reason_1", "reason_2", "reason_3"]:
        text = str(row.get(col, "") or "")
        if text.startswith(prefix):
            return text.replace(prefix, "", 1).strip()
    return "n/a"


def _canonical_company_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    text = (
        text.replace("엘지", "lg")
        .replace("(주)", "")
        .replace("정보", "")
        .replace("신호", "")
        .replace("주가", "")
        .replace("왜", "")
        .replace("이유", "")
    )
    return text


def _is_preferred_name(name: str) -> bool:
    clean = str(name or "").strip()
    return bool(re.search(r"(우|1우|2우|3우|우B|우C)$", clean))


def _prefer_common_share(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if df.empty:
        return df
    query_norm = _canonical_company_text(query)
    exact_match = df[df["name"].astype(str).map(_canonical_company_text) == query_norm].copy()
    if not exact_match.empty:
        df = exact_match
    if "name" in df.columns and "우" not in str(query):
        common = df[~df["name"].astype(str).map(_is_preferred_name)].copy()
        if not common.empty:
            df = common
    return df


def _find_company_signal_rows(query: str) -> pd.DataFrame:
    signals = _read_signal_lookup()
    if signals.empty:
        return signals
    q = str(query or "").strip()
    if not q:
        return pd.DataFrame()
    code = normalize_code(q)
    if code.isdigit() or q.upper() == code:
        hit = signals[signals["code"] == code].copy()
        if not hit.empty:
            return hit
    text = _canonical_company_text(q)
    if not text:
        return pd.DataFrame()
    names = signals["name"].astype(str).map(_canonical_company_text)
    hit = signals[names.str.contains(re.escape(text), na=False)].copy()
    if not hit.empty:
        hit = _prefer_common_share(hit, q)
        return hit.sort_values(["code"], ascending=[True])
    return pd.DataFrame()


def _find_company_price_rows(query: str) -> pd.DataFrame:
    prices = _read_price_snapshot()
    if prices.empty:
        return prices
    q = str(query or "").strip()
    if not q:
        return pd.DataFrame()
    code = normalize_code(q)
    if code.isdigit() or q.upper() == code:
        hit = prices[prices["code"] == code].copy()
        if not hit.empty:
            return hit
    text = _canonical_company_text(q)
    if not text:
        return pd.DataFrame()
    names = prices["name"].astype(str).map(_canonical_company_text)
    hit = prices[names.str.contains(re.escape(text), na=False)].copy()
    return _prefer_common_share(hit, q)


def _exclude_securities_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "code" not in df.columns:
        return df
    excluded_codes = {normalize_code(code) for code in EXCLUDED_SECURITIES}
    work = df.copy()
    work["code"] = work["code"].astype(str).map(normalize_code)
    return work[~work["code"].isin(excluded_codes)].copy()


def _signal_display_df() -> pd.DataFrame:
    df = _read_signal_latest()
    if df.empty:
        return df
    display = _exclude_securities_df(df)
    if display.empty:
        return display
    display["display_signal"] = display.apply(
        lambda row: _display_signal(row.get("signal"), row.get("conviction_score"), row.get("risk_flag")),
        axis=1,
    )
    display["signal_rank"] = display["display_signal"].map(_signal_sort_key)
    display["signal_ko"] = display["display_signal"].map(_signal_label)
    return display.sort_values(["signal_rank", "code"], ascending=[True, True]).reset_index(drop=True)


def _real_holding_codes(chat_id: str) -> set[str]:
    if not str(chat_id or "").strip():
        return set()
    snap = portfolio_snapshot(chat_id)
    if snap.empty:
        return set()
    return set(snap["code"].astype(str).map(normalize_code))


def _operational_signal_df(chat_id: str = "") -> pd.DataFrame:
    df = _signal_display_df()
    if df.empty:
        return df
    held_codes = _real_holding_codes(chat_id)
    df = df.copy()
    df["is_real_holding"] = df["code"].astype(str).map(normalize_code).isin(held_codes)
    if held_codes:
        df = df[df["is_real_holding"] | df["display_signal"].isin(["BUY", "BUY_WATCH"])].copy()
    else:
        df = df[df["display_signal"].isin(["BUY", "BUY_WATCH"])].copy()
    return df.sort_values(["signal_rank", "is_real_holding", "code"], ascending=[True, False, True]).reset_index(drop=True)


def _decision_latest_row() -> pd.Series | None:
    decision = _read_decision_latest()
    if decision.empty:
        return None
    frame = decision.copy()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame.sort_values("date").iloc[-1]


def _market_session_open(now: datetime | None = None) -> bool:
    return _is_execution_window(now)


def _current_price_info(code: str) -> tuple[str, str, str]:
    norm = normalize_code(code)
    prices = _read_price_snapshot()
    if not prices.empty:
        hit = prices[prices["code"] == norm]
        if not hit.empty:
            row = hit.iloc[-1]
            basis = "n/a"
            if pd.notna(row.get("date")):
                basis = str(pd.to_datetime(row.get("date"), errors="coerce").date())
            return ("반영가", _fmt_num(row.get("close"), "원"), basis)
    return ("반영가", "n/a", "n/a")


def help_text() -> str:
    return "\n".join(
        [
            "[상태 조회]",
            "/status",
            "/health",
            "/latest",
            "/eval",
            "/regime",
            "/report",
            "",
            "[실보유 관리]",
            "/portfolio",
            "/myeval",
            "/mytrades",
            "/note",
            "/notecancel",
            "",
            "[시스템]",
            "/refreshinc",
            "/refreshfull",
            "/streamliton",
            "/streamlitoff",
            "/bridgeoff",
            "yes / no",
            "",
            "[입력 예시]",
            "매수 005930 70000 10",
            "매도 005930 73000 5",
            "/note",
            "신영증권 가격규칙 확인 필요",
            "005930 왜 HOLD야?",
            "삼성전자 정보",
            "증분최신화",
            "전체증분최신화",
        ]
    )


def latest_signals_text(signal_filter: str | None = None, chat_id: str = "") -> str:
    df = _operational_signal_df(chat_id)
    if df.empty:
        return "실운영 기준으로 표시할 최신 전략 신호가 없습니다."
    if signal_filter:
        if signal_filter == "WATCH":
            df = df[df["display_signal"].isin(["BUY_WATCH"])]
        elif signal_filter == "SELL":
            df = df[df["display_signal"].isin(["SELL_WATCH", "SELL"])]
        else:
            df = df[df["display_signal"] == signal_filter]
    if df.empty:
        return "실운영 기준으로 해당 조건의 최신 전략 신호가 없습니다."
    optimal_ma = _read_optimal_ma_snapshot()
    if not optimal_ma.empty:
        df = df.merge(
            optimal_ma[["code", "optimal_ma_ok"]],
            on="code",
            how="left",
        )
    execution_window = _is_execution_window()
    lines = [f"V2 실운영 최신 의사결정 ({'장중 실행형' if execution_window else '장후 익일후보형'})"]
    counts = df["display_signal"].fillna("").astype(str).str.upper().value_counts().to_dict()
    lines.append(f"- {_signal_distribution_text(counts, execution_window=execution_window)}")
    for _, row in df.head(12).iterrows():
        signal_value = row.get("display_signal", row.get("signal"))
        ma_alignment = optimal_ma_alignment(signal_value, row.get("optimal_ma_ok"))
        action_text = _current_action_text(signal_value, execution_window=execution_window)
        reason_text = _brief_reason_text(row)
        v2_text = _v2_timing_summary_text(row)
        next_text = _next_review_text(execution_window=execution_window)
        lines.append(
            f"- {_signal_label(signal_value, execution_window=execution_window)} | {row['code']} {row['name']} | 최적MA {ma_alignment} | V2 {v2_text} | 지금 행동: {action_text} | 이유: {reason_text} | 다음 판단: {next_text}"
        )
    lines.extend(["", *_execution_state_lines()])
    return "\n".join(lines)


def early_session_brief_text(slot_label: str = "", chat_id: str = "") -> str:
    df = _operational_signal_df(chat_id)
    execution_window = True
    header = "[장초반 대응]"
    if slot_label:
        header = f"[장초반 대응 {slot_label}]"
    if df.empty:
        return "\n".join([header, "- 최신 전략 신호가 없습니다."])

    focus = df[df["display_signal"].isin(["BUY", "BUY_WATCH", "HOLD", "SELL_WATCH", "SELL"])].copy()
    if focus.empty:
        focus = df.copy()

    counts = focus["display_signal"].fillna("").astype(str).str.upper().value_counts().to_dict()
    lines = [
        header,
        f"- {_signal_distribution_text(counts, execution_window=execution_window)}",
    ]
    def _row_lines(row: pd.Series) -> list[str]:
        code = normalize_code(row.get("code"))
        price_label, price_value, price_basis = _current_price_info(code)
        signal_value = row.get("display_signal", row.get("signal"))
        action_text = _current_action_text(signal_value, execution_window=execution_window)
        reason_text = _brief_reason_text(row)
        v2_text = _v2_timing_summary_text(row)
        return [
            f"- {row['code']} {row['name']} | {_signal_label(signal_value, execution_window=execution_window)} | {price_label} {price_value}({price_basis}) | 현재 행동: {action_text}",
            f"  V2: {v2_text}",
            f"  사유: {reason_text}",
        ]

    sections = [
        ("[매수/관심 후보]", focus[focus["display_signal"].isin(["BUY", "BUY_WATCH", "WATCH"])]),
        ("[보유 점검]", focus[focus["display_signal"].isin(["HOLD"])]),
        ("[매도/경고]", focus[focus["display_signal"].isin(["SELL_WATCH", "SELL"])]),
    ]
    for title, section_df in sections:
        if section_df.empty:
            continue
        lines.extend(["", title])
        for _, row in section_df.iterrows():
            lines.extend(_row_lines(row))
    lines.extend(["", *_execution_state_lines()])
    return "\n".join(lines)


def tomorrow_plan_text(chat_id: str = "") -> str:
    return "\n".join(
        [
            "`/tomorrow`는 `/latest`로 통합되었습니다.",
            "",
            latest_signals_text(chat_id=chat_id),
        ]
    )


def _held_strategy_status_text(chat_id: str) -> str:
    snap = portfolio_snapshot(chat_id)
    if snap.empty:
        return "실보유 종목 없음"
    counts = snap.get("signal", pd.Series(dtype=str)).fillna("").astype(str).str.upper().value_counts().to_dict()
    execution_window = _is_execution_window()
    return "\n".join(
        [
            f"- 실보유 종목 수: {len(snap)}",
            f"- {_signal_distribution_text(counts, execution_window=execution_window)}",
            "- 기준 전략: 월봉매수 / 주봉매도 / buy_0%__sell_-5%",
        ]
    )


def latest_status_text(chat_id: str) -> str:
    snapshot = _runtime_data_snapshot()
    decision = _decision_latest_row()
    signal_df = _operational_signal_df(chat_id)
    counts = signal_df["display_signal"].value_counts().to_dict() if not signal_df.empty else {}
    execution_window = _is_execution_window()
    lines = ["[실보유 현재평가]", portfolio_status_line(chat_id), "", "[실보유 종목 V2 평가]", _held_strategy_status_text(chat_id), "", "[V2 전략 현재상태]"]
    lines.extend(
        [
            f"- 최신 신호일: {snapshot['signal_date']}",
            f"- 시장 상태: {_market_state_label(decision.get('market_regime', '-'))}" if decision is not None else "- 시장 상태: -",
            (
                f"- 운용강도: {_operating_intensity_label(decision.get('exposure', 0.0))} "
                f"(노출 {float(decision.get('exposure', 0.0)):.2f})"
            ) if decision is not None else "- 운용강도: -",
            f"- {_signal_distribution_text(counts, execution_window=execution_window)}",
            "",
            "[서비스 상태]",
            *_service_status_lines(),
            "",
            *_execution_state_lines(),
            "",
            *_bridge_state_lines(),
        ]
    )
    return "\n".join(lines)


def myeval_summary_text(chat_id: str) -> str:
    snap = portfolio_snapshot(chat_id)
    if snap.empty:
        return "[실보유 종목 전략평가]\n실보유 종목이 없습니다."
    total_value = pd.to_numeric(snap["market_value"], errors="coerce").sum()
    total_pnl = pd.to_numeric(snap["unrealized_pnl"], errors="coerce").sum()
    counts = snap.get("signal", pd.Series(dtype=str)).fillna("").astype(str).str.upper().value_counts().to_dict()
    execution_window = _is_execution_window()
    lines = [
        "[실보유 종목 V2 평가]",
        f"- 평가금액: {total_value:,.0f}원",
        f"- 평가손익: {total_pnl:,.0f}원",
        f"- 전략상 {_signal_distribution_text(counts, execution_window=execution_window)}",
    ]
    for _, row in snap.head(8).iterrows():
        ret_text = "n/a" if pd.isna(row.get("unrealized_return")) else f"{float(row['unrealized_return']):+.2%}"
        lines.append(
            f"- {row['code']} {row['name']} | 전략신호 {_signal_label(row.get('signal'), execution_window=execution_window)} | 수익률 {ret_text}"
        )
    return "\n".join(lines)


def eval_summary_text(chat_id: str) -> str:
    eval_df = _read_strategy_eval()
    snapshot = _runtime_data_snapshot()
    lines = ["[실보유 현재평가]", portfolio_status_line(chat_id), "", "[V2 전략 전체 백테스트]"]
    if eval_df.empty:
        lines.append("- 전략 성과 파일이 없습니다.")
    else:
        metrics = {str(row["metric"]): row["value"] for _, row in eval_df.iterrows()}
        lines.extend(
            [
                f"- 기간: {metrics.get('date_min', '-')} ~ {metrics.get('date_max', '-')}",
                f"- CAGR: {_fmt_pct(metrics.get('cagr'))}",
                f"- MDD: {_fmt_pct(metrics.get('mdd'))}",
                f"- Sharpe: {float(metrics.get('sharpe')):.2f}" if metrics.get("sharpe") is not None else "- Sharpe: n/a",
                f"- 승률: {_fmt_pct(metrics.get('win_rate'))}",
                f"- 종료 거래 수: {_fmt_num(metrics.get('num_closed_trades'))}",
                f"- 미청산 포지션 수: {_fmt_num(metrics.get('num_open_trades'))}",
                f"- 평균 보유일: {float(metrics.get('avg_holding_days')):.2f}일" if metrics.get("avg_holding_days") is not None else "- 평균 보유일: n/a",
                f"- 최신 신호일: {snapshot['signal_date']}",
            ]
        )
    return "\n".join(lines)


def regime_explain_text() -> str:
    decision = _decision_latest_row()
    if decision is None:
        return "시장 상태를 설명할 최신 의사결정 데이터가 없습니다."
    regime = str(decision.get("market_regime", "-"))
    exposure = float(decision.get("exposure", 0.0))
    target_positions = int(float(decision.get("target_positions", 0)))
    meanings = {
        "risk_on": "위험 신호 0개 기준의 정상구간이라 기본 운용 강도를 유지하는 상태입니다.",
        "neutral": "위험 신호 1개 기준의 주의구간이라 선별 진입과 보수적 운용이 필요한 상태입니다.",
        "risk_off": "위험 신호 2개 기준의 방어구간입니다. V2에서는 하드 매수금지보다 운용강도를 낮춰 대응합니다.",
        "unknown": "같은 날짜의 매크로 레짐이 아직 붙지 않아 판단 불가 상태입니다.",
    }
    return "\n".join(
        [
            f"시장 상태: {_market_state_label(regime)}",
            f"- 설명: {meanings.get(regime, '정의되지 않은 상태입니다.')}",
            f"- 운용강도: {_operating_intensity_label(exposure)} (노출 {exposure:.2f})",
            f"- 목표 포지션 수: {target_positions}",
        ]
    )


def why_no_buy_text() -> str:
    decision = _decision_latest_row()
    signal_df = _operational_signal_df("")
    if signal_df.empty:
        return "최신 전략 신호가 없어 매수 부재 이유를 설명할 수 없습니다."
    buy_count = int((signal_df["signal"] == "BUY").sum())
    if buy_count > 0:
        return latest_signals_text("BUY")
    watch = signal_df[signal_df["signal"].isin(["WATCH", "BUY_WATCH"])].head(5)
    execution_window = _is_execution_window()
    lines = [f"V2 기준 현재 {_signal_label('BUY', execution_window=execution_window)}가 없는 이유입니다."]
    if decision is not None:
        lines.append(f"- 시장 상태: {_market_state_label(decision.get('market_regime', '-'))}")
        lines.append(
            f"- 운용강도: {_operating_intensity_label(decision.get('exposure', 0.0))} "
            f"(노출 {float(decision.get('exposure', 0.0)):.2f})"
        )
        lines.append(f"- 목표 포지션 수: {int(float(decision.get('target_positions', 0)))}")
    if not watch.empty:
        lines.append("- 대신 상위 관심 종목은 아래와 같습니다.")
        for _, row in watch.iterrows():
            lines.append(f"  - {row['code']} {row['name']} | {_signal_label(row['signal'], execution_window=execution_window)}")
    return "\n".join(lines)


def recent_trades_text(limit: int = 10) -> str:
    trades = _read_trade_log()
    if trades.empty:
        return "V2 전략 거래 기록이 없습니다."
    trades = trades.sort_values("entry_date", ascending=False).head(limit)
    lines = ["V2 전략 최근 거래", "- CLOSED: 전략상 청산 완료", "- OPEN: 아직 미청산 상태"]
    for _, row in trades.iterrows():
        reason = str(row.get("exit_reason") or "")
        reason_label = EXIT_REASON_LABELS.get(reason, reason or "-")
        reason_desc = EXIT_REASON_DESCRIPTIONS.get(reason, "")
        exit_date = row.get("exit_date") if pd.notna(row.get("exit_date")) else "미청산"
        ret_text = _fmt_pct(row.get("realized_return"))
        lines.append(
            f"- {row['status']} | {row['code']} {row['name']} | {row['entry_date']} -> {exit_date} | 수익률 {ret_text} | 사유 {reason_label}{' - ' + reason_desc if reason_desc else ''}"
        )
    return "\n".join(lines)


def recent_alerts_text(limit: int = 10) -> str:
    alerts = _read_alert_log()
    if alerts.empty:
        return "최근 알림 기록이 없습니다."
    view = alerts.sort_values("created_at", ascending=False).head(limit)
    lines = ["최근 알림"]
    for _, row in view.iterrows():
        name = str(row.get("name") or row.get("code") or "-")
        lines.append(
            f"- {row.get('created_at', '-')} | {row.get('channel', '-')} | {name} | {row.get('signal', '-')} | {'성공' if bool(row.get('sent')) else '실패'}"
        )
    return "\n".join(lines)


def data_health_text() -> str:
    snapshot = _runtime_data_snapshot()
    lines = [
        "데이터 최신 상태",
        f"- 주가 최신일: {snapshot['price_date']}",
        f"- feature 최신일: {snapshot['feature_date']}",
        f"- 매크로 최신일: {snapshot['macro_date']}",
        f"- 재무 최신일: {snapshot['fundamental_date']}",
        f"- 최신 신호일: {snapshot['signal_date']}",
        "",
        "서비스 상태",
        *_service_status_lines(),
        "",
        *_execution_state_lines(),
    ]
    return "\n".join(lines)


def latest_report_text(chat_id: str) -> str:
    decision = _decision_latest_row()
    signal_df = _operational_signal_df(chat_id)
    if decision is None and signal_df.empty:
        return "최신 의사결정 리포트가 없습니다."
    execution_window = _is_execution_window()
    lines = ["오늘의 의사결정"]
    if decision is not None:
        lines.extend(
            [
                f"- 기준일: {pd.to_datetime(decision.get('date'), errors='coerce').date() if pd.notna(decision.get('date')) else '-'}",
                f"- 시장 상태: {_market_state_label(decision.get('market_regime', '-'))}",
                (
                    f"- 운용강도: {_operating_intensity_label(decision.get('exposure', 0.0))} "
                    f"(노출 {float(decision.get('exposure', 0.0)):.2f})"
                ),
                f"- 목표 포지션 수: {int(float(decision.get('target_positions', 0)))}",
            ]
        )
    if not signal_df.empty:
        counts = signal_df["display_signal"].value_counts().to_dict()
        lines.append(f"- 신호 분포: {_signal_distribution_text(counts, execution_window=execution_window)}")
        for _, row in signal_df.head(5).iterrows():
            lines.append(f"  - {_signal_label(row['display_signal'], execution_window=execution_window)} | {row['code']} {row['name']}")
    lines.extend(["", "실보유 상태", portfolio_status_line(chat_id)])
    return "\n".join(lines)


def _company_match_text(query: str) -> str:
    excluded = _excluded_security_text(query)
    if excluded:
        return excluded
    price_hits = _find_company_price_rows(query)
    signal_hits = _find_company_signal_rows(query)
    if price_hits.empty and signal_hits.empty:
        return ""
    if not price_hits.empty and len(_prefer_common_share(price_hits, query).head(1)) == 1:
        return signal_detail_text(str(_prefer_common_share(price_hits, query).iloc[0]["code"]))
    hits = signal_hits if not signal_hits.empty else price_hits
    if len(hits) == 1:
        return signal_detail_text(str(hits.iloc[0]["code"]))
    execution_window = _is_execution_window()
    choices = []
    for _, row in hits.head(5).iterrows():
        signal_text = ""
        if pd.notna(row.get("signal")) and str(row.get("signal")).strip():
            signal_text = f" | {_signal_label(row.get('signal', '-'), execution_window=execution_window)}"
        choices.append(f"- {row['code']} {row['name']}{signal_text}")
    return "\n".join(["이름이 비슷한 종목이 여러 개 있습니다. 6자리 종목코드로 다시 요청해 주세요.", *choices])


def signal_detail_text(identifier: str, chat_id: str = "") -> str:
    excluded = _excluded_security_text(identifier)
    if excluded:
        return excluded
    execution_window = _is_execution_window()
    price_hits = _find_company_price_rows(identifier)
    signal_hits = _find_company_signal_rows(identifier)
    if price_hits.empty and signal_hits.empty:
        return "해당 종목을 찾지 못했습니다. 6자리 종목코드 또는 정확한 종목명으로 다시 요청해 주세요."

    if not price_hits.empty:
        base = _prefer_common_share(price_hits, identifier).head(1).copy()
    else:
        base = _prefer_common_share(signal_hits, identifier).head(1).copy()
    row = base.iloc[0].copy()
    code = normalize_code(str(row["code"]))

    feature_snapshot = _read_feature_snapshot()
    optimal_ma_snapshot = _read_optimal_ma_snapshot()
    feature_row = feature_snapshot[feature_snapshot["code"] == code].head(1).copy() if not feature_snapshot.empty else pd.DataFrame()
    optimal_ma_row = optimal_ma_snapshot[optimal_ma_snapshot["code"] == code].head(1).copy() if not optimal_ma_snapshot.empty else pd.DataFrame()
    signal_row = signal_hits[signal_hits["code"] == code].head(1).copy() if not signal_hits.empty else pd.DataFrame()
    if signal_row.empty and feature_row.empty:
        return _out_of_universe_text(code, str(row.get("name", code)))
    if not signal_row.empty:
        for col in signal_row.columns:
            row[col] = signal_row.iloc[0][col]

    if not feature_row.empty:
        frow = feature_row.iloc[0]
        row["industry"] = frow.get("industry", row.get("industry", pd.NA))
        if pd.isna(row.get("conviction_score")):
            row["conviction_score"] = float("nan")
        for col in ["ma_day_20", "week_10_ma", "month_10_ma", "weekly_aux_ok", "monthly_main_ok"]:
            if pd.isna(row.get(col)) or row.get(col) is None:
                row[col] = frow.get(col)
    if not optimal_ma_row.empty:
        for col in optimal_ma_row.columns:
            if col != "code":
                row[col] = optimal_ma_row.iloc[0][col]
    row["display_signal"] = _display_signal(row.get("signal"), row.get("conviction_score"), row.get("risk_flag"))
    decision = _decision_latest_row()

    price_label, price_value, price_basis = _current_price_info(code)
    basis_numeric = None
    basis_label = "전일종가"
    basis_date = "n/a"
    if not price_hits.empty and pd.notna(price_hits.iloc[0].get("close")):
        basis_numeric = float(price_hits.iloc[0]["close"])
        if pd.notna(price_hits.iloc[0].get("date")):
            basis_date = str(pd.to_datetime(price_hits.iloc[0].get("date"), errors="coerce").date())
    basis_text = f"{basis_date} 전일종가" if basis_date != "n/a" else "전일종가"
    op_margin = _extract_metric_from_reasons(row, "영업이익률")
    net_margin = _extract_metric_from_reasons(row, "순이익률")
    op_qoq = _extract_metric_from_reasons(row, "영업이익 QoQ")
    if not feature_row.empty:
        frow = feature_row.iloc[0]
        if op_margin == "n/a" and pd.notna(frow.get("op_margin_pti")):
            op_margin = _fmt_pct(frow.get("op_margin_pti"))
        if net_margin == "n/a" and pd.notna(frow.get("net_margin_pti")):
            net_margin = _fmt_pct(frow.get("net_margin_pti"))
        if op_qoq == "n/a":
            if pd.notna(frow.get("op_income_qoq_pti")):
                op_qoq = _fmt_num(frow.get("op_income_qoq_pti"), "원")
            elif pd.notna(frow.get("op_income_qoq_period")):
                op_qoq = _fmt_num(frow.get("op_income_qoq_period"), "원")
    if op_qoq == "n/a":
        op_qoq = _extract_metric_from_reasons(row, "순이익 QoQ")
    risk_flag = _prettify_risk_flag(row.get("risk_flag")) or "없음"
    stop_rule = _display_text(row.get("stop_rule"), "없음")
    exit_rule = _display_text(row.get("target_exit_rule"), "없음")
    fast_positions = _read_fast_positions()
    entry_price = None
    held_snap = portfolio_snapshot(chat_id) if chat_id else pd.DataFrame()
    if not held_snap.empty:
        held_hit = held_snap[held_snap["code"] == code]
        if not held_hit.empty and pd.notna(held_hit.iloc[-1].get("avg_price")):
            entry_price = float(held_hit.iloc[-1]["avg_price"])
            row["entry_price"] = entry_price
    if not fast_positions.empty:
        pos = fast_positions[fast_positions["code"] == code]
        if entry_price is None and not pos.empty and pd.notna(pos.iloc[-1].get("entry_price")):
            entry_price = float(pos.iloc[-1]["entry_price"])
            row["entry_price"] = entry_price
    action_guide = _price_action_guide(row, current_price=basis_numeric, current_basis=basis_text)
    quarter_text = "n/a"
    filing_text = "n/a"
    if not feature_row.empty:
        quarter_text = _quarter_label(feature_row.iloc[0].get("fiscal_year_pti"), feature_row.iloc[0].get("reprt_code_pti"))
        filing_value = pd.to_datetime(feature_row.iloc[0].get("filing_date_pti"), errors="coerce")
        if pd.notna(filing_value):
            filing_text = str(filing_value.date())
    current_action = _current_action_text(row.get("display_signal"), execution_window=execution_window)
    next_review = _next_review_text(execution_window=execution_window)
    reason_text = _brief_reason_text(row)
    market_regime = row.get("market_regime")
    if pd.isna(market_regime) or not str(market_regime).strip():
        market_regime = decision.get("market_regime") if decision is not None else "-"
    exposure_value = row.get("market_exposure")
    if pd.isna(pd.to_numeric(pd.Series([exposure_value]), errors="coerce").iloc[0]):
        exposure_value = row.get("exposure")
    if pd.isna(pd.to_numeric(pd.Series([exposure_value]), errors="coerce").iloc[0]):
        exposure_value = decision.get("exposure") if decision is not None else float("nan")
    usdkrw = pd.to_numeric(pd.Series([row.get("usdkrw")]), errors="coerce").iloc[0]
    vix = pd.to_numeric(pd.Series([row.get("vix")]), errors="coerce").iloc[0]
    macro_parts = [f"{_market_state_label(market_regime)} / 운용강도 {_operating_intensity_label(exposure_value)}"]
    if pd.notna(usdkrw):
        macro_parts.append(f"환율 {usdkrw:,.0f}")
    if pd.notna(vix):
        macro_parts.append(f"VIX {vix:.1f}")
    price_axis_head = "관심 유지 / 추격 금지" if str(row.get("display_signal", "")).upper() in {"BUY", "BUY_WATCH", "WATCH"} else "보유 관리 / 방어선 점검"
    financial_summary = f"{quarter_text} · {filing_text} | 영업이익률 {op_margin} | 영업이익 QoQ {op_qoq}"
    lines = [
        f"[종목] {code} {row.get('name', code)}",
        f"- 현재 의사결정: {_signal_label(row.get('display_signal', 'n/a'), execution_window=execution_window)}",
        f"- 지금 행동: {current_action}",
        f"- 이유: {reason_text}",
        f"- 다음 판단: {next_review}",
        "",
        "[4축 의견]",
        f"- 최적 MA: {_v2_timing_summary_text(row)}",
        f"- 주가 위치: {price_axis_head} | {price_label} {price_value}({price_basis})",
        f"- 재무: {financial_summary}",
        f"- 매크로: {' | '.join(macro_parts)}",
        "",
        "[실행 가이드]",
        f"- {action_guide}",
        "",
        "[추가 정보]",
        f"- 업종: {row.get('industry', 'n/a')}",
        f"- 순이익률: {net_margin}",
        f"- 리스크: {risk_flag}",
        f"- 손절 규칙: {stop_rule}",
        f"- 청산 규칙: {exit_rule}",
        f"- 근거 분기: {quarter_text}",
        f"- 공시일: {filing_text}",
    ]
    holding = position_detail_line(chat_id, code) if chat_id else None
    if holding:
        lines.append(f"- 실보유 상태: {holding}")
    reasons = [str(row.get(col) or "") for col in ["reason_1", "reason_2", "reason_3"] if str(row.get(col) or "").strip()]
    if reasons:
        lines.append("- 근거: " + " / ".join(reasons))
    return "\n".join(lines)


def unhandled_requests_text(chat_id: str, limit: int = 8) -> str:
    rows = load_recent_unhandled(UNHANDLED_PATH, str(chat_id), limit)
    if not rows:
        return "최근 미처리 요청이 없습니다."
    lines = ["최근 미처리 요청"]
    for row in reversed(rows):
        lines.append(f"- {row.get('created_at', '-')} | {row.get('text', '')} | {row.get('reason', '-')}")
    return "\n".join(lines)


def record_manual_trade_text(chat_id: str, side: str, code: str, quantity: str, price: str) -> str:
    parsed = ParsedTrade(side=str(side).upper(), code=normalize_code(code), quantity=float(quantity), price=float(price))
    return record_manual_trade(chat_id, parsed)


def read_log_tail(path: Path, max_lines: int = 20) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def build_job_spec(action: str) -> JobSpec | None:
    python_cmd = [sys.executable, "-m", "new_strategy.run_signal_pipeline"]
    if action == "run_fast_alert":
        return JobSpec(
            action=action,
            summary="fast alert를 다시 계산하고 텔레그램 알림까지 발송합니다.",
            command=python_cmd + ["--fast-alerts", "--send-alerts"],
        )
    if action == "run_refresh_data":
        return JobSpec(
            action=action,
            summary="주가를 키움 우선 기준으로 증분 최신화한 뒤 fast alert와 알림을 다시 실행합니다.",
            command=python_cmd + ["--refresh-data", "--prefer-kiwoom-eod", "--fast-alerts", "--send-alerts"],
        )
    if action == "run_refresh_incremental":
        return JobSpec(
            action=action,
            summary="주가를 키움 우선 기준으로 증분 최신화한 뒤 fast alert와 알림을 다시 실행합니다.",
            command=python_cmd + ["--refresh-data", "--prefer-kiwoom-eod", "--fast-alerts", "--send-alerts"],
        )
    if action == "run_refresh_full":
        return JobSpec(
            action=action,
            summary="주가를 키움 우선 기준으로, 매크로·금과 함께 전체 증분 최신화한 뒤 fast alert와 알림을 다시 실행합니다.",
            command=python_cmd + ["--refresh-data", "--refresh-macro", "--refresh-gold", "--prefer-kiwoom-eod", "--fast-alerts", "--send-alerts"],
        )
    if action == "run_refresh_full_incremental":
        return JobSpec(
            action=action,
            summary="주가를 키움 우선 기준으로, 매크로·금과 함께 전체 증분 최신화한 뒤 fast alert와 알림을 다시 실행합니다.",
            command=python_cmd + ["--refresh-data", "--refresh-macro", "--refresh-gold", "--prefer-kiwoom-eod", "--fast-alerts", "--send-alerts"],
        )
    if action == "run_streamlit_on":
        return JobSpec(
            action=action,
            summary="스트림릿 대시보드를 다시 실행합니다.",
            command=["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(STREAMLIT_START_SCRIPT)],
        )
    if action == "run_streamlit_off":
        return JobSpec(
            action=action,
            summary="스트림릿 대시보드를 종료합니다.",
            command=["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(STREAMLIT_STOP_SCRIPT)],
        )
    if action == "run_bridge_off":
        return JobSpec(action=action, summary="텔레그램 브리지를 종료합니다.", command=[], require_confirm=True)
    return None


def start_job(job_spec: JobSpec, log_path: Path) -> tuple[subprocess.Popen[str], TextIO]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("w", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        job_spec.command,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(REPO_ROOT),
        creationflags=creationflags,
    )
    return proc, log_handle


def _is_help_or_noise(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return True
    lowered = raw.lower()
    if lowered in {"/help", "help", "hi", "hello"}:
        return True
    if raw in {"안녕", "안녕하세요", "반가워", "반가워요", "?", "??", "...", "ㅋㅋ", "ㅎㅎ"}:
        return True
    if NOISE_RE.fullmatch(raw):
        return True
    if SHORT_NOISE_RE.fullmatch(raw):
        return True
    return False


def local_chat_reply_ex(text: str, chat_id: str) -> LocalReply:
    raw = str(text or "").strip()
    if _is_help_or_noise(raw):
        return LocalReply(help_text(), True)

    if CODE_RE.search(raw):
        return LocalReply(signal_detail_text(CODE_RE.search(raw).group(1), chat_id), True)

    if any(keyword in raw for keyword in ["정보", "주가", "신호", "엘지디스플레이", "셀트리온", "삼성전자"]):
        company_text = _company_match_text(raw)
        if company_text:
            return LocalReply(company_text, True)

    if any(keyword in raw for keyword in ["최신일", "데이터 최신", "데이터 상태"]):
        return LocalReply(data_health_text(), True)
    if any(keyword in raw for keyword in ["스트림릿 안", "대시보드 안"]):
        return LocalReply("스트림릿 상태를 먼저 확인합니다.\n\n" + "\n".join(_service_status_lines()) + "\n\n필요하면 /streamliton 또는 /streamlitoff 를 사용하세요.", True)
    if any(keyword in raw.lower() for keyword in ["ip", "링크", "주소"]):
        return LocalReply("외부 공유는 현재 Tailscale 기준입니다. 대시보드 사이드바의 서비스 상태와 저장된 안내문 파일을 확인하세요.", True)

    fallback = "\n".join(
        [
            "현재 바로 처리할 수 있는 명령이 아닙니다.",
            "그래도 아래 명령으로 대부분의 상태를 확인할 수 있습니다.",
            "",
            help_text(),
        ]
    )
    return LocalReply(fallback, False)
