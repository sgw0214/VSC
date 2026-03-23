from __future__ import annotations

import re
from dataclasses import dataclass, field

from new_strategy.telegram_bridge_portfolio import parse_trade_text


CODE_PATTERN = re.compile(r"\b([0-9A-Za-z]{4,6})\b")


@dataclass
class BridgeIntent:
    name: str
    args: dict[str, str] = field(default_factory=dict)


def _contains_any(raw: str, items: list[str]) -> bool:
    return any(item in raw for item in items)


def parse_intent(text: str) -> BridgeIntent:
    raw = (text or "").strip()
    lower = raw.lower()

    if not raw:
        return BridgeIntent("show_help")

    if lower == "/note":
        return BridgeIntent("note_prompt")

    if lower == "/notecancel":
        return BridgeIntent("note_cancel")

    for prefix in ("기록_", "기록]", "기록:", "기록 "):
        if raw.startswith(prefix):
            note_text = raw[len(prefix) :].strip()
            return BridgeIntent("note_direct", {"text": note_text})

    trade = parse_trade_text(raw)
    if trade is not None:
        if trade.blocked_reason:
            return BridgeIntent("record_manual_trade_blocked", {"message": trade.blocked_reason})
        return BridgeIntent(
            "record_manual_trade",
            {
                "side": trade.side,
                "code": trade.code,
                "quantity": str(trade.quantity),
                "price": str(trade.price),
            },
        )

    if lower in {"/help", "help"} or _contains_any(raw, ["사용법", "명령어", "도움말"]):
        return BridgeIntent("show_help")
    if lower in {"hi", "hello"} or raw in {"안녕", "안녕?", "안녕하세요", "안녕하세요?", "반가워", "반가워요"}:
        return BridgeIntent("greeting")
    if lower in {"yes", "y"} or raw in {"네", "예", "확인"}:
        return BridgeIntent("confirm_latest")
    if lower in {"no", "n"} or raw in {"아니오", "취소", "중단"}:
        return BridgeIntent("reject_latest")

    if lower in {"/status", "status"} or _contains_any(raw, ["시장 상태", "전략 상태", "상태 알려줘", "브릿지 상태"]):
        return BridgeIntent("status_query")
    if lower in {"/portfolio", "/positions", "portfolio", "positions"} or _contains_any(raw, ["보유현황", "실보유", "잔고", "포트폴리오"]):
        return BridgeIntent("portfolio_query")
    if lower in {"/myeval", "myeval"} or _contains_any(raw, ["내 보유종목 전략평가", "실보유 전략평가", "보유종목 전략평가"]):
        return BridgeIntent("myeval_query")
    if lower in {"/mytrades", "/manualtrades", "mytrades"} or _contains_any(raw, ["내 거래", "내 거래내역"]):
        return BridgeIntent("manual_trades_query")
    if lower in {"/pending", "pending"} or _contains_any(raw, ["미처리", "답 못한", "처리 안 된"]):
        return BridgeIntent("unhandled_query")
    if lower in {"/bridgeoff", "bridgeoff"} or _contains_any(raw, ["브릿지 꺼줘", "브릿지 off", "bridge off"]):
        return BridgeIntent("run_bridge_off")
    if lower in {"/streamliton", "streamliton"} or _contains_any(raw, ["스트림릿 켜줘", "대시보드 켜줘", "streamlit on"]):
        return BridgeIntent("run_streamlit_on")
    if lower in {"/streamlitoff", "streamlitoff"} or _contains_any(raw, ["스트림릿 꺼줘", "대시보드 꺼줘", "streamlit off"]):
        return BridgeIntent("run_streamlit_off")
    if lower in {"/refreshinc", "refreshinc"} or _contains_any(raw, ["증분최신화", "증분 최신화"]):
        return BridgeIntent("run_refresh_incremental")
    if lower in {"/refreshfull", "refreshfull"} or _contains_any(raw, ["전체증분최신화", "전체 증분 최신화"]):
        return BridgeIntent("run_refresh_full_incremental")

    if lower in {"/buy", "buy"} or _contains_any(raw, ["매수 후보", "매수 신호", "살만한 종목"]):
        return BridgeIntent("buy_query")
    if lower in {"/sell", "sell"} or _contains_any(raw, ["매도 후보", "매도 신호", "팔아야할 종목"]):
        return BridgeIntent("sell_query")
    if lower in {"/hold", "hold"} or _contains_any(raw, ["보유 종목", "보유 신호", "계속 들고갈 종목"]):
        return BridgeIntent("hold_query")
    if lower in {"/watch", "watch"} or _contains_any(raw, ["관심 종목", "지켜볼 종목"]):
        return BridgeIntent("watch_query")
    if lower in {"/latest", "latest"} or _contains_any(raw, ["최신 신호", "오늘 신호", "후보 보여줘"]):
        return BridgeIntent("signal_query")
    if lower in {"/tomorrow", "tomorrow"} or _contains_any(raw, ["익일 계획", "내일 계획", "내일 뭐해", "내일 매수", "내일 매도"]):
        return BridgeIntent("tomorrow_query")
    if _contains_any(raw, ["왜 매수가", "매수가 없어"]):
        return BridgeIntent("why_no_buy")
    if lower in {"/eval", "eval"} or _contains_any(raw, ["전략 성과", "백테스트"]) or "cagr" in lower or "mdd" in lower:
        return BridgeIntent("eval_query")
    if lower in {"/regime", "regime"} or _contains_any(raw, ["레짐", "노출", "리스크 상태"]):
        return BridgeIntent("regime_query")
    if lower in {"/trades", "trades"} or _contains_any(raw, ["거래 내역", "최근 거래", "트레이드"]):
        return BridgeIntent("trades_query")
    if lower in {"/alerts", "alerts"} or _contains_any(raw, ["최근 알림"]):
        return BridgeIntent("alerts_query")
    if lower in {"/health", "health"} or _contains_any(raw, ["데이터 상태", "최신 데이터", "헬스"]):
        return BridgeIntent("health_query")
    if lower in {"/report", "report"} or _contains_any(raw, ["리포트", "요약"]):
        return BridgeIntent("latest_report")

    confirm_match = re.match(r"^/?confirm\s+(\d+)$", lower)
    if confirm_match:
        return BridgeIntent("confirm_job", {"job_id": confirm_match.group(1)})

    reject_match = re.match(r"^/?reject\s+(\d+)$", lower)
    if reject_match:
        return BridgeIntent("reject_job", {"job_id": reject_match.group(1)})

    if "fast alert" in lower or _contains_any(raw, ["즉시 알림", "빠른 알림", "패스트 알림"]):
        return BridgeIntent("run_fast_alert")

    if _contains_any(raw, ["최신화", "갱신", "다시 받아", "업데이트"]) or "refresh" in lower:
        if _contains_any(raw, ["주가만", "가격만"]) or "price only" in lower:
            return BridgeIntent("run_refresh_data")
        return BridgeIntent("run_refresh_full")

    code_match = CODE_PATTERN.search(raw)
    if code_match:
        return BridgeIntent("signal_detail", {"code": code_match.group(1)})

    return BridgeIntent("chat")
