from __future__ import annotations

import csv
import json
import sys
import time as time_module
from dataclasses import dataclass
from datetime import datetime, time as time_of_day
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))
DOC_PATH = REPO_ROOT / "docs" / "STRATEGY_V2_FINAL_2026-03-21.md"
RUNTIME_CONTRACT_DOC_PATH = REPO_ROOT / "docs" / "STREAMLIT_RUNTIME_CONTRACT.md"
MARKET_SCHEDULE_PATH = REPO_ROOT / "run_market_schedule_service.py"
BRIDGE_SERVICE_PATH = REPO_ROOT / "telegram_bridge_service.py"
BRIDGE_TOOLS_PATH = REPO_ROOT / "telegram_bridge_tools.py"
STREAMLIT_APP_PATH = REPO_ROOT / "streamlit_app.py"
STREAMLIT_WRAPPER_STATE_PATH = Path(r"C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\streamlit_wrapper_state.json")
BRIDGE_STATE_PATH = Path(r"C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\telegram_bridge\telegram_bridge_state.json")
MESSAGE_LOG_PATH = Path(r"C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\telegram_bridge\telegram_bridge_message_log.csv")
MARKET_STATE_PATH = Path(r"C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\market_schedule_state.json")
MANUAL_POSITIONS_PATH = BRIDGE_STATE_PATH.parent / "manual_portfolio_positions.csv"
SHADOW_RUNTIME_DIR = REPO_ROOT / "output" / "strategy_v2"
CANONICAL_RUNTIME_FILES = [
    "signal_daily_latest.csv",
    "signal_daily_fast_latest.csv",
    "price_panel_latest_snapshot.csv",
    "price_panel_industry_base.pkl",
]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_message_rows() -> list[dict[str, str]]:
    if not MESSAGE_LOG_PATH.exists():
        return []
    with MESSAGE_LOG_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _contains_suspicious_mojibake(text: str) -> bool:
    if "\ufffd" in text:
        return True
    return any(0xF900 <= ord(ch) <= 0xFAFF for ch in text)


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def _check_doc_schedule() -> CheckResult:
    text = _read_text(DOC_PATH)
    needles = [
        "08:20 ~ 08:25",
        "09:20 ~ 09:25",
        "20:10",
        "마감 요약",
        "07:00",
    ]
    ok = _contains_all(text, needles)
    return CheckResult("doc_schedule", ok, "문서에 운영 스케줄 항목 존재" if ok else "문서 스케줄 항목 누락")


def _check_runtime_contract_doc() -> CheckResult:
    if not RUNTIME_CONTRACT_DOC_PATH.exists():
        return CheckResult("runtime_contract_doc", False, "runtime contract 문서 없음")
    text = _read_text(RUNTIME_CONTRACT_DOC_PATH)
    needles = [
        "단일 출력 경로 계약",
        "단일 진실원천 계약",
        "보유 종목 계약 이평가 계약",
        "상세 종목 선택 계약",
        "서버 stale 계약",
        "수정 완료 선언 계약",
        "이번에 반복된 실수 기록",
    ]
    ok = _contains_all(text, needles)
    return CheckResult("runtime_contract_doc", ok, "runtime contract 문서 존재" if ok else "runtime contract 문서 항목 누락")


def _check_market_schedule_times() -> CheckResult:
    text = _read_text(MARKET_SCHEDULE_PATH)
    needles = [
        '--intraday-open", default="08:10"',
        '--intraday-close", default="20:00"',
        '--eod-time", default="20:10"',
        '--krx-reconcile-time", default="07:00"',
    ]
    ok = _contains_all(text, needles)
    return CheckResult("market_schedule_times", ok, "운영 스케줄 시간 기본값 일치" if ok else "운영 스케줄 시간 기본값 불일치")


def _check_market_schedule_actions() -> CheckResult:
    text = _read_text(MARKET_SCHEDULE_PATH)
    needles = [
        "def _run_intraday_full_refresh_fast_alert()",
        "def _run_eod_refresh_summary()",
        "def _run_krx_reconcile()",
        '"--prefer-kiwoom-eod"',
        '"--send-alerts"',
    ]
    ok = _contains_all(text, needles)
    return CheckResult("market_schedule_actions", ok, "장중/EOD/KRX 액션 연결 존재" if ok else "스케줄 액션 연결 누락")


