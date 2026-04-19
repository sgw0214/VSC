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
from PIL import Image, ImageDraw, ImageFont

from new_strategy.earnings_signal_engine import EarningsStrategyConfig
from new_strategy.optimal_ma_publish_contract import OPTIMAL_MA_ALL_SELECTION_PATH
from new_strategy.paths import data_path, output_path, strategy_output_path
from new_strategy.price_latest_snapshot import read_price_latest_snapshot
from new_strategy.price_level_map import build_price_level_map, DEFAULT_MA_STOP_PCT
from new_strategy.v2_ma_contract import (
    normalize_v2_ma_frame,
    normalize_v2_mode_contract_frame,
    v2_mode_contract_context,
)
from new_strategy.optimal_ma_overlay import load_latest_optimal_ma_snapshot
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
PRICE_PANEL_PATH = data_path("price_panel.csv")
BEST_MODE_BY_STOCK_PATH = output_path("v2_four_timing_mode_grid", "best_mode_by_stock_full.csv")
UNHANDLED_PATH = BRIDGE_DIR / "telegram_bridge_unhandled_log.csv"
NOTES_PATH = BRIDGE_DIR / "telegram_bridge_notes.csv"
BRIDGE_STATE_PATH = BRIDGE_DIR / "telegram_bridge_state.json"
BRIEF_IMAGE_DIR = BRIDGE_DIR / "briefings"
EXECUTION_SNAPSHOT_PATH = APP_DIR / "dashboard_operational_execution_snapshot.csv"
POSTCLOSE_SNAPSHOT_PATH = APP_DIR / "dashboard_operational_postclose_snapshot.csv"
FRAME_CACHE: dict[str, tuple[tuple[int, int], pd.DataFrame]] = {}
INTRADAY_RECALC_MINUTES = 30
DEFAULT_FIXED_STOP_LOSS = EarningsStrategyConfig().fixed_stop_loss
DEFAULT_MA_STOP_LOSS = DEFAULT_MA_STOP_PCT
WINDOWS_FONT_REG = Path(r"C:\Windows\Fonts\malgun.ttf")
WINDOWS_FONT_BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")

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
SIGNAL_ORDER = {"BUY": 0, "BUY_WATCH": 1, "HOLD": 2, "WATCH": 3, "SELL_WATCH": 4, "SELL": 5}
SIGNAL_RESOLUTION_ORDER = {"SELL": 0, "BUY": 1, "SELL_WATCH": 2, "BUY_WATCH": 3, "WATCH": 4, "HOLD": 5}
EXIT_REASON_LABELS = {
    "timing_break": "타이밍 훼손",
    "stop_loss": "손절",
    "quality_drop": "품질 저하",
    "signal_sell": "매도 신호 전환",
}
EXIT_REASON_DESCRIPTIONS = {
    "timing_break": "단기 타이밍 보조 조건이 깨져 청산했습니다.",
    "stop_loss": "손절 기준에 도달해 청산했습니다.",
    "quality_drop": "핵심 실적 또는 품질 조건이 약해져 청산했습니다.",
    "signal_sell": "전략 신호가 매도로 전환되어 청산했습니다.",
}