def _check_bridge_schedule_hooks() -> CheckResult:
    text = _read_text(BRIDGE_SERVICE_PATH)
    needles = [
        "def _maybe_send_early_session_brief",
        "def _maybe_send_postclose_summary",
        "_maybe_send_early_session_brief(cfg, state)",
        "_maybe_send_postclose_summary(cfg, state)",
        "scheduled_postclose_summary",
    ]
    ok = _contains_all(text, needles)
    return CheckResult("bridge_schedule_hooks", ok, "브리지 자동 발송 훅 연결 존재" if ok else "브리지 자동 발송 훅 누락")


def _check_bridge_text_generators() -> CheckResult:
    text = _read_text(BRIDGE_TOOLS_PATH)
    needles = [
        "def early_session_brief_text",
        "def postclose_summary_text",
        "signal_daily_latest.csv",
        "signal_daily_fast_latest.csv",
        "익일매수",
        "익일관심유지",
        "익일소액매도검토",
        "익일매도",
    ]
    ok = _contains_all(text, needles)
    return CheckResult("bridge_text_generators", ok, "브리프/장후 요약 생성기 존재" if ok else "브리프/장후 요약 생성기 누락")


def _check_streamlit_change_verification_contract() -> CheckResult:
    text = _read_text(STREAMLIT_APP_PATH)
    needles = [
        "변경 후 점검 계약",
        "python -m py_compile streamlit_app.py",
        "의사결정 상세차트 렌더",
    ]
    ok = _contains_all(text, needles)
    return CheckResult(
        "streamlit_change_verification_contract",
        ok,
        "Streamlit 변경 후 점검 계약 문구 존재" if ok else "Streamlit 변경 후 점검 계약 문구 누락",
    )


def _check_runtime_files() -> CheckResult:
    ok = BRIDGE_STATE_PATH.exists() and MARKET_STATE_PATH.exists() and MESSAGE_LOG_PATH.exists()
    return CheckResult("runtime_files", ok, "운영 상태 파일 존재" if ok else "운영 상태 파일 누락")



def _check_runtime_shadow_files() -> CheckResult:
    existing = [name for name in CANONICAL_RUNTIME_FILES if (SHADOW_RUNTIME_DIR / name).exists()]
    ok = not existing
    detail = "repo-local shadow runtime 파일 없음" if ok else f"repo-local shadow runtime 파일 존재: {', '.join(existing)}"
    return CheckResult("runtime_shadow_files", ok, detail)


def _streamlit_source_token() -> str:
    candidates = [
        path
        for path in REPO_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and "output" not in path.parts and ".venv" not in path.parts
    ]
    if not candidates:
        return "missing-source"
    latest = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    # PowerShell wrapper stores .NET DateTime ticks, not Unix ns.
    dotnet_ticks = int(latest.stat().st_mtime_ns / 100) + 621355968000000000
    return f"{dotnet_ticks}|{latest}"


def _check_streamlit_wrapper_source_fresh() -> CheckResult:
    if not STREAMLIT_WRAPPER_STATE_PATH.exists():
        return CheckResult("streamlit_wrapper_source_fresh", False, "streamlit wrapper state 없음")
    state = None
    last_exc: Exception | None = None
    for _ in range(5):
        try:
            state = _read_json(STREAMLIT_WRAPPER_STATE_PATH)
            break
        except Exception as exc:
            last_exc = exc
            time_module.sleep(0.2)
    if state is None:
        return CheckResult("streamlit_wrapper_source_fresh", False, f"wrapper state 파싱 실패: {type(last_exc).__name__}")
    running_token = str(state.get("source_token") or "").strip()
    current_token = _streamlit_source_token()
    ok = bool(running_token) and running_token == current_token
    if not ok and "|" in running_token and "|" in current_token:
        running_tick, running_path = running_token.split("|", 1)
        current_tick, current_path = current_token.split("|", 1)
        try:
            ok = running_path == current_path and abs(int(running_tick) - int(current_tick)) <= 10
        except ValueError:
            ok = False
    detail = "streamlit wrapper source token 최신" if ok else f"source token 불일치: running={running_token or '-'} current={current_token}"
    return CheckResult("streamlit_wrapper_source_fresh", ok, detail)


def _load_dashboard_contract_snapshot() -> tuple[pd.DataFrame, dict]:
    import logging

    for logger_name in [
        "streamlit",
        "streamlit.runtime",
        "streamlit.runtime.caching",
        "streamlit.runtime.caching.cache_data_api",
        "streamlit.runtime.scriptrunner_utils.script_run_context",
    ]:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    import new_strategy.streamlit_app as dashboard  # noqa: WPS433

    version_tokens = dashboard.build_version_tokens()
    payload = dashboard.build_strategy_report_payload(
        version_tokens["output"],
        version_tokens["price"],
        version_tokens["fundamental"],
        version_tokens["optimal_ma"],
        0,
        dashboard.is_execution_window(),
        0,
    )
    return payload.get("signal_df", pd.DataFrame()).copy(), payload


def _check_dashboard_display_signal_consistency() -> CheckResult:
    try:
        signal_df, payload = _load_dashboard_contract_snapshot()
        if signal_df.empty:
            return CheckResult("dashboard_display_signal_consistency", False, "signal_df empty")

        import new_strategy.streamlit_app as dashboard  # noqa: WPS433

        cfg = payload.get("cfg", {})
        holding_mask = signal_df.get("is_real_holding", pd.Series(False, index=signal_df.index)).fillna(False).astype(bool)
        sample = signal_df[holding_mask].copy()
        if sample.empty:
            sample = signal_df.head(5).copy()

        mismatches: list[str] = []
        for _, row in sample.head(5).iterrows():
            expected = str(dashboard.classify_signal(row, cfg) or "").strip().upper()
            actual = str(row.get("display_signal") or "").strip().upper()
            if expected != actual:
                mismatches.append(f"{str(row.get('code')).zfill(6)}:{actual}->{expected}")
        ok = not mismatches
        detail = "payload row와 display_signal 일치" if ok else " / ".join(mismatches)
        return CheckResult("dashboard_display_signal_consistency", ok, detail)
    except Exception as exc:
        return CheckResult("dashboard_display_signal_consistency", False, f"{type(exc).__name__}: {exc}")