def _numeric_series_or_na(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric Series for a column, or an aligned NaN Series.

    This is intentionally strict about always returning a Series. The fast
    briefing renderer previously used `DataFrame.get()` and implicitly assumed
    the result would always be a Series, which broke when a column was absent.
    """
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(pd.NA, index=frame.index, dtype="Float64")

RISK_FLAG_LABELS = {
    "macro_risk_off": "매크로 위험장",
    "high_volatility": "고변동성",
    "earnings_exception": "실적 예외",
    "sell_watch": "매도경계",
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
    stat = path.stat()
    cache_token = (int(stat.st_mtime_ns), int(stat.st_size))
    cached = FRAME_CACHE.get(key)
    if cached and cached[0] == cache_token:
        return cached[1].copy()
    df = pd.read_csv(path, low_memory=False, **kwargs)
    FRAME_CACHE[key] = (cache_token, df)
    return df.copy()


def _read_best_mode_contract() -> pd.DataFrame:
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
    df = _read_csv_cached(BEST_MODE_BY_STOCK_PATH, dtype={"code": str})
    if df.empty:
        return pd.DataFrame(columns=columns)
    df["code"] = df["code"].astype(str).map(normalize_code)
    df = normalize_v2_mode_contract_frame(df)
    return df[columns].drop_duplicates(subset=["code"], keep="last").reset_index(drop=True)


def _merge_best_mode_contract(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    contract = _read_best_mode_contract()
    if contract.empty:
        return df.copy()
    work = df.copy()
    work["code"] = work["code"].astype(str).map(normalize_code)
    merged = work.merge(contract, on="code", how="left", suffixes=("", "_contract"))
    for col in [column for column in contract.columns if column != "code"]:
        aux = f"{col}_contract"
        if aux not in merged.columns:
            continue
        if col in merged.columns:
            merged[col] = merged[col].combine_first(merged[aux])
        else:
            merged[col] = merged[aux]
        merged = merged.drop(columns=[aux])
    return normalize_v2_mode_contract_frame(merged)


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


def _fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):+.2%}"


def _fmt_num(value: Any, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):,.0f}{suffix}"


def _fmt_num_plain(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.0f}"


def _display_text(value: Any, default: str = "없음") -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _safe_bool(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"", "0", "false", "no", "n", "off", "none", "nan"}:
            return False
        if text in {"1", "true", "yes", "y", "on"}:
            return True
    return bool(value)


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
    if not raw or raw.lower() in {"nan", "none", "null"}:
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
    contract = v2_mode_contract_context(row)
    parts: list[str] = []
    if contract.get("mode_label"):
        parts.append(str(contract["mode_label"]))
    buy_text = _contract_action_text(contract, "buy")
    sell_text = _contract_action_text(contract, "sell")
    if buy_text:
        parts.append(buy_text)
    if sell_text:
        parts.append(sell_text)
    return " / ".join(parts) if parts else "V2 타이밍 데이터 없음"


def _v2_timing_detail_lines(row: pd.Series | dict[str, Any]) -> list[str]:
    contract = v2_mode_contract_context(row)
    lines: list[str] = []
    if contract.get("mode_label"):
        lines.append(f"- 최적 MA 계약: {contract['mode_label']}")
    buy_text = _contract_action_text(contract, "buy", detailed=True)
    sell_text = _contract_action_text(contract, "sell", detailed=True)
    if buy_text:
        lines.append(f"- {buy_text}")
    if sell_text:
        lines.append(f"- {sell_text}")
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
        pct = float(text) / 100.0
    except Exception:
        return None
    return None if pd.isna(pct) else float(pct)


def _non_nan_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _format_live_basis(date_value: Any, quote_time_value: Any) -> str:
    quote_time = pd.to_datetime(quote_time_value, errors="coerce")
    if pd.notna(quote_time):
        return quote_time.strftime("%Y-%m-%d %H:%M:%S")
    date = pd.to_datetime(date_value, errors="coerce")
    if pd.notna(date):
        return f"{date.date()} 실시간"
    return "n/a"


def _latest_weekly_ma_from_price_panel(code: Any, window: int = 10) -> float | None:
    norm = normalize_code(str(code or ""))
    price_path = data_path("price_panel.csv")
    if not norm or not price_path.exists():
        return None
    try:
        df = pd.read_csv(price_path, usecols=["date", "code", "close"], dtype={"code": str}, low_memory=False)
        df = df[df["code"].astype(str).map(normalize_code) == norm].copy()
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
    if _non_nan_float(base.get("v2_week_ma")) is None and _non_nan_float(base.get("week_10_ma")) is None:
        weekly_ma = _latest_weekly_ma_from_price_panel(base.get("code"), window=10)
        if weekly_ma is not None:
            base["week_10_ma"] = weekly_ma
    return base


def _risk_levels(row: pd.Series | dict[str, Any], *, current_price: float | None, entry_price: float | None = None) -> dict[str, float | None]:
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


def _resolve_entry_price(code: str, chat_id: str = "", row: pd.Series | dict[str, Any] | None = None) -> float | None:
    held_snap = portfolio_snapshot(chat_id) if chat_id else pd.DataFrame()
    if not held_snap.empty:
        held_hit = held_snap[held_snap["code"] == code]
        if not held_hit.empty:
            avg_price = _non_nan_float(held_hit.iloc[-1].get("avg_price"))
            if avg_price is not None:
                return avg_price
    if row is not None:
        row_entry = _non_nan_float(row.get("entry_price"))
        if row_entry is not None:
            return row_entry
    fast_positions = _read_fast_positions()
    if not fast_positions.empty:
        pos = fast_positions[fast_positions["code"] == code]
        if not pos.empty:
            fast_entry = _non_nan_float(pos.iloc[-1].get("entry_price"))
            if fast_entry is not None:
                return fast_entry
    return None


def _sell_execution_hint(
    row: pd.Series | dict[str, Any],
    *,
    code: str,
    chat_id: str = "",
    current_price: float | None,
    current_basis: str,
) -> str:
    if current_price is None or pd.isna(current_price):
        return ""
    entry_price = _resolve_entry_price(code, chat_id=chat_id, row=row)
    levels = _risk_levels(row, current_price=float(current_price), entry_price=entry_price)
    parts = [f"제안 매도가 {float(current_price):,.0f}원({current_basis})"]
    if levels["initial_stop"] is not None:
        parts.append(f"매수손절가 {levels['initial_stop']:,.0f}원")
    if levels["weekly_ma_guard"] is not None:
        parts.append(f"주이평손절가 {levels['weekly_ma_guard']:,.0f}원")
    if levels["monthly_ma_guard"] is not None:
        parts.append(f"월이평손절가 {levels['monthly_ma_guard']:,.0f}원")
    return " / ".join(parts)


def _current_action_text(signal: Any, *, execution_window: bool) -> str:
    signal_text = str(signal or "").strip().upper()
    if execution_window:
        mapping = {
            "BUY": "분할 매수 검토",
            "BUY_WATCH": "관심 유지, 강하면 소액매수 검토",
            "WATCH": "관심 유지",
            "HOLD": "보유 유지",
            "SELL_WATCH": "소액매도 우선 검토",
            "SELL": "매도 우선",
        }
    else:
        mapping = {
            "BUY": "익일 매수 준비",
            "BUY_WATCH": "익일 관심 유지, 강하면 소액매수 검토",
            "WATCH": "익일 관심 유지",
            "HOLD": "익일보유 유지",
            "SELL_WATCH": "익일 소액매도 우선 검토",
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
    row = _risk_row_with_fallbacks(row)
    base_guide = _action_guide(row, execution_window=execution_window)
    if current_price is None or pd.isna(current_price):
        return base_guide
    signal = str(row.get("signal") or "").upper()
    parts = [base_guide, f"기준가 {float(current_price):,.0f}원({current_basis})"]
    entry_price = _non_nan_float(row.get("entry_price"))
    levels = _risk_levels(row, current_price=float(current_price), entry_price=entry_price)
    if signal in {"BUY", "WATCH"}:
        parts.append(f"관찰 구간 {float(current_price) * 0.99:,.0f}~{float(current_price) * 1.01:,.0f}원")
        parts.append(f"추격 금지 상단 {float(current_price) * 1.02:,.0f}원")
        if levels["initial_stop"] is not None:
            parts.append(f"진입 후 초기 손절가 {levels['initial_stop']:,.0f}원")
    elif signal in {"SELL", "SELL_WATCH"}:
        parts.append(f"제안 매도가 {float(current_price):,.0f}원")
        if levels["buy_price"] is not None:
            parts.append(f"매수가 {levels['buy_price']:,.0f}원")
        if levels["initial_stop"] is not None:
            parts.append(f"매수손절가 {levels['initial_stop']:,.0f}원")
        if levels["weekly_ma_price"] is not None:
            window_text = f"({int(levels['weekly_window'])}주)" if levels["weekly_window"] is not None else ""
            parts.append(f"주이평가{window_text} {levels['weekly_ma_price']:,.0f}원")
        if levels["weekly_ma_guard"] is not None:
            parts.append(f"주이평손절가 {levels['weekly_ma_guard']:,.0f}원")
        if levels["monthly_ma_price"] is not None:
            window_text = f"({int(levels['monthly_window'])}월)" if levels["monthly_window"] is not None else ""
            parts.append(f"월이평가{window_text} {levels['monthly_ma_price']:,.0f}원")
        if levels["monthly_ma_guard"] is not None:
            parts.append(f"월이평손절가 {levels['monthly_ma_guard']:,.0f}원")
        if levels["breakeven_guard"] is not None:
            parts.append(f"원금 보호선 {levels['breakeven_guard']:,.0f}원")
        parts.append("매도는 제안 매도가 우선이며, 매수손절가·주이평손절가·월이평손절가를 함께 점검합니다.")
    elif signal in {"HOLD"}:
        if levels["buy_price"] is not None:
            parts.append(f"매수가 {levels['buy_price']:,.0f}원")
        if levels["initial_stop"] is not None:
            parts.append(f"매수손절가 {levels['initial_stop']:,.0f}원")
        if levels["weekly_ma_price"] is not None:
            window_text = f"({int(levels['weekly_window'])}주)" if levels["weekly_window"] is not None else ""
            parts.append(f"주이평가{window_text} {levels['weekly_ma_price']:,.0f}원")
        if levels["weekly_ma_guard"] is not None:
            parts.append(f"주이평손절가 {levels['weekly_ma_guard']:,.0f}원")
        if levels["monthly_ma_price"] is not None:
            window_text = f"({int(levels['monthly_window'])}월)" if levels["monthly_window"] is not None else ""
            parts.append(f"월이평가{window_text} {levels['monthly_ma_price']:,.0f}원")
        if levels["monthly_ma_guard"] is not None:
            parts.append(f"월이평손절가 {levels['monthly_ma_guard']:,.0f}원")
        if levels["breakeven_guard"] is not None:
            parts.append(f"원금 보호선 {levels['breakeven_guard']:,.0f}원")
        parts.append("가격 방어는 매수손절가, 주이평손절가, 월이평손절가 순으로 함께 점검합니다.")
    return " / ".join(parts)


def _price_level_lines(code: str, *, current_price: float | None, buy_price: float | None) -> list[str]:
    levels = build_price_level_map(code, buy_price=buy_price, buy_stop_pct=DEFAULT_FIXED_STOP_LOSS, ma_stop_pct=DEFAULT_MA_STOP_LOSS)
    lines: list[str] = []
    if current_price is not None and not pd.isna(current_price):
        lines.append(f"- 기준가: {float(current_price):,.0f}원")
    if levels["buy_price"] is not None:
        lines.append(f"- 매수가: {levels['buy_price']:,.0f}원")
    if levels["buy_stop_price"] is not None:
        lines.append(f"- 매수손절가: {levels['buy_stop_price']:,.0f}원")
    if levels["weekly_ma_price"] is not None:
        window_text = f" ({int(levels['weekly_window'])}주)" if levels["weekly_window"] is not None else ""
        lines.append(f"- 주이평가{window_text}: {levels['weekly_ma_price']:,.0f}원")
    if levels["weekly_ma_stop_price"] is not None:
        lines.append(f"- 주이평손절가: {levels['weekly_ma_stop_price']:,.0f}원")
    if levels["monthly_ma_price"] is not None:
        window_text = f" ({int(levels['monthly_window'])}월)" if levels["monthly_window"] is not None else ""
        lines.append(f"- 월이평가{window_text}: {levels['monthly_ma_price']:,.0f}원")
    if levels["monthly_ma_stop_price"] is not None:
        lines.append(f"- 월이평손절가: {levels['monthly_ma_stop_price']:,.0f}원")
    return lines


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
            "SELL_WATCH": "소액매도 검토가 우선입니다. 약세가 이어지면 절반정리 또는 매도로 강화합니다.",
            "SELL": "실행 가능한 매도 신호입니다. 반등 대기보다 정리를 우선합니다.",
        }
    else:
        guide_map = {
            "BUY": "익일 시초 5~15분 대기 후 가격 안정 또는 첫 눌림 확인 뒤 분할 진입합니다.",
            "BUY_WATCH": "익일 관심 유지가 기본입니다. 시초 강도가 좋으면 소액매수를 검토하고, 아니면 관찰 유지로 둡니다.",
            "WATCH": "익일 관심 유지가 기본입니다. 주문보다 장초반 흐름 확인이 우선입니다.",
            "HOLD": "익일 보유 유지가 기본입니다. 시초 약세가 크면 비중축소, 방어선 이탈이면 매도로 전환합니다.",
            "SELL_WATCH": "익일 소액매도 검토가 우선입니다. 장초반 약세면 절반정리 또는 축소를 먼저 봅니다.",
            "SELL": "익일 장 초반 유동성 구간에서 매도를 우선합니다. 약세가 크면 지체 없이 정리합니다.",
        }
    return guide_map.get(signal, "장 시작 후 신호를 다시 확인합니다.")


def _action_guide(row: pd.Series | dict[str, Any], *, execution_window: bool) -> str:
    key = "intraday_action_guide" if execution_window else "next_day_action_guide"
    value = str(row.get(key) or "").strip()
    if value and value.lower() not in {"nan", "none", "null"}:
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


def _display_signal_from_row(row: pd.Series | dict[str, Any], *, is_real_holding: bool = False) -> str:
    signal_text = str(row.get("signal") or "").upper()
    risk_flag = row.get("risk_flag")
    risk_text = "" if pd.isna(risk_flag) else str(risk_flag).strip()
    sell_trigger = _safe_bool(row.get("v2_sell_trigger", row.get("v2_week_sell_trigger", False)))
    sell_watch = _safe_bool(row.get("v2_sell_watch", row.get("v2_week_sell_watch", False)))
    risk_parts = {part.strip().lower() for part in risk_text.split("|") if part.strip()}

    if is_real_holding:
        if signal_text == "SELL" or sell_trigger:
            return "SELL"
        if signal_text == "SELL_WATCH" or sell_watch or {"weekly_sell_watch", "sell_watch"} & risk_parts:
            return "SELL_WATCH"
        return "HOLD"

    if signal_text in {"BUY", "BUY_WATCH", "SELL", "SELL_WATCH"}:
        return signal_text
    if signal_text == "WATCH":
        return "BUY_WATCH"
    if signal_text == "HOLD" and ({"weekly_sell_watch", "sell_watch"} & risk_parts):
        return "SELL_WATCH"
    return "HOLD"


def _display_signal(signal: Any, conviction_score: Any, risk_flag: Any, is_real_holding: bool = False) -> str:
    row = {"signal": signal, "conviction_score": conviction_score, "risk_flag": risk_flag}
    return _display_signal_from_row(row, is_real_holding=is_real_holding)


def _optimal_ma_summary_lines(row: pd.Series | dict[str, Any], *, signal_value: Any) -> list[str]:
    contract = v2_mode_contract_context(row)
    if contract.get("buy_window") is None and contract.get("sell_window") is None:
        return ["- 최적 MA: 데이터 없음"]
    lines: list[str] = []
    if contract.get("mode_label"):
        lines.append(f"- 최적 MA 계약: {contract['mode_label']}")
    buy_text = _contract_action_text(contract, "buy", detailed=True)
    sell_text = _contract_action_text(contract, "sell", detailed=True)
    if buy_text:
        lines.append(f"- {buy_text}")
    if sell_text:
        lines.append(f"- {sell_text}")
    return lines


def _latest_existing_path(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda item: item.stat().st_mtime)


def _first_existing_path(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _read_signal_latest() -> pd.DataFrame:
    candidates = [APP_DIR / "signal_daily_fast_latest.csv", APP_DIR / "signal_daily_latest.csv"]
    if not _is_execution_window():
        candidates = [APP_DIR / "signal_daily_latest.csv", APP_DIR / "signal_daily_fast_latest.csv"]
    path = _first_existing_path(candidates)
    if path is None:
        return pd.DataFrame()
    df = _read_csv_cached(path, dtype={"code": str})
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).map(normalize_code)
    return df


def _merged_display_signal(signal: Any, risk_flag: Any, is_real_holding: bool = False) -> str:
    row = {"signal": signal, "risk_flag": risk_flag}
    return _display_signal_from_row(row, is_real_holding=is_real_holding)


def _read_operational_dashboard_snapshot(*, execution_window: bool) -> pd.DataFrame:
    path = EXECUTION_SNAPSHOT_PATH if execution_window else POSTCLOSE_SNAPSHOT_PATH
    if not path.exists():
        return pd.DataFrame()
    df = _read_csv_cached(path, dtype={"code": str})
    if df.empty:
        return df
    work = df.copy()
    work["code"] = work["code"].astype(str).map(normalize_code)
    if "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
    if "display_signal" not in work.columns:
        work["display_signal"] = work.apply(
            lambda row: _merged_display_signal(
                row.get("signal"),
                row.get("risk_flag"),
                bool(row.get("is_real_holding", False)),
            ),
            axis=1,
        )
    if "signal_rank" not in work.columns:
        work["signal_rank"] = work["display_signal"].map(_signal_sort_key)
    if "signal_ko" not in work.columns:
        work["signal_ko"] = work["display_signal"].map(
            lambda value: _signal_label(value, execution_window=execution_window)
        )
    return work


def _read_signal_lookup() -> pd.DataFrame:
    snapshot = _read_operational_dashboard_snapshot(execution_window=True)
    if not snapshot.empty:
        return snapshot
    frames: list[pd.DataFrame] = []
    if _is_execution_window():
        candidates = [
            (APP_DIR / "signal_daily_fast_latest.csv", 0),
        ]
    else:
        candidates = [
            (APP_DIR / "signal_daily_latest.csv", 0),
            (APP_DIR / "signal_daily_fast_latest.csv", 1),
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
    combined["display_signal"] = combined.apply(
        lambda row: _merged_display_signal(row.get("signal"), row.get("risk_flag")),
        axis=1,
    )
    combined["_resolution_rank"] = combined["display_signal"].map(lambda x: SIGNAL_RESOLUTION_ORDER.get(str(x).upper(), 99))
    sort_cols = ["_resolution_rank", "_source_rank", "code"]
    ascending = [True, True, True]
    if "date" in combined.columns:
        sort_cols = ["date", "_resolution_rank", "_source_rank", "code"]
        ascending = [False, True, True, True]
    combined = combined.sort_values(sort_cols, ascending=ascending, kind="stable")
    combined = combined.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    return combined.drop(columns=["_source_rank", "_resolution_rank"], errors="ignore")


def _read_postclose_signal_lookup() -> pd.DataFrame:
    snapshot = _read_operational_dashboard_snapshot(execution_window=False)
    if not snapshot.empty:
        return snapshot
    path = APP_DIR / "signal_daily_latest.csv"
    if not path.exists():
        return pd.DataFrame()
    df = _read_csv_cached(path, dtype={"code": str})
    if df.empty:
        return df
    work = df.copy()
    work["code"] = work["code"].astype(str).map(normalize_code)
    if "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
    return work


def _read_decision_latest() -> pd.DataFrame:
    candidates = [APP_DIR / "decision_report_fast_latest.csv", APP_DIR / "decision_report_daily.csv"]
    if not _is_execution_window():
        candidates = [APP_DIR / "decision_report_daily.csv", APP_DIR / "decision_report_fast_latest.csv"]
    path = _first_existing_path(candidates)
    if path is None:
        return pd.DataFrame()
    return _read_csv_cached(path)


def _read_postclose_decision_latest() -> pd.DataFrame:
    path = APP_DIR / "decision_report_daily.csv"
    if not path.exists():
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
    df = read_price_latest_snapshot(allow_refresh=False)
    if df.empty:
        return pd.DataFrame(columns=["code", "name", "close", "date"])
    df = df.copy()
    df["code"] = df["code"].astype(str).map(normalize_code)
    return df


def _read_feature_snapshot() -> pd.DataFrame:
    snapshot_path = APP_DIR / "feature_latest_snapshot.pkl"
    legacy_snapshot_path = APP_DIR / "feature_latest_snapshot.csv"
    feature_path = FEATURE_DATA_PATH
    if (not snapshot_path.exists()) and legacy_snapshot_path.exists():
        try:
            legacy_snapshot_path.replace(snapshot_path)
        except Exception:
            snapshot_path = legacy_snapshot_path
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
    for col in ["close", "open", "high", "low", "volume", "trading_value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "quote_time" in df.columns:
        df["quote_time"] = pd.to_datetime(df["quote_time"], errors="coerce")
    if "close" in df.columns:
        df["close"] = df["close"].where(pd.to_numeric(df["close"], errors="coerce") > 0)
        df = df.dropna(subset=["close"])
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
    df = _read_signal_lookup()
    if df.empty:
        return df
    display = _exclude_securities_df(df)
    if display.empty:
        return display
    display = _merge_best_mode_contract(display)
    display["display_signal"] = display.apply(lambda row: _display_signal_from_row(row), axis=1)
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


def _append_missing_real_holdings(
    df: pd.DataFrame,
    *,
    chat_id: str,
    execution_window: bool,
) -> pd.DataFrame:
    if not str(chat_id or "").strip():
        return df
    snap = portfolio_snapshot(chat_id)
    if snap.empty:
        return df
    base = df.copy()
    base["code"] = base["code"].astype(str).map(normalize_code)
    snap = snap.copy()
    snap["code"] = snap["code"].astype(str).map(normalize_code)
    missing = snap[~snap["code"].isin(base["code"])].copy()
    if missing.empty:
        return base

    missing["signal"] = missing.get("signal", pd.Series(index=missing.index)).fillna("HOLD")
    missing["reason_1"] = missing.get("reason_1", pd.Series(index=missing.index)).fillna("실보유 종목")
    missing["reason_2"] = missing.get("reason_2", pd.Series(index=missing.index)).fillna("전략 신호 없음")
    missing["reason_3"] = missing.get("reason_3", pd.Series(index=missing.index)).fillna("")
    missing["risk_flag"] = missing.get("risk_flag", pd.Series(index=missing.index)).fillna("signal_missing")
    missing["is_real_holding"] = True
    missing["display_signal"] = missing.apply(
        lambda row: _display_signal_from_row(row, is_real_holding=True),
        axis=1,
    )
    missing["signal_rank"] = missing["display_signal"].map(_signal_sort_key)
    missing["signal_ko"] = missing["display_signal"].map(
        lambda value: _signal_label(value, execution_window=execution_window)
    )

    for col in base.columns:
        if col not in missing.columns:
            missing[col] = pd.NA
    missing = missing[base.columns]
    return pd.concat([base, missing], ignore_index=True)


def _operational_signal_df(chat_id: str = "") -> pd.DataFrame:
    df = _signal_display_df()
    if df.empty:
        if str(chat_id or "").strip():
            df = pd.DataFrame(columns=["code", "name", "signal", "display_signal", "signal_rank", "signal_ko", "is_real_holding"])
        else:
            return df
    elif EXECUTION_SNAPSHOT_PATH.exists():
        return df.sort_values(["signal_rank", "is_real_holding", "code"], ascending=[True, False, True]).reset_index(drop=True)
    held_codes = _real_holding_codes(chat_id)
    df = df.copy()
    df["is_real_holding"] = df["code"].astype(str).map(normalize_code).isin(held_codes)
    df["display_signal"] = df.apply(lambda row: _display_signal_from_row(row, is_real_holding=bool(row.get("is_real_holding", False))), axis=1)
    df["signal_rank"] = df["display_signal"].map(_signal_sort_key)
    df["signal_ko"] = df["display_signal"].map(_signal_label)
    df = _append_missing_real_holdings(df, chat_id=chat_id, execution_window=True)
    df = _merge_best_mode_contract(df)
    df = _filter_dashboard_like_signal_set(df)
    return df.sort_values(["signal_rank", "is_real_holding", "code"], ascending=[True, False, True]).reset_index(drop=True)


def _postclose_operational_signal_df(chat_id: str = "") -> pd.DataFrame:
    df = _read_postclose_signal_lookup()
    if df.empty:
        if str(chat_id or "").strip():
            df = pd.DataFrame(columns=["code", "name", "signal", "display_signal", "signal_rank", "signal_ko", "is_real_holding"])
        else:
            return df
    elif POSTCLOSE_SNAPSHOT_PATH.exists():
        return df.sort_values(["signal_rank", "is_real_holding", "code"], ascending=[True, False, True]).reset_index(drop=True)
    display = _exclude_securities_df(df)
    if display.empty:
        return display
    display["display_signal"] = display.apply(lambda row: _display_signal_from_row(row), axis=1)
    display["signal_rank"] = display["display_signal"].map(_signal_sort_key)
    display["signal_ko"] = display["display_signal"].map(lambda value: _signal_label(value, execution_window=False))
    held_codes = _real_holding_codes(chat_id)
    display["is_real_holding"] = display["code"].astype(str).map(normalize_code).isin(held_codes)
    display["display_signal"] = display.apply(lambda row: _display_signal_from_row(row, is_real_holding=bool(row.get("is_real_holding", False))), axis=1)
    display["signal_rank"] = display["display_signal"].map(_signal_sort_key)
    display["signal_ko"] = display["display_signal"].map(lambda value: _signal_label(value, execution_window=False))
    display = _append_missing_real_holdings(display, chat_id=chat_id, execution_window=False)
    display = _merge_best_mode_contract(display)
    display = _filter_dashboard_like_signal_set(display)
    return display.sort_values(["signal_rank", "is_real_holding", "code"], ascending=[True, False, True]).reset_index(drop=True)


def _decision_latest_row() -> pd.Series | None:
    decision = _read_decision_latest()
    if decision.empty:
        return None
    frame = decision.copy()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame.sort_values("date").iloc[-1]


def _postclose_decision_latest_row() -> pd.Series | None:
    decision = _read_postclose_decision_latest()
    if decision.empty:
        return None
    frame = decision.copy()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame.sort_values("date").iloc[-1]


def _market_session_open(now: datetime | None = None) -> bool:
    return _is_execution_window(now)


def _current_price_payload(code: str) -> dict[str, Any]:
    norm = normalize_code(code)
    snapshot_row: pd.Series | None = None
    snapshot_date = pd.NaT
    prices = _read_price_snapshot()
    if not prices.empty:
        hit = prices[prices["code"] == norm]
        if not hit.empty:
            snapshot_row = hit.iloc[-1]
            snapshot_date = pd.to_datetime(snapshot_row.get("date"), errors="coerce")

    if _is_execution_window():
        live_quotes = _read_live_quotes()
        if not live_quotes.empty:
            live = live_quotes[live_quotes["code"] == norm].copy()
            if not live.empty:
                if "date" not in live.columns:
                    live["date"] = pd.NaT
                if "quote_time" not in live.columns:
                    live["quote_time"] = pd.NaT
                live = live.sort_values(["date", "quote_time"], kind="stable")
                row = live.iloc[-1]
                close = _non_nan_float(row.get("close"))
                if close is not None and close > 0:
                    live_date = pd.to_datetime(row.get("date"), errors="coerce")
                    if pd.isna(snapshot_date) or (pd.notna(live_date) and live_date >= snapshot_date):
                        basis = _format_live_basis(row.get("date"), row.get("quote_time"))
                        return {"label": "기준가", "value": _fmt_num(close, "원"), "basis": basis, "numeric": close}

    if snapshot_row is not None:
        row = snapshot_row
        basis = "n/a"
        if pd.notna(row.get("date")):
            basis = str(pd.to_datetime(row.get("date"), errors="coerce").date())
        numeric = None if pd.isna(row.get("close")) else float(row.get("close"))
        return {"label": "기준가", "value": _fmt_num(row.get("close"), "원"), "basis": basis, "numeric": numeric}
    return {"label": "기준가", "value": "n/a", "basis": "n/a", "numeric": None}


def _current_price_info(code: str) -> tuple[str, str, str]:
    payload = _current_price_payload(code)
    return str(payload["label"]), str(payload["value"]), str(payload["basis"])


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
            "매수 10 70000 005930 (순서 자유)",
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
    execution_window = _is_execution_window()
    lines = [f"V2 실운영 최신 의사결정 ({'장중 실행형' if execution_window else '장후 익일후보형'})"]
    counts = df["display_signal"].fillna("").astype(str).str.upper().value_counts().to_dict()
    lines.append(f"- {_signal_distribution_text(counts, execution_window=execution_window)}")
    for _, row in df.head(12).iterrows():
        signal_value = row.get("display_signal", row.get("signal"))
        action_text = _current_action_text(signal_value, execution_window=execution_window)
        reason_text = _brief_reason_text(row)
        v2_text = _v2_timing_summary_text(row)
        next_text = _next_review_text(execution_window=execution_window)
        lines.append(
            f"- {_signal_label(signal_value, execution_window=execution_window)} | {row['code']} {row['name']} | V2 {v2_text} | 지금 행동: {action_text} | 이유: {reason_text} | 다음 판단: {next_text}"
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
        price_payload = _current_price_payload(code)
        price_label = str(price_payload["label"])
        price_value = str(price_payload["value"])
        price_basis = str(price_payload["basis"])
        price_numeric = price_payload.get("numeric")
        signal_value = row.get("display_signal", row.get("signal"))
        action_text = _current_action_text(signal_value, execution_window=execution_window)
        reason_text = _brief_reason_text(row)
        v2_text = _v2_timing_summary_text(row)
        lines = [
            f"- {row['code']} {row['name']} | {_signal_label(signal_value, execution_window=execution_window)} | {price_label} {price_value}({price_basis}) | 현재 행동: {action_text}",
            f"  V2: {v2_text}",
            f"  사유: {reason_text}",
        ]
        if str(signal_value).upper() in {"SELL", "SELL_WATCH"}:
            sell_hint = _sell_execution_hint(
                row,
                code=code,
                chat_id=chat_id,
                current_price=price_numeric,
                current_basis=f"{price_label} {price_basis}",
            )
            if sell_hint:
                lines.append(f"  가격: {sell_hint}")
        return lines

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


def postclose_summary_text(chat_id: str = "") -> str:
    signal_df = _postclose_operational_signal_df(chat_id)
    if signal_df.empty:
        return ""
    if "date" in signal_df.columns:
        signal_dates = pd.to_datetime(signal_df["date"], errors="coerce").dropna()
        if signal_dates.empty:
            return ""
        latest_signal_date = signal_dates.max().date()
    else:
        return ""
    if latest_signal_date != datetime.now().date():
        return ""

    decision = _postclose_decision_latest_row()
    counts = signal_df["display_signal"].fillna("").astype(str).str.upper().value_counts().to_dict()
    lines = ["[장후 요약]"]
    lines.append(f"- 기준일: {latest_signal_date}")
    if decision is not None:
        lines.append(f"- 시장 상태: {_market_state_label(decision.get('market_regime', '-'))}")
        try:
            exposure = float(decision.get("exposure", 0.0))
            lines.append(f"- 운용강도: {_operating_intensity_label(exposure)} (노출 {exposure:.2f})")
        except Exception:
            pass
    lines.append(
        "- "
        + " / ".join(
            [
                f"익일매수 {int(counts.get('BUY', 0))}건",
                f"익일관심유지 {int(counts.get('BUY_WATCH', 0) + counts.get('WATCH', 0))}건",
                f"익일소액매도검토 {int(counts.get('SELL_WATCH', 0))}건",
                f"익일매도 {int(counts.get('SELL', 0))}건",
            ]
        )
    )

    section_defs = [
        ("[익일매수]", signal_df[signal_df["display_signal"].isin(["BUY"])]),
        ("[익일관심유지]", signal_df[signal_df["display_signal"].isin(["BUY_WATCH", "WATCH"])]),
        ("[익일소액매도검토]", signal_df[signal_df["display_signal"].isin(["SELL_WATCH"])]),
        ("[익일매도]", signal_df[signal_df["display_signal"].isin(["SELL"])]),
    ]
    for title, section_df in section_defs:
        if section_df.empty:
            continue
        lines.extend(["", title])
        for _, row in section_df.head(12).iterrows():
            code = normalize_code(row.get("code"))
            price_payload = _current_price_payload(code)
            reason_text = _brief_reason_text(row)
            v2_text = _v2_timing_summary_text(row)
            signal_value = str(row.get("display_signal", "")).upper()
            lines.append(
                f"- {row['code']} {row['name']} | {_signal_label(signal_value, execution_window=False)} | "
                f"{price_payload['label']} {price_payload['value']}({price_payload['basis']})"
            )
            lines.append(f"  V2: {v2_text}")
            lines.append(f"  사유: {reason_text}")
            if signal_value in {"SELL", "SELL_WATCH"}:
                sell_hint = _sell_execution_hint(
                    row,
                    code=code,
                    chat_id=chat_id,
                    current_price=price_payload.get("numeric"),
                    current_basis=f"{price_payload['label']} {price_payload['basis']}",
                )
                if sell_hint:
                    lines.append(f"  가격: {sell_hint}")
    return "\n".join(lines)


def _postclose_latest_signal_date(signal_df: pd.DataFrame) -> datetime | None:
    if signal_df.empty or "date" not in signal_df.columns:
        return None
    dates = pd.to_datetime(signal_df["date"], errors="coerce").dropna()
    if dates.empty:
        return None
    return dates.max().to_pydatetime()


def _load_optimal_ma_windows_for_codes(codes: list[str]) -> pd.DataFrame:
    norm_codes = sorted({normalize_code(code) for code in codes if str(code or "").strip()})
    if not norm_codes or not OPTIMAL_MA_ALL_SELECTION_PATH.exists():
        return pd.DataFrame(columns=["code", "monthly_window", "weekly_window"])
    usecols = ["code", "name", "ma_timeframe", "ma_window"]
    df = pd.read_csv(OPTIMAL_MA_ALL_SELECTION_PATH, usecols=usecols, dtype={"code": str}, low_memory=False)
    if df.empty:
        return pd.DataFrame(columns=["code", "monthly_window", "weekly_window"])
    df["code"] = df["code"].astype(str).map(normalize_code)
    df["ma_timeframe"] = df["ma_timeframe"].astype(str).str.lower()
    sub = df[df["code"].isin(norm_codes) & df["ma_timeframe"].isin(["monthly", "weekly"])].copy()
    if sub.empty:
        return pd.DataFrame(columns=["code", "monthly_window", "weekly_window"])
    pivot = (
        sub.pivot_table(index=["code", "name"], columns="ma_timeframe", values="ma_window", aggfunc="last")
        .reset_index()
        .rename_axis(None, axis=1)
        .rename(columns={"monthly": "monthly_window", "weekly": "weekly_window"})
    )
    return pivot


def _load_close_history_for_codes(codes: list[str]) -> pd.DataFrame:
    norm_codes = sorted({normalize_code(code) for code in codes if str(code or "").strip()})
    if not norm_codes or not PRICE_PANEL_PATH.exists():
        return pd.DataFrame(columns=["date", "code", "close"])
    code_set = set(norm_codes)
    frames: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        PRICE_PANEL_PATH,
        usecols=["date", "code", "close"],
        dtype={"code": str},
        chunksize=250000,
        low_memory=False,
    ):
        chunk["code"] = chunk["code"].astype(str).map(normalize_code)
        part = chunk[chunk["code"].isin(code_set)][["date", "code", "close"]]
        if not part.empty:
            frames.append(part)
    if not frames:
        return pd.DataFrame(columns=["date", "code", "close"])
    hist = pd.concat(frames, ignore_index=True)
    hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
    hist["close"] = pd.to_numeric(hist["close"], errors="coerce")
    hist = hist.dropna(subset=["date", "close"]).sort_values(["code", "date"]).reset_index(drop=True)
    return hist


def _latest_optimal_ma_metrics(codes: list[str]) -> pd.DataFrame:
    windows = _load_optimal_ma_windows_for_codes(codes)
    hist = _load_close_history_for_codes(codes)
    if windows.empty or hist.empty:
        return pd.DataFrame(
            columns=[
                "code",
                "monthly_window",
                "monthly_ma_price",
                "monthly_dist",
                "weekly_window",
                "weekly_ma_price",
                "weekly_dist",
                "current_price",
            ]
        )

    rows: list[dict[str, Any]] = []
    for _, meta in windows.iterrows():
        code = normalize_code(meta.get("code"))
        sub = hist[hist["code"] == code]
        if sub.empty:
            continue
        close_series = sub.set_index("date")["close"].sort_index()
        current_price = float(close_series.iloc[-1])

        monthly_window = pd.to_numeric(pd.Series([meta.get("monthly_window")]), errors="coerce").iloc[0]
        weekly_window = pd.to_numeric(pd.Series([meta.get("weekly_window")]), errors="coerce").iloc[0]

        monthly_ma_price = None
        monthly_dist = None
        if pd.notna(monthly_window) and int(float(monthly_window)) > 0:
            monthly_series = close_series.resample("M").last().dropna()
            if not monthly_series.empty:
                monthly_ma_price = float(monthly_series.rolling(int(float(monthly_window)), min_periods=1).mean().iloc[-1])
                if monthly_ma_price:
                    monthly_dist = (current_price / monthly_ma_price) - 1.0

        weekly_ma_price = None
        weekly_dist = None
        if pd.notna(weekly_window) and int(float(weekly_window)) > 0:
            weekly_series = close_series.resample("W-FRI").last().dropna()
            if not weekly_series.empty:
                weekly_ma_price = float(weekly_series.rolling(int(float(weekly_window)), min_periods=1).mean().iloc[-1])
                if weekly_ma_price:
                    weekly_dist = (current_price / weekly_ma_price) - 1.0

        rows.append(
            {
                "code": code,
                "monthly_window": None if pd.isna(monthly_window) else int(float(monthly_window)),
                "monthly_ma_price": monthly_ma_price,
                "monthly_dist": monthly_dist,
                "weekly_window": None if pd.isna(weekly_window) else int(float(weekly_window)),
                "weekly_ma_price": weekly_ma_price,
                "weekly_dist": weekly_dist,
                "current_price": current_price,
            }
        )
    return pd.DataFrame(rows)


def _brief_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_path = WINDOWS_FONT_BOLD if bold else WINDOWS_FONT_REG
    return ImageFont.truetype(str(font_path), size=size)


def _brief_action_palette(signal_value: str) -> tuple[str, str]:
    signal = str(signal_value or "").upper()
    if signal == "BUY":
        return "#dbeafe", "#1d4ed8"
    if signal in {"BUY_WATCH", "WATCH"}:
        return "#fef3c7", "#b45309"
    if signal == "HOLD":
        return "#e0f2fe", "#0f766e"
    if signal in {"SELL_WATCH", "SELL"}:
        return "#fee2e2", "#b91c1c"
    return "#e5e7eb", "#334155"


def _brief_holding_palette(is_holding: bool) -> tuple[str, str]:
    if is_holding:
        return "#eff6ff", "#1d4ed8"
    return "#f5f3ff", "#6d28d9"


def _brief_price_label(row: pd.Series | dict[str, Any]) -> str:
    quote_raw = row.get("alert_quote_time", row.get("quote_time"))
    quote_ts = pd.to_datetime(pd.Series([quote_raw]), errors="coerce").iloc[0]
    if pd.notna(quote_ts):
        return f"현재({quote_ts.strftime('%H:%M')})"
    return "기준"


def _filter_dashboard_like_signal_set(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    work = df.copy()
    if "is_real_holding" not in work.columns:
        work["is_real_holding"] = False
    signal_text = work.get("display_signal", pd.Series(index=work.index, dtype="string")).astype(str).str.upper()
    action_mask = signal_text.isin(["BUY", "BUY_WATCH"])
    buy_cross_mask = pd.Series(False, index=work.index, dtype=bool)
    for col in ("v2_buy_cross", "v2_month_buy_cross"):
        if col in work.columns:
            buy_cross_mask = buy_cross_mask | pd.to_numeric(work[col], errors="coerce").fillna(0).astype(bool)
    holding_mask = work["is_real_holding"].fillna(False).astype(bool)
    if holding_mask.any():
        return work[holding_mask | (action_mask & buy_cross_mask)].copy()
    return work[action_mask & buy_cross_mask].copy()


def _brief_section_rows(signal_df: pd.DataFrame, *, execution_window: bool) -> list[tuple[str, pd.DataFrame]]:
    if execution_window:
        return [
            ("매도", signal_df[signal_df["display_signal"].eq("SELL")].copy()),
            ("소액매도검토", signal_df[signal_df["display_signal"].eq("SELL_WATCH")].copy()),
            ("보유유지", signal_df[signal_df["display_signal"].eq("HOLD")].copy()),
            ("소액매수검토", signal_df[signal_df["display_signal"].isin(["BUY", "BUY_WATCH", "WATCH"])].copy()),
        ]
    return [
        ("익일매도", signal_df[signal_df["display_signal"].eq("SELL")].copy()),
        ("익일소액매도검토", signal_df[signal_df["display_signal"].eq("SELL_WATCH")].copy()),
        ("익일보유", signal_df[signal_df["display_signal"].eq("HOLD")].copy()),
        ("익일관심유지", signal_df[signal_df["display_signal"].isin(["BUY", "BUY_WATCH", "WATCH"])].copy()),
    ]


def _prepare_brief_signal_frame(signal_df: pd.DataFrame) -> pd.DataFrame:
    if signal_df.empty:
        return signal_df.copy()
    metrics = _latest_optimal_ma_metrics(signal_df["code"].astype(str).tolist())
    work = signal_df.copy()
    if not metrics.empty:
        work = work.merge(metrics, on="code", how="left", suffixes=("", "_calc"))
    for src, dst in [
        ("current_price", "current_price"),
        ("monthly_window", "monthly_window"),
        ("monthly_ma_price", "monthly_ma_price"),
        ("monthly_dist", "monthly_dist"),
        ("weekly_window", "weekly_window"),
        ("weekly_ma_price", "weekly_ma_price"),
        ("weekly_dist", "weekly_dist"),
    ]:
        if f"{dst}_calc" in work.columns:
            work[dst] = pd.to_numeric(work.get(dst), errors="coerce").combine_first(
                pd.to_numeric(work.get(f"{dst}_calc"), errors="coerce")
            )
    work = normalize_v2_mode_contract_frame(normalize_v2_ma_frame(work))

    def _series_or_na(column: str) -> pd.Series:
        if column in work.columns:
            return pd.to_numeric(work[column], errors="coerce")
        return pd.Series([float("nan")] * len(work), index=work.index, dtype="float64")

    monthly_window = _series_or_na("v2_month_window")
    weekly_window = _series_or_na("v2_week_window")
    monthly_ma_price = _series_or_na("v2_month_ma")
    weekly_ma_price = _series_or_na("v2_week_ma")
    monthly_dist = _series_or_na("v2_month_display_dist")
    weekly_dist = _series_or_na("v2_week_display_dist")

    work["monthly_window"] = monthly_window
    work["weekly_window"] = weekly_window
    work["monthly_ma_price"] = monthly_ma_price
    work["weekly_ma_price"] = weekly_ma_price
    work["monthly_dist"] = monthly_dist
    work["weekly_dist"] = weekly_dist
    work["current_price"] = (
        _series_or_na("alert_current_price")
        .combine_first(_series_or_na("current_price"))
        .combine_first(_series_or_na("latest_close"))
        .combine_first(_series_or_na("close"))
    )

    buy_timeframe = work["v2_buy_timeframe"].astype("string").str.strip().str.lower() if "v2_buy_timeframe" in work.columns else pd.Series(pd.NA, index=work.index, dtype="string")
    sell_timeframe = work["v2_sell_timeframe"].astype("string").str.strip().str.lower() if "v2_sell_timeframe" in work.columns else pd.Series(pd.NA, index=work.index, dtype="string")
    buy_window = _series_or_na("v2_buy_window")
    sell_window = _series_or_na("v2_sell_window")
    buy_is_month = buy_timeframe.eq("monthly")
    sell_is_month = sell_timeframe.eq("monthly")

    work["buy_window"] = buy_window
    work["sell_window"] = sell_window
    work["buy_ma_price"] = _series_or_na("v2_buy_ma").combine_first(weekly_ma_price.where(~buy_is_month, monthly_ma_price))
    work["sell_ma_price"] = _series_or_na("v2_sell_ma").combine_first(weekly_ma_price.where(~sell_is_month, monthly_ma_price))
    work["buy_dist"] = _series_or_na("v2_buy_live_dist").combine_first(_series_or_na("v2_buy_period_dist")).combine_first(weekly_dist.where(~buy_is_month, monthly_dist))
    work["sell_dist"] = _series_or_na("v2_sell_live_dist").combine_first(_series_or_na("v2_sell_period_dist")).combine_first(weekly_dist.where(~sell_is_month, monthly_dist))
    return work


def render_postclose_brief_image(chat_id: str = "", *, require_today: bool = False) -> tuple[Path | None, str]:
    signal_df = _postclose_operational_signal_df(chat_id)
    if signal_df.empty:
        return None, ""

    latest_signal_dt = _postclose_latest_signal_date(signal_df)
    if latest_signal_dt is None:
        return None, ""
    if require_today and latest_signal_dt.date() != datetime.now().date():
        return None, ""

    decision = _postclose_decision_latest_row()
    work = _prepare_brief_signal_frame(signal_df)

    counts = work["display_signal"].fillna("").astype(str).str.upper().value_counts().to_dict()
    market_state = "-"
    exposure_text = "-"
    if decision is not None:
        market_state = _market_state_label(decision.get("market_regime", "-"))
        try:
            exposure_text = _operating_intensity_label(float(decision.get("exposure", 0.0)))
        except Exception:
            exposure_text = "-"

    title = "장후 브리핑"
    subtitle = (
        f"기준일 {latest_signal_dt.date()} · 시장 {market_state} · 운용강도 {exposure_text}"
    )
    summary_line = (
        f"익일보유 {int(counts.get('HOLD', 0))} · "
        f"익일관심유지 {int(counts.get('BUY_WATCH', 0) + counts.get('WATCH', 0) + counts.get('BUY', 0))} · "
        f"익일소액매도검토 {int(counts.get('SELL_WATCH', 0))} · "
        f"익일매도 {int(counts.get('SELL', 0))}"
    )

    section_defs = _brief_section_rows(work, execution_window=False)
    row_h = 68
    section_gap = 18
    section_title_h = 34
    table_header_h = 46
    top_h = 146
    footer_h = 52
    bottom_h = 40
    width = 1450
    margin = 30
    table_rows = int(sum(len(section_df) for _, section_df in section_defs if not section_df.empty))
    section_count = int(sum(1 for _, section_df in section_defs if not section_df.empty))
    height = (
        margin
        + top_h
        + section_count * (section_title_h + table_header_h)
        + table_rows * row_h
        + max(section_count - 1, 0) * section_gap
        + footer_h
        + bottom_h
        + margin
    )

    BRIEF_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRIEF_IMAGE_DIR / f"postclose_brief_{latest_signal_dt.strftime('%Y%m%d')}_{str(chat_id or 'default')}.png"

    img = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=24, fill="#ffffff", outline="#e2e8f0", width=2)

    title_font = _brief_font(34, bold=True)
    text_font = _brief_font(20)
    text_bold = _brief_font(20, bold=True)
    section_font = _brief_font(22, bold=True)
    cell_font = _brief_font(18)
    cell_bold = _brief_font(18, bold=True)

    draw.text((margin + 24, margin + 20), title, font=title_font, fill="#0f172a")
    draw.text((margin + 24, margin + 68), subtitle, font=text_font, fill="#475569")
    draw.text((margin + 24, margin + 96), summary_line, font=text_bold, fill="#0f172a")

    cols = [
        ("구분", 92),
        ("종목", 240),
        ("액션", 170),
        ("월/주 이격률", 270),
        ("가격 기준", 520),
    ]
    x_positions: list[int] = []
    x_cursor = margin + 24
    for _, col_w in cols:
        x_positions.append(x_cursor)
        x_cursor += col_w
    table_w = sum(col_w for _, col_w in cols)

    y = margin + top_h
    rendered_sections = 0
    for section_title, section_df in section_defs:
        if section_df.empty:
            continue
        draw.text((margin + 24, y), section_title, font=section_font, fill="#0f172a")
        y += section_title_h

        draw.rounded_rectangle((margin + 24, y, margin + 24 + table_w, y + table_header_h), radius=12, fill="#f8fafc", outline="#e2e8f0", width=1)
        for (col_name, _), x in zip(cols, x_positions):
            draw.text((x + 12, y + 12), col_name, font=cell_bold, fill="#334155")
        y += table_header_h

        for _, row in section_df.iterrows():
            row_box = (margin + 24, y, margin + 24 + table_w, y + row_h)
            draw.rounded_rectangle(row_box, radius=12, fill="#ffffff", outline="#e5e7eb", width=1)

            kind_bg, kind_fg = _brief_holding_palette(bool(row.get("is_real_holding", False)))
            action_bg, action_fg = _brief_action_palette(row.get("display_signal", row.get("signal")))
            kind_text = "보유" if bool(row.get("is_real_holding", False)) else "신규"
            action_text = str(row.get("signal_ko") or _signal_label(row.get("display_signal"), execution_window=False))

            kind_box = (x_positions[0] + 10, y + 16, x_positions[0] + 72, y + 50)
            draw.rounded_rectangle(kind_box, radius=16, fill=kind_bg)
            kind_bbox = draw.textbbox((0, 0), kind_text, font=cell_bold)
            kind_w = kind_bbox[2] - kind_bbox[0]
            draw.text((kind_box[0] + (kind_box[2] - kind_box[0] - kind_w) / 2, y + 22), kind_text, font=cell_bold, fill=kind_fg)

            draw.text((x_positions[1] + 10, y + 10), f"{normalize_code(row.get('code'))} {row.get('name', '-')}", font=cell_bold, fill="#0f172a")

            action_box = (x_positions[2] + 10, y + 16, x_positions[2] + 150, y + 50)
            draw.rounded_rectangle(action_box, radius=16, fill=action_bg)
            action_bbox = draw.textbbox((0, 0), action_text, font=cell_bold)
            action_w = action_bbox[2] - action_bbox[0]
            draw.text((action_box[0] + (action_box[2] - action_box[0] - action_w) / 2, y + 22), action_text, font=cell_bold, fill=action_fg)

            contract = v2_mode_contract_context(row)
            buy_window = pd.to_numeric(pd.Series([row.get("buy_window")]), errors="coerce").iloc[0]
            sell_window = pd.to_numeric(pd.Series([row.get("sell_window")]), errors="coerce").iloc[0]
            buy_dist = pd.to_numeric(pd.Series([row.get("buy_dist")]), errors="coerce").iloc[0]
            sell_dist = pd.to_numeric(pd.Series([row.get("sell_dist")]), errors="coerce").iloc[0]
            buy_short = contract.get("buy_short_label")
            sell_short = contract.get("sell_short_label")
            dist_line_1 = "-" if pd.isna(buy_window) or not buy_short else f"매수 {buy_short}{int(float(buy_window))} {_fmt_pct(buy_dist)}"
            dist_line_2 = "-" if pd.isna(sell_window) or not sell_short else f"매도 {sell_short}{int(float(sell_window))} {_fmt_pct(sell_dist)}"
            draw.text((x_positions[3] + 10, y + 10), dist_line_1, font=cell_font, fill="#0f172a")
            draw.text((x_positions[3] + 10, y + 36), dist_line_2, font=cell_font, fill="#475569")

            current_price = pd.to_numeric(pd.Series([row.get("current_price")]), errors="coerce").iloc[0]
            buy_ma_price = pd.to_numeric(pd.Series([row.get("buy_ma_price")]), errors="coerce").iloc[0]
            sell_ma_price = pd.to_numeric(pd.Series([row.get("sell_ma_price")]), errors="coerce").iloc[0]
            price_line_1 = f"{_brief_price_label(row)} {_fmt_num_plain(current_price)}"
            if bool(row.get("is_real_holding", False)):
                price_line_2 = "-" if pd.isna(sell_window) or not sell_short else f"매도선 {_fmt_num_plain(sell_ma_price)}"
            else:
                price_line_2 = "-" if pd.isna(buy_window) or not buy_short else f"매수선 {_fmt_num_plain(buy_ma_price)}"
            draw.text((x_positions[4] + 10, y + 10), price_line_1, font=cell_font, fill="#0f172a")
            draw.text((x_positions[4] + 10, y + 36), price_line_2, font=cell_font, fill="#475569")

            y += row_h
        rendered_sections += 1
        if rendered_sections < section_count:
            y += section_gap

    footer = "가격 기준: 계약 기준 매수선/매도선을 사용합니다."
    footer_y = max(y + 12, height - margin - footer_h)
    draw.text((margin + 24, footer_y), footer, font=_brief_font(16), fill="#64748b")
    img.save(out_path)

    caption = (
        f"[장후 브리핑] 기준 {latest_signal_dt.date()} | "
        f"익일보유 {int(counts.get('HOLD', 0))} / "
        f"익일관심유지 {int(counts.get('BUY_WATCH', 0) + counts.get('WATCH', 0) + counts.get('BUY', 0))} / "
        f"익일소액매도검토 {int(counts.get('SELL_WATCH', 0))} / "
        f"익일매도 {int(counts.get('SELL', 0))}"
    )
    return out_path, caption


def render_operational_brief_image(slot_label: str = "", chat_id: str = "", *, require_today: bool = False) -> tuple[Path | None, str]:
    signal_df = _operational_signal_df(chat_id)
    if signal_df.empty:
        return None, ""

    latest_signal_dt = _postclose_latest_signal_date(signal_df)
    if latest_signal_dt is None:
        return None, ""
    if require_today and latest_signal_dt.date() != datetime.now().date():
        return None, ""

    decision = _decision_latest_row()
    work = _prepare_brief_signal_frame(signal_df)
    counts = work["display_signal"].fillna("").astype(str).str.upper().value_counts().to_dict()
    market_state = "-"
    exposure_text = "-"
    if decision is not None:
        market_state = _market_state_label(decision.get("market_regime", "-"))
        try:
            exposure_text = _operating_intensity_label(float(decision.get("exposure", 0.0)))
        except Exception:
            exposure_text = "-"

    slot_text = str(slot_label or "").strip()
    title = "장초반 브리핑"
    stem = "open"
    if "프리" in slot_text:
        title = "프리장 1차 브리핑"
        stem = "premarket"
    elif "본" in slot_text:
        title = "본장 2차 브리핑"
        stem = "open"

    subtitle = (
        f"기준일 {latest_signal_dt.date()} · 시장 {market_state} · 운용강도 {exposure_text}"
    )
    summary_line = (
        f"보유유지 {int(counts.get('HOLD', 0))} · "
        f"소액매수검토 {int(counts.get('BUY_WATCH', 0) + counts.get('WATCH', 0) + counts.get('BUY', 0))} · "
        f"소액매도검토 {int(counts.get('SELL_WATCH', 0))} · "
        f"매도 {int(counts.get('SELL', 0))}"
    )

    section_defs = _brief_section_rows(work, execution_window=True)
    row_h = 68
    section_gap = 18
    section_title_h = 34
    table_header_h = 46
    top_h = 146
    footer_h = 52
    bottom_h = 40
    width = 1450
    margin = 30
    table_rows = int(sum(len(section_df) for _, section_df in section_defs if not section_df.empty))
    section_count = int(sum(1 for _, section_df in section_defs if not section_df.empty))
    height = (
        margin
        + top_h
        + section_count * (section_title_h + table_header_h)
        + table_rows * row_h
        + max(section_count - 1, 0) * section_gap
        + footer_h
        + bottom_h
        + margin
    )

    BRIEF_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRIEF_IMAGE_DIR / f"operational_brief_{stem}_{latest_signal_dt.strftime('%Y%m%d')}_{str(chat_id or 'default')}.png"

    img = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=24, fill="#ffffff", outline="#e2e8f0", width=2)

    title_font = _brief_font(34, bold=True)
    text_font = _brief_font(20)
    text_bold = _brief_font(20, bold=True)
    section_font = _brief_font(22, bold=True)
    cell_font = _brief_font(18)
    cell_bold = _brief_font(18, bold=True)

    draw.text((margin + 24, margin + 20), title, font=title_font, fill="#0f172a")
    draw.text((margin + 24, margin + 68), subtitle, font=text_font, fill="#475569")
    draw.text((margin + 24, margin + 96), summary_line, font=text_bold, fill="#0f172a")

    cols = [
        ("구분", 92),
        ("종목", 240),
        ("액션", 170),
        ("월/주 이격률", 270),
        ("가격 기준", 520),
    ]
    x_positions: list[int] = []
    x_cursor = margin + 24
    for _, col_w in cols:
        x_positions.append(x_cursor)
        x_cursor += col_w
    table_w = sum(col_w for _, col_w in cols)

    y = margin + top_h
    rendered_sections = 0
    for section_title, section_df in section_defs:
        if section_df.empty:
            continue
        draw.text((margin + 24, y), section_title, font=section_font, fill="#0f172a")
        y += section_title_h

        draw.rounded_rectangle((margin + 24, y, margin + 24 + table_w, y + table_header_h), radius=12, fill="#f8fafc", outline="#e2e8f0", width=1)
        for (col_name, _), x in zip(cols, x_positions):
            draw.text((x + 12, y + 12), col_name, font=cell_bold, fill="#334155")
        y += table_header_h

        for _, row in section_df.iterrows():
            row_box = (margin + 24, y, margin + 24 + table_w, y + row_h)
            draw.rounded_rectangle(row_box, radius=12, fill="#ffffff", outline="#e5e7eb", width=1)

            kind_bg, kind_fg = _brief_holding_palette(bool(row.get("is_real_holding", False)))
            action_bg, action_fg = _brief_action_palette(row.get("display_signal", row.get("signal")))
            kind_text = "보유" if bool(row.get("is_real_holding", False)) else "신규"
            action_text = str(row.get("signal_ko") or _signal_label(row.get("display_signal"), execution_window=True))

            kind_box = (x_positions[0] + 10, y + 16, x_positions[0] + 72, y + 50)
            draw.rounded_rectangle(kind_box, radius=16, fill=kind_bg)
            kind_bbox = draw.textbbox((0, 0), kind_text, font=cell_bold)
            kind_w = kind_bbox[2] - kind_bbox[0]
            draw.text((kind_box[0] + (kind_box[2] - kind_box[0] - kind_w) / 2, y + 22), kind_text, font=cell_bold, fill=kind_fg)

            draw.text((x_positions[1] + 10, y + 10), f"{normalize_code(row.get('code'))} {row.get('name', '-')}", font=cell_bold, fill="#0f172a")

            action_box = (x_positions[2] + 10, y + 16, x_positions[2] + 150, y + 50)
            draw.rounded_rectangle(action_box, radius=16, fill=action_bg)
            action_bbox = draw.textbbox((0, 0), action_text, font=cell_bold)
            action_w = action_bbox[2] - action_bbox[0]
            draw.text((action_box[0] + (action_box[2] - action_box[0] - action_w) / 2, y + 22), action_text, font=cell_bold, fill=action_fg)

            contract = v2_mode_contract_context(row)
            buy_window = pd.to_numeric(pd.Series([row.get("buy_window")]), errors="coerce").iloc[0]
            sell_window = pd.to_numeric(pd.Series([row.get("sell_window")]), errors="coerce").iloc[0]
            buy_dist = pd.to_numeric(pd.Series([row.get("buy_dist")]), errors="coerce").iloc[0]
            sell_dist = pd.to_numeric(pd.Series([row.get("sell_dist")]), errors="coerce").iloc[0]
            buy_short = contract.get("buy_short_label")
            sell_short = contract.get("sell_short_label")
            dist_line_1 = "-" if pd.isna(buy_window) or not buy_short else f"매수 {buy_short}{int(float(buy_window))} {_fmt_pct(buy_dist)}"
            dist_line_2 = "-" if pd.isna(sell_window) or not sell_short else f"매도 {sell_short}{int(float(sell_window))} {_fmt_pct(sell_dist)}"
            draw.text((x_positions[3] + 10, y + 10), dist_line_1, font=cell_font, fill="#0f172a")
            draw.text((x_positions[3] + 10, y + 36), dist_line_2, font=cell_font, fill="#475569")

            current_price = pd.to_numeric(pd.Series([row.get("current_price")]), errors="coerce").iloc[0]
            buy_ma_price = pd.to_numeric(pd.Series([row.get("buy_ma_price")]), errors="coerce").iloc[0]
            sell_ma_price = pd.to_numeric(pd.Series([row.get("sell_ma_price")]), errors="coerce").iloc[0]
            price_line_1 = f"{_brief_price_label(row)} {_fmt_num_plain(current_price)}"
            if bool(row.get("is_real_holding", False)):
                price_line_2 = "-" if pd.isna(sell_window) or not sell_short else f"매도선 {_fmt_num_plain(sell_ma_price)}"
            else:
                price_line_2 = "-" if pd.isna(buy_window) or not buy_short else f"매수선 {_fmt_num_plain(buy_ma_price)}"
            draw.text((x_positions[4] + 10, y + 10), price_line_1, font=cell_font, fill="#0f172a")
            draw.text((x_positions[4] + 10, y + 36), price_line_2, font=cell_font, fill="#475569")
            y += row_h

        rendered_sections += 1
        if rendered_sections < section_count:
            y += section_gap

    footer = "가격 기준: 계약 기준 매수선/매도선을 사용합니다."
    footer_y = max(y + 12, height - margin - footer_h)
    draw.text((margin + 24, footer_y), footer, font=_brief_font(16), fill="#64748b")
    img.save(out_path)

    caption = (
        f"[{title}] 기준 {latest_signal_dt.date()} | "
        f"보유유지 {int(counts.get('HOLD', 0))} / "
        f"소액매수검토 {int(counts.get('BUY_WATCH', 0) + counts.get('WATCH', 0) + counts.get('BUY', 0))} / "
        f"소액매도검토 {int(counts.get('SELL_WATCH', 0))} / "
        f"매도 {int(counts.get('SELL', 0))}"
    )
    return out_path, caption


def render_fast_trigger_image(signal_df: pd.DataFrame, *, slot_label: str = "") -> tuple[Path | None, str]:
    if signal_df.empty:
        return None, ""

    work = signal_df.copy()
    if "code" in work.columns:
        work["code"] = work["code"].astype(str).map(normalize_code)
    if "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["display_signal"] = work.get("signal", "").astype(str).str.upper()
    work = work[work["display_signal"].isin(["BUY", "SELL"])].copy()
    if work.empty:
        return None, ""

    work["is_real_holding"] = work["display_signal"].eq("SELL")
    # No fallback for fast trigger price: use explicit alert price only.
    work["current_price"] = _numeric_series_or_na(work, "alert_current_price")
    work["monthly_ma_price"] = _numeric_series_or_na(work, "alert_monthly_ma").combine_first(
        _numeric_series_or_na(work, "v2_month_ma")
    )
    work["weekly_ma_price"] = _numeric_series_or_na(work, "alert_weekly_ma").combine_first(
        _numeric_series_or_na(work, "v2_week_ma")
    )
    work["monthly_window"] = _numeric_series_or_na(work, "v2_month_window")
    work["weekly_window"] = _numeric_series_or_na(work, "v2_week_window")
    work["monthly_dist"] = _numeric_series_or_na(work, "v2_month_period_dist")
    work["weekly_dist"] = _numeric_series_or_na(work, "v2_week_period_dist")
    latest_signal_dt = work["date"].dropna().max()
    if pd.isna(latest_signal_dt):
        latest_signal_dt = pd.Timestamp(datetime.now().date())

    title = f"장중 FAST {slot_label}".strip()
    summary_line = (
        f"매수 {int(work['display_signal'].eq('BUY').sum())} · "
        f"매도 {int(work['display_signal'].eq('SELL').sum())}"
    )
    section_defs = [
        ("매도 변화", work[work["display_signal"] == "SELL"].copy()),
        ("매수 변화", work[work["display_signal"] == "BUY"].copy()),
    ]
    row_h = 68
    section_gap = 18
    section_title_h = 34
    table_header_h = 46
    top_h = 130
    footer_h = 52
    bottom_h = 36
    width = 1450
    margin = 30
    table_rows = int(sum(len(section_df) for _, section_df in section_defs if not section_df.empty))
    section_count = int(sum(1 for _, section_df in section_defs if not section_df.empty))
    height = (
        margin + top_h + section_count * (section_title_h + table_header_h) + table_rows * row_h
        + max(section_count - 1, 0) * section_gap + footer_h + bottom_h + margin
    )

    BRIEF_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = latest_signal_dt.strftime("%Y%m%d")
    out_path = BRIEF_IMAGE_DIR / f"fast_trigger_{stamp}_{slot_label.replace(':','').replace(' ','_') or 'slot'}.png"

    img = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=24, fill="#ffffff", outline="#e2e8f0", width=2)

    title_font = _brief_font(34, bold=True)
    text_font = _brief_font(20)
    text_bold = _brief_font(20, bold=True)
    section_font = _brief_font(22, bold=True)
    cell_font = _brief_font(18)
    cell_bold = _brief_font(18, bold=True)

    draw.text((margin + 24, margin + 20), title, font=title_font, fill="#0f172a")
    draw.text((margin + 24, margin + 68), f"기준일 {latest_signal_dt.date()} · 변화 종목만 표시", font=text_font, fill="#475569")
    draw.text((margin + 24, margin + 96), summary_line, font=text_bold, fill="#0f172a")

    cols = [
        ("구분", 92),
        ("종목", 240),
        ("액션", 170),
        ("기준가", 190),
        ("월/주 이격률", 270),
        ("가격 기준", 430),
    ]
    x_positions: list[int] = []
    x_cursor = margin + 24
    for _, col_w in cols:
        x_positions.append(x_cursor)
        x_cursor += col_w
    table_w = sum(col_w for _, col_w in cols)

    y = margin + top_h
    rendered_sections = 0
    for section_title, section_df in section_defs:
        if section_df.empty:
            continue
        draw.text((margin + 24, y), section_title, font=section_font, fill="#0f172a")
        y += section_title_h
        draw.rounded_rectangle((margin + 24, y, margin + 24 + table_w, y + table_header_h), radius=12, fill="#f8fafc", outline="#e2e8f0", width=1)
        for (col_name, _), x in zip(cols, x_positions):
            draw.text((x + 12, y + 12), col_name, font=cell_bold, fill="#334155")
        y += table_header_h

        for _, row in section_df.iterrows():
            row_box = (margin + 24, y, margin + 24 + table_w, y + row_h)
            draw.rounded_rectangle(row_box, radius=12, fill="#ffffff", outline="#e5e7eb", width=1)
            kind_bg, kind_fg = _brief_holding_palette(bool(row.get("is_real_holding", False)))
            action_bg, action_fg = _brief_action_palette(row.get("display_signal"))
            kind_text = "보유" if bool(row.get("is_real_holding", False)) else "신규"
            action_text = "매도" if str(row.get("display_signal")).upper() == "SELL" else "매수"

            kind_box = (x_positions[0] + 10, y + 16, x_positions[0] + 72, y + 50)
            draw.rounded_rectangle(kind_box, radius=16, fill=kind_bg)
            kind_bbox = draw.textbbox((0, 0), kind_text, font=cell_bold)
            kind_w = kind_bbox[2] - kind_bbox[0]
            draw.text((kind_box[0] + (kind_box[2] - kind_box[0] - kind_w) / 2, y + 22), kind_text, font=cell_bold, fill=kind_fg)

            draw.text((x_positions[1] + 10, y + 10), f"{normalize_code(row.get('code'))} {row.get('name', '-')}", font=cell_bold, fill="#0f172a")

            action_box = (x_positions[2] + 10, y + 16, x_positions[2] + 150, y + 50)
            draw.rounded_rectangle(action_box, radius=16, fill=action_bg)
            action_bbox = draw.textbbox((0, 0), action_text, font=cell_bold)
            action_w = action_bbox[2] - action_bbox[0]
            draw.text((action_box[0] + (action_box[2] - action_box[0] - action_w) / 2, y + 22), action_text, font=cell_bold, fill=action_fg)

            draw.text((x_positions[3] + 10, y + 22), _fmt_num_plain(row.get("current_price")), font=cell_font, fill="#0f172a")

            month_window = pd.to_numeric(pd.Series([row.get("monthly_window")]), errors="coerce").iloc[0]
            week_window = pd.to_numeric(pd.Series([row.get("weekly_window")]), errors="coerce").iloc[0]
            month_dist = pd.to_numeric(pd.Series([row.get("monthly_dist")]), errors="coerce").iloc[0]
            week_dist = pd.to_numeric(pd.Series([row.get("weekly_dist")]), errors="coerce").iloc[0]
            dist_line_1 = "-" if pd.isna(month_window) else f"월{int(float(month_window))} {_fmt_pct(month_dist)}"
            dist_line_2 = "-" if pd.isna(week_window) else f"주{int(float(week_window))} {_fmt_pct(week_dist)}"
            draw.text((x_positions[4] + 10, y + 10), dist_line_1, font=cell_font, fill="#0f172a")
            draw.text((x_positions[4] + 10, y + 36), dist_line_2, font=cell_font, fill="#475569")

            if bool(row.get("is_real_holding", False)):
                weekly_line = pd.to_numeric(pd.Series([row.get("weekly_ma_price")]), errors="coerce").iloc[0]
                price_line_1 = f"주{int(float(week_window))}선 {_fmt_num_plain(weekly_line)}" if pd.notna(week_window) else "주이평선 -"
                trigger_line = pd.to_numeric(pd.Series([row.get("alert_weekly_trigger_price")]), errors="coerce").iloc[0]
                price_line_2 = f"트리거 {_fmt_num_plain(trigger_line)}"
            else:
                monthly_line = pd.to_numeric(pd.Series([row.get("monthly_ma_price")]), errors="coerce").iloc[0]
                proposal = monthly_line * 1.02 if pd.notna(monthly_line) else None
                price_line_1 = f"월선 {_fmt_num_plain(monthly_line)}"
                price_line_2 = f"제안 {_fmt_num_plain(proposal)}"
            draw.text((x_positions[5] + 10, y + 10), price_line_1, font=cell_font, fill="#0f172a")
            draw.text((x_positions[5] + 10, y + 36), price_line_2, font=cell_font, fill="#475569")
            y += row_h

        rendered_sections += 1
        if rendered_sections < section_count:
            y += section_gap

    footer = "장중 FAST는 포지션 변화(BUY/SELL)만 표시합니다."
    footer_y = max(y + 12, height - margin - footer_h)
    draw.text((margin + 24, footer_y), footer, font=_brief_font(16), fill="#64748b")
    img.save(out_path)

    caption = f"[장중 FAST {slot_label}] 매수 {int(work['display_signal'].eq('BUY').sum())} / 매도 {int(work['display_signal'].eq('SELL').sum())}"
    return out_path, caption


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
            "- 실행 기본형: 월봉매수 / 주봉매도 / buy_0%__sell_-5%",
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
    is_real_holding = code in _real_holding_codes(chat_id)
    row["display_signal"] = _display_signal_from_row(row, is_real_holding=is_real_holding)
    decision = _decision_latest_row()

    price_payload = _current_price_payload(code)
    price_label = str(price_payload["label"])
    price_value = str(price_payload["value"])
    price_basis = str(price_payload["basis"])
    basis_numeric = price_payload.get("numeric")
    basis_text = f"{price_label} {price_basis}".strip()
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
    risk_flag = _prettify_risk_flag(row.get("risk_flag")) or "위험없음"
    stop_rule = _display_text(row.get("stop_rule"), "없음")
    exit_rule = _display_text(row.get("target_exit_rule"), "없음")
    entry_price = _resolve_entry_price(code, chat_id=chat_id, row=row)
    if entry_price is not None:
        row["entry_price"] = entry_price
    action_guide = _price_action_guide(row, current_price=basis_numeric, current_basis=basis_text)
    price_level_lines = _price_level_lines(code, current_price=basis_numeric, buy_price=entry_price)
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
        "[가격 기준 맵]",
        *(price_level_lines if price_level_lines else ["- 표시 가능한 가격 기준이 없습니다."]),
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