def _check_contract_price_map_consistency() -> CheckResult:
    try:
        signal_df, _payload = _load_dashboard_contract_snapshot()
        if signal_df.empty:
            return CheckResult("contract_price_map_consistency", False, "signal_df empty")
        if not MANUAL_POSITIONS_PATH.exists():
            return CheckResult("contract_price_map_consistency", False, "manual positions missing")

        manual_positions = pd.read_csv(MANUAL_POSITIONS_PATH, dtype={"code": str}, low_memory=False)
        if manual_positions.empty:
            return CheckResult("contract_price_map_consistency", False, "manual positions empty")
        manual_positions["code"] = manual_positions["code"].astype(str).str.zfill(6)
        holding_mask = signal_df.get("is_real_holding", pd.Series(False, index=signal_df.index)).fillna(False).astype(bool)
        holdings = signal_df[holding_mask].copy()
        if holdings.empty:
            return CheckResult("contract_price_map_consistency", False, "보유 종목 없음")

        import new_strategy.streamlit_app as dashboard  # noqa: WPS433

        mismatches: list[str] = []
        for _, row in holdings.head(5).iterrows():
            code = str(row.get("code") or "").zfill(6)
            manual_row = manual_positions[manual_positions["code"] == code].tail(1)
            buy_price = float("nan")
            if not manual_row.empty:
                pos = manual_row.iloc[-1]
                buy_price = pd.to_numeric(pd.Series([pos.get("avg_price")]), errors="coerce").iloc[0]
                if pd.isna(buy_price):
                    buy_price = pd.to_numeric(pd.Series([pos.get("entry_price")]), errors="coerce").iloc[0]
            current_price = pd.to_numeric(pd.Series([row.get("alert_current_price", row.get("latest_close"))]), errors="coerce").iloc[0]
            level_df = dashboard.build_price_level_rows(
                code,
                current_price=None if pd.isna(current_price) else float(current_price),
                buy_price=None if pd.isna(buy_price) else float(buy_price),
                row=row,
            )
            if level_df.empty:
                mismatches.append(f"{code}:level_df empty")
                continue

            buy_rows = level_df[level_df["left_label"].astype(str).str.contains("매수이평가", na=False)]
            sell_rows = level_df[level_df["left_label"].astype(str).str.contains("매도이평가", na=False)]
            buy_price_map = float(buy_rows.iloc[-1]["price"]) if not buy_rows.empty else float("nan")
            sell_price_map = float(sell_rows.iloc[-1]["price"]) if not sell_rows.empty else float("nan")
            buy_expected = pd.to_numeric(pd.Series([row.get("v2_buy_ma")]), errors="coerce").iloc[0]
            sell_expected = pd.to_numeric(pd.Series([row.get("v2_sell_ma")]), errors="coerce").iloc[0]
            if pd.isna(buy_expected) or pd.isna(sell_expected):
                mismatches.append(f"{code}:expected ma missing")
                continue
            if pd.isna(buy_price_map) or abs(buy_price_map - float(buy_expected)) > 1e-6:
                mismatches.append(f"{code}:buy {buy_price_map} != {float(buy_expected)}")
            if pd.isna(sell_price_map) or abs(sell_price_map - float(sell_expected)) > 1e-6:
                mismatches.append(f"{code}:sell {sell_price_map} != {float(sell_expected)}")
        ok = not mismatches
        detail = "가격기준맵과 계약 이평가 일치" if ok else " / ".join(mismatches)
        return CheckResult("contract_price_map_consistency", ok, detail)
    except Exception as exc:
        return CheckResult("contract_price_map_consistency", False, f"{type(exc).__name__}: {exc}")


def _check_telegram_encoding_contract() -> CheckResult:
    if not MESSAGE_LOG_PATH.exists():
        return CheckResult("telegram_encoding_contract", False, "message log missing")
    try:
        raw = MESSAGE_LOG_PATH.read_bytes()
        if not raw.startswith(b"\xef\xbb\xbf"):
            return CheckResult("telegram_encoding_contract", False, "message log is not UTF-8 BOM CSV")
        rows = _read_message_rows()
    except Exception as exc:
        return CheckResult("telegram_encoding_contract", False, f"encoding read failed: {type(exc).__name__}")

    outgoing = [row for row in rows if str(row.get("direction") or "").strip().lower() == "out"]
    sample = outgoing[-200:] if outgoing else []
    broken = 0
    for row in sample:
        text = str(row.get("text") or "")
        if _contains_suspicious_mojibake(text):
            broken += 1
    if broken:
        return CheckResult("telegram_encoding_contract", False, f"detected suspicious mojibake rows={broken}")
    return CheckResult("telegram_encoding_contract", True, "UTF-8 BOM + no suspicious mojibake in recent outgoing rows")


def _check_postclose_state_field() -> CheckResult:
    if not BRIDGE_STATE_PATH.exists():
        return CheckResult("postclose_state_field", False, "브리지 상태 파일 없음")
    try:
        payload = _read_json(BRIDGE_STATE_PATH)
    except Exception as exc:
        return CheckResult("postclose_state_field", False, f"브리지 상태 파일 파싱 실패: {type(exc).__name__}")
    ok = "last_postclose_summary_at" in payload and "scheduled_briefs" in payload
    return CheckResult("postclose_state_field", ok, "장후 요약 상태 필드 존재" if ok else "장후 요약 상태 필드 누락")


def _check_bridge_loop_fresh() -> CheckResult:
    if not BRIDGE_STATE_PATH.exists():
        return CheckResult("bridge_loop_fresh", False, "브리지 상태 파일 없음")
    try:
        payload = _read_json(BRIDGE_STATE_PATH)
        last_loop_at = str(payload.get("last_loop_at") or "").strip()
        if not last_loop_at:
            return CheckResult("bridge_loop_fresh", False, "last_loop_at 없음")
        parsed = datetime.fromisoformat(last_loop_at)
    except Exception as exc:
        return CheckResult("bridge_loop_fresh", False, f"last_loop_at 파싱 실패: {type(exc).__name__}")
    delta = datetime.now() - parsed
    ok = delta.total_seconds() <= 600
    return CheckResult("bridge_loop_fresh", ok, f"최근 루프 {int(delta.total_seconds())}초 전" if ok else f"브리지 루프 stale: {int(delta.total_seconds())}초 전")


def _scheduled_message_sent_today(*, tool_name: str, text_contains: str = "") -> bool:
    today = datetime.now().date()
    for row in reversed(_read_message_rows()):
        if str(row.get("direction") or "").strip().lower() != "out":
            continue
        if str(row.get("tool_name") or "").strip() != tool_name:
            continue
        created_at = str(row.get("created_at") or "").strip()
        try:
            created = datetime.fromisoformat(created_at)
        except Exception:
            continue
        if created.date() != today:
            continue
        text = str(row.get("text") or "")
        if text_contains and text_contains not in text:
            continue
        return True
    return False


def _check_runtime_slot(*, name: str, after_time: time_of_day, state_key: str, tool_name: str, text_contains: str = "") -> CheckResult:
    now = datetime.now()
    if now.weekday() >= 5:
        return CheckResult(name, True, "주말은 점검 제외")
    if now.time() < after_time:
        return CheckResult(name, True, "아직 점검 시각 전")
    if not BRIDGE_STATE_PATH.exists():
        return CheckResult(name, False, "브리지 상태 파일 없음")
    try:
        payload = _read_json(BRIDGE_STATE_PATH)
    except Exception as exc:
        return CheckResult(name, False, f"브리지 상태 파일 파싱 실패: {type(exc).__name__}")
    scheduled = payload.get("scheduled_briefs", {})
    today_key = f"{now.date().isoformat()}:{state_key}"
    has_state_key = today_key in scheduled
    has_message = _scheduled_message_sent_today(tool_name=tool_name, text_contains=text_contains)
    ok = has_state_key and has_message
    if ok:
        return CheckResult(name, True, f"{today_key} 발송 확인")
    detail_parts = []
    if not has_state_key:
        detail_parts.append("state key 없음")
    if not has_message:
        detail_parts.append("message log 없음")
    return CheckResult(name, False, " / ".join(detail_parts))


def main() -> int:
    checks = [
        _check_doc_schedule(),
        _check_runtime_contract_doc(),
        _check_market_schedule_times(),
        _check_market_schedule_actions(),
        _check_bridge_schedule_hooks(),
        _check_bridge_text_generators(),
        _check_streamlit_change_verification_contract(),
        _check_runtime_files(),
        _check_runtime_shadow_files(),
        _check_streamlit_wrapper_source_fresh(),
        _check_dashboard_display_signal_consistency(),
        _check_contract_price_map_consistency(),
        _check_telegram_encoding_contract(),
        _check_postclose_state_field(),
        _check_bridge_loop_fresh(),
        _check_runtime_slot(
            name="runtime_preopen_brief",
            after_time=time_of_day(8, 25),
            state_key="preopen_1",
            tool_name="scheduled_early_session_brief",
            text_contains="[장초반 대응 프리장]",
        ),
        _check_runtime_slot(
            name="runtime_open_brief",
            after_time=time_of_day(9, 25),
            state_key="regular_open_1",
            tool_name="scheduled_early_session_brief",
            text_contains="[장초반 대응 본장]",
        ),
        _check_runtime_slot(
            name="runtime_postclose_summary",
            after_time=time_of_day(20, 10),
            state_key="postclose_summary",
            tool_name="scheduled_postclose_summary",
            text_contains="[장후 요약]",
        ),
    ]
    failures = [check for check in checks if not check.ok]
    for check in checks:
        prefix = "OK" if check.ok else "FAIL"
        print(f"[{prefix}] {check.name}: {check.detail}")
    if failures:
        print(f"\nFAILED {len(failures)} checks")
        return 1
    print(f"\nPASSED {len(checks)} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

