from __future__ import annotations

import argparse
import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, time as time_of_day
from pathlib import Path
from typing import Any

import requests

from new_strategy.paths import strategy_output_path
from new_strategy.telegram_bridge_config import TelegramBridgeConfig, load_bridge_config
from new_strategy.telegram_bridge_memory import (
    append_job_log,
    append_message_log,
    append_note_log,
    append_unhandled_log,
    load_recent_messages,
    load_state,
    reserve_job_id,
    save_state,
)
from new_strategy.telegram_bridge_models import generate_reply
from new_strategy.telegram_bridge_router import BridgeIntent, parse_intent
from new_strategy.telegram_bridge_tools import (
    JobSpec,
    build_job_spec,
    data_health_text,
    early_session_brief_text,
    eval_summary_text,
    help_text,
    latest_report_text,
    latest_signals_text,
    latest_status_text,
    local_chat_reply_ex,
    manual_trade_history_text,
    myeval_summary_text,
    portfolio_summary_text,
    read_log_tail,
    recent_alerts_text,
    recent_trades_text,
    record_manual_trade_text,
    regime_explain_text,
    signal_detail_text,
    start_job,
    tomorrow_plan_text,
    unhandled_requests_text,
    why_no_buy_text,
)


REPLY_TIMEOUT_SECONDS = 15
TELEGRAM_TEXT_LIMIT = 3500
PIPELINE_PROGRESS_PATH = strategy_output_path("dashboard_pipeline_progress.json")
EARLY_SESSION_WINDOWS = [
    ("preopen_1", "프리장", time_of_day(8, 20), time_of_day(8, 25, 59)),
    ("regular_open_1", "본장", time_of_day(9, 20), time_of_day(9, 25, 59)),
]


def _is_pipeline_job_command(command: list[str]) -> bool:
    return "new_strategy.run_signal_pipeline" in " ".join(str(part) for part in command)


def _write_shared_pipeline_progress(payload: dict[str, Any]) -> None:
    PIPELINE_PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _telegram_pipeline_run_id(job_id: int) -> str:
    return f"telegram_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"


def _touch_state_timestamp(state: dict[str, Any], key: str, when: datetime | None = None) -> None:
    state[key] = (when or datetime.now()).replace(microsecond=0).isoformat()


def _telegram_api(bot_token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    resp = requests.post(url, json=payload, timeout=40)
    resp.raise_for_status()
    return resp.json()


def get_updates(bot_token: str, offset: int | None = None, timeout: int = 20) -> list[dict[str, Any]]:
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params: dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(url, params=params, timeout=timeout + 10)
    resp.raise_for_status()
    return resp.json().get("result", [])


def _split_message(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    raw = str(text or "")
    if len(raw) <= limit:
        return [raw]

    chunks: list[str] = []
    current = ""
    for line in raw.splitlines(keepends=True):
        if len(current) + len(line) <= limit:
            current += line
            continue
        if current:
            chunks.append(current.rstrip())
            current = ""
        if len(line) <= limit:
            current = line
            continue
        start = 0
        while start < len(line):
            piece = line[start : start + limit]
            chunks.append(piece.rstrip())
            start += limit
    if current:
        chunks.append(current.rstrip())
    return [chunk for chunk in chunks if chunk]


def send_text(bot_token: str, chat_id: str, text: str) -> None:
    for chunk in _split_message(text):
        _telegram_api(bot_token, "sendMessage", {"chat_id": chat_id, "text": chunk})


def _safe_send_text(
    cfg: TelegramBridgeConfig,
    state: dict[str, Any],
    *,
    chat_id: str,
    text: str,
    error_action: str,
    when: datetime | None = None,
) -> bool:
    try:
        send_text(cfg.bot_token, chat_id, text)
        _touch_state_timestamp(state, "last_outgoing_at", when)
        return True
    except requests.RequestException as exc:
        _touch_state_timestamp(state, "last_error_at", when)
        state["last_error_action"] = error_action
        state["last_error_message"] = str(exc)
        save_state(cfg.state_path, state)
        return False


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    return update.get("message") or update.get("edited_message")


def _job_preview_text(job_id: int, job_spec: JobSpec) -> str:
    return "\n".join(
        [
            f"작업 확인이 필요합니다. job_id={job_id}",
            job_spec.summary,
            "실행하려면 이 채팅에서 `yes` 또는 `no`로 답해 주세요.",
            f"명시적으로 확인하려면 `confirm {job_id}`를 입력해 주세요.",
            f"명시적으로 취소하려면 `reject {job_id}`를 입력해 주세요.",
        ]
    )


def _dispatch_query(intent: BridgeIntent, chat_id: str) -> tuple[str, str]:
    query_map = {
        "status_query": lambda: latest_status_text(chat_id),
        "portfolio_query": lambda: portfolio_summary_text(chat_id),
        "myeval_query": lambda: myeval_summary_text(chat_id),
        "manual_trades_query": lambda: manual_trade_history_text(chat_id),
        "unhandled_query": lambda: unhandled_requests_text(chat_id),
        "signal_query": lambda: latest_signals_text(chat_id=chat_id),
        "tomorrow_query": lambda: tomorrow_plan_text(chat_id),
        "buy_query": lambda: latest_signals_text(signal_filter="BUY", chat_id=chat_id),
        "sell_query": lambda: latest_signals_text(signal_filter="SELL", chat_id=chat_id),
        "hold_query": lambda: latest_signals_text(signal_filter="HOLD", chat_id=chat_id),
        "watch_query": lambda: latest_signals_text(signal_filter="WATCH", chat_id=chat_id),
        "eval_query": lambda: eval_summary_text(chat_id),
        "regime_query": regime_explain_text,
        "why_no_buy": why_no_buy_text,
        "trades_query": recent_trades_text,
        "alerts_query": recent_alerts_text,
        "health_query": data_health_text,
        "latest_report": lambda: latest_report_text(chat_id),
        "show_help": help_text,
        "greeting": help_text,
    }
    if intent.name == "signal_detail":
        return signal_detail_text(intent.args["code"], chat_id), "signal_detail"
    handler = query_map.get(intent.name, help_text)
    return handler(), intent.name


def _context_blocks_for_chat(text: str, chat_id: str) -> list[str]:
    blocks = [
        "Current system status:\n" + latest_status_text(chat_id),
        "Latest decision report:\n" + latest_report_text(chat_id),
    ]
    intent = parse_intent(text)
    if intent.name == "signal_detail":
        blocks.append("Signal detail:\n" + signal_detail_text(intent.args["code"], chat_id))
    return blocks


def _start_job(
    *,
    cfg: TelegramBridgeConfig,
    chat_id: str,
    job_id: int,
    job_spec: JobSpec,
    running_jobs: dict[int, dict[str, Any]],
) -> str:
    log_path = cfg.jobs_dir / f"job_{job_id}.log"
    command = list(job_spec.command)
    progress_run_id = ""
    started_at = datetime.now().isoformat(timespec="seconds")
    if _is_pipeline_job_command(command):
        progress_run_id = _telegram_pipeline_run_id(job_id)
        if "--progress-file" not in command:
            command.extend(["--progress-file", str(PIPELINE_PROGRESS_PATH)])
        _write_shared_pipeline_progress(
            {
                "run_id": progress_run_id,
                "pid": 0,
                "started_at": started_at,
                "updated_at": started_at,
                "finished_at": "",
                "status": "starting",
                "percent": 0,
                "stage": "starting",
                "detail": job_spec.summary,
                "duration_seconds": 0,
                "description": job_spec.summary,
                "command": " ".join(job_spec.command),
                "stdout_path": str(log_path),
                "stderr_path": str(log_path),
                "source": "telegram",
                "job_id": str(job_id),
            }
        )
    effective_job_spec = JobSpec(
        action=job_spec.action,
        summary=job_spec.summary,
        command=command,
        require_confirm=job_spec.require_confirm,
    )
    proc, log_handle = start_job(effective_job_spec, log_path)
    if progress_run_id:
        _write_shared_pipeline_progress(
            {
                "run_id": progress_run_id,
                "pid": proc.pid,
                "started_at": started_at,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": "",
                "status": "starting",
                "percent": 0,
                "stage": "starting",
                "detail": job_spec.summary,
                "duration_seconds": 0,
                "description": job_spec.summary,
                "command": " ".join(job_spec.command),
                "stdout_path": str(log_path),
                "stderr_path": str(log_path),
                "source": "telegram",
                "job_id": str(job_id),
            }
        )
    running_jobs[job_id] = {
        "process": proc,
        "log_handle": log_handle,
        "chat_id": chat_id,
        "job_id": job_id,
        "action": job_spec.action,
        "summary": job_spec.summary,
        "log_path": str(log_path),
        "started_at": datetime.now().isoformat(),
        "progress_run_id": progress_run_id,
    }
    append_job_log(
        cfg.job_log_path,
        job_id=job_id,
        chat_id=chat_id,
        action=job_spec.action,
        status="started",
        summary=job_spec.summary,
        command=" ".join(effective_job_spec.command),
        log_path=str(log_path),
    )
    return "\n".join(
        [
            f"작업을 시작했습니다. job_id={job_id}",
            job_spec.summary,
            "완료되면 결과와 최근 로그를 다시 알려드리겠습니다.",
        ]
    )

def _prune_scheduled_briefs(state: dict[str, Any], keep_days: int = 7) -> None:
    now = datetime.now()
    scheduled = state.setdefault("scheduled_briefs", {})
    stale_keys: list[str] = []
    for key, value in scheduled.items():
        try:
            created = datetime.fromisoformat(str(value))
        except Exception:
            stale_keys.append(key)
            continue
        if (now - created).days > keep_days:
            stale_keys.append(key)
    for key in stale_keys:
        scheduled.pop(key, None)


def _maybe_send_early_session_brief(cfg: TelegramBridgeConfig, state: dict[str, Any]) -> None:
    now = datetime.now()
    if now.weekday() >= 5:
        return
    if not cfg.allowed_chat_ids:
        return

    _prune_scheduled_briefs(state)
    scheduled = state.setdefault("scheduled_briefs", {})
    sent = False

    for slot_key, slot_label, start_at, end_at in EARLY_SESSION_WINDOWS:
        if not (start_at <= now.time() <= end_at):
            continue
        state_key = f"{now.date().isoformat()}:{slot_key}"
        if state_key in scheduled:
            continue
        for chat_id in cfg.allowed_chat_ids:
            text = early_session_brief_text(slot_label, str(chat_id))
            sent_ok = _safe_send_text(
                cfg,
                state,
                chat_id=str(chat_id),
                text=text,
                error_action="scheduled_early_session_brief",
                when=now,
            )
            if not sent_ok:
                continue
            append_message_log(
                cfg.message_log_path,
                direction="out",
                chat_id=str(chat_id),
                text=text,
                intent="scheduled_early_session_brief",
                used_model=False,
                tool_name="scheduled_early_session_brief",
            )
        scheduled[state_key] = now.isoformat()
        sent = True

    if sent:
        _touch_state_timestamp(state, "last_early_session_brief_at", now)
        save_state(cfg.state_path, state)


def _resolve_latest_pending_job_id(state: dict[str, Any], chat_id: str) -> str | None | list[str]:
    pending = state.get("pending_confirmations", {})
    matches = [
        str(job_id)
        for job_id, payload in pending.items()
        if str(payload.get("chat_id")) == str(chat_id)
    ]
    if not matches:
        return None
    matches = sorted(matches, key=lambda value: int(value))
    if len(matches) == 1:
        return matches[0]
    return matches


def _handle_confirmation(
    *,
    cfg: TelegramBridgeConfig,
    state: dict[str, Any],
    chat_id: str,
    intent: BridgeIntent,
    running_jobs: dict[int, dict[str, Any]],
) -> str:
    job_id = intent.args.get("job_id", "")
    pending = state.get("pending_confirmations", {}).get(job_id)
    if not pending or str(pending.get("chat_id")) != str(chat_id):
        return f"job_id={job_id}에 해당하는 대기 작업이 없습니다."

    job_spec = JobSpec(
        action=str(pending["action"]),
        summary=str(pending["summary"]),
        command=list(pending["command"]),
        require_confirm=False,
    )
    del state["pending_confirmations"][job_id]
    if job_spec.action == "run_bridge_off":
        state["shutdown_after_reply"] = True
        save_state(cfg.state_path, state)
        append_job_log(
            cfg.job_log_path,
            job_id=int(job_id),
            chat_id=chat_id,
            action=job_spec.action,
            status="finished",
            summary=job_spec.summary,
        )
        return "브리지를 종료합니다. 다시 열려면 PC에서 브리지를 다시 실행해야 합니다."

    save_state(cfg.state_path, state)
    return _start_job(cfg=cfg, chat_id=chat_id, job_id=int(job_id), job_spec=job_spec, running_jobs=running_jobs)


def _handle_rejection(
    *,
    cfg: TelegramBridgeConfig,
    state: dict[str, Any],
    chat_id: str,
    intent: BridgeIntent,
) -> str:
    job_id = intent.args.get("job_id", "")
    pending = state.get("pending_confirmations", {}).get(job_id)
    if not pending or str(pending.get("chat_id")) != str(chat_id):
        return f"job_id={job_id}에 해당하는 대기 작업이 없습니다."
    del state["pending_confirmations"][job_id]
    save_state(cfg.state_path, state)
    append_job_log(
        cfg.job_log_path,
        job_id=int(job_id),
        chat_id=chat_id,
        action=str(pending["action"]),
        status="rejected",
        summary=str(pending["summary"]),
        command=" ".join(pending["command"]),
    )
    return f"job_id={job_id} 작업을 취소했습니다."


def _handle_latest_confirmation(
    *,
    cfg: TelegramBridgeConfig,
    state: dict[str, Any],
    chat_id: str,
    running_jobs: dict[int, dict[str, Any]],
) -> str:
    resolved = _resolve_latest_pending_job_id(state, chat_id)
    if resolved is None:
        return "확인 대기 중인 작업이 없습니다."
    if isinstance(resolved, list):
        ids = ", ".join(resolved)
        return f"대기 중인 작업이 여러 개 있습니다: {ids}. `confirm <job_id>` 또는 `reject <job_id>`로 지정해 주세요."
    return _handle_confirmation(
        cfg=cfg,
        state=state,
        chat_id=chat_id,
        intent=BridgeIntent("confirm_job", {"job_id": resolved}),
        running_jobs=running_jobs,
    )


def _handle_latest_rejection(
    *,
    cfg: TelegramBridgeConfig,
    state: dict[str, Any],
    chat_id: str,
) -> str:
    resolved = _resolve_latest_pending_job_id(state, chat_id)
    if resolved is None:
        return "확인 대기 중인 작업이 없습니다."
    if isinstance(resolved, list):
        ids = ", ".join(resolved)
        return f"대기 중인 작업이 여러 개 있습니다: {ids}. `confirm <job_id>` 또는 `reject <job_id>`로 지정해 주세요."
    return _handle_rejection(
        cfg=cfg,
        state=state,
        chat_id=chat_id,
        intent=BridgeIntent("reject_job", {"job_id": resolved}),
    )


def _route_message(
    *,
    cfg: TelegramBridgeConfig,
    state: dict[str, Any],
    chat_id: str,
    text: str,
    running_jobs: dict[int, dict[str, Any]],
) -> tuple[str, str, bool]:
    pending_notes = state.setdefault("pending_notes", {})
    raw_text = str(text or "").strip()
    if str(chat_id) in pending_notes:
        if raw_text.lower() == "/notecancel":
            pending_notes.pop(str(chat_id), None)
            save_state(cfg.state_path, state)
            return "기록 대기를 취소했습니다.", "note_cancel", False
        if raw_text and not raw_text.startswith("/"):
            append_note_log(
                cfg.notes_log_path,
                chat_id=chat_id,
                text=raw_text,
                note_type="record",
            )
            pending_notes.pop(str(chat_id), None)
            save_state(cfg.state_path, state)
            return "기록으로 저장했습니다. 나중에 모아서 검토할 수 있습니다.", "record_note", False
        if raw_text.startswith("/"):
            return "지금은 기록 내용을 기다리고 있습니다. 내용을 그대로 보내거나, 취소하려면 /notecancel 을 입력하세요.", "note_pending", False

    intent = parse_intent(text)

    if intent.name in {
        "show_help",
        "greeting",
        "status_query",
        "portfolio_query",
        "myeval_query",
        "manual_trades_query",
        "unhandled_query",
        "signal_query",
        "tomorrow_query",
        "buy_query",
        "sell_query",
        "hold_query",
        "watch_query",
        "eval_query",
        "regime_query",
        "why_no_buy",
        "trades_query",
        "alerts_query",
        "health_query",
        "latest_report",
        "signal_detail",
    }:
        reply, tool_name = _dispatch_query(intent, chat_id)
        return reply, tool_name, False

    if intent.name == "record_manual_trade":
        reply = record_manual_trade_text(
            chat_id=chat_id,
            side=intent.args["side"],
            code=intent.args["code"],
            quantity=intent.args["quantity"],
            price=intent.args["price"],
        )
        return reply, "record_manual_trade", False

    if intent.name == "record_manual_trade_blocked":
        return intent.args.get("message", "입력값이 비정상적으로 보여 거래 기록을 저장하지 않았습니다."), "record_manual_trade_blocked", False

    if intent.name == "note_prompt":
        pending_notes[str(chat_id)] = datetime.now().isoformat()
        save_state(cfg.state_path, state)
        return '기록할 내용을 다음 메시지로 보내주세요. 취소는 /notecancel 입니다.', "note_prompt", False

    if intent.name == "note_direct":
        note_text = str(intent.args.get("text") or "").strip()
        if not note_text:
            return "기록할 내용을 함께 보내주세요. 예: 기록_신영증권 가격규칙 확인 필요", "note_direct_empty", False
        append_note_log(
            cfg.notes_log_path,
            chat_id=chat_id,
            text=note_text,
            note_type="record",
        )
        return "기록 저장했습니다.", "note_direct", False

    if intent.name == "note_cancel":
        pending_notes.pop(str(chat_id), None)
        save_state(cfg.state_path, state)
        return "기록 대기를 취소했습니다.", "note_cancel", False

    if intent.name == "confirm_job":
        return _handle_confirmation(cfg=cfg, state=state, chat_id=chat_id, intent=intent, running_jobs=running_jobs), "confirm_job", False

    if intent.name == "reject_job":
        return _handle_rejection(cfg=cfg, state=state, chat_id=chat_id, intent=intent), "reject_job", False

    if intent.name == "confirm_latest":
        return _handle_latest_confirmation(cfg=cfg, state=state, chat_id=chat_id, running_jobs=running_jobs), "confirm_latest", False

    if intent.name == "reject_latest":
        return _handle_latest_rejection(cfg=cfg, state=state, chat_id=chat_id), "reject_latest", False

    if intent.name in {
        "run_fast_alert",
        "run_refresh_data",
        "run_refresh_incremental",
        "run_refresh_full",
        "run_refresh_full_incremental",
        "run_streamlit_on",
        "run_streamlit_off",
        "run_bridge_off",
    }:
        job_spec = build_job_spec(intent.name)
        if job_spec is None:
            return "지원하지 않는 작업입니다.", "job_unsupported", False
        job_id = reserve_job_id(state)
        save_state(cfg.state_path, state)
        if job_spec.require_confirm:
            state.setdefault("pending_confirmations", {})[str(job_id)] = {
                "chat_id": chat_id,
                "action": job_spec.action,
                "summary": job_spec.summary,
                "command": job_spec.command,
            }
            save_state(cfg.state_path, state)
            append_job_log(
                cfg.job_log_path,
                job_id=job_id,
                chat_id=chat_id,
                action=job_spec.action,
                status="pending_confirmation",
                summary=job_spec.summary,
                command=" ".join(job_spec.command),
            )
            return _job_preview_text(job_id, job_spec), "job_preview", False
        return _start_job(cfg=cfg, chat_id=chat_id, job_id=job_id, job_spec=job_spec, running_jobs=running_jobs), "job_started", False

    local = local_chat_reply_ex(text, chat_id)
    if not cfg.openai_api_key:
        return local.text, ("chat_local" if local.answered else "chat_unhandled"), False

    history = load_recent_messages(cfg.message_log_path, chat_id, cfg.history_turns)
    context_blocks = _context_blocks_for_chat(text, chat_id)
    try:
        reply = generate_reply(
            api_key=cfg.openai_api_key,
            model=cfg.model,
            history=history,
            user_text=text,
            context_blocks=context_blocks,
        )
        return reply, "chat", True
    except requests.HTTPError:
        return local.text, ("chat_local_fallback" if local.answered else "chat_unhandled"), False
    except Exception:
        return local.text, ("chat_local_fallback" if local.answered else "chat_unhandled"), False


def _process_update(
    *,
    cfg: TelegramBridgeConfig,
    state: dict[str, Any],
    update: dict[str, Any],
    running_jobs: dict[int, dict[str, Any]],
) -> None:
    message = _extract_message(update)
    if not message:
        return
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if cfg.allowed_chat_ids and chat_id not in cfg.allowed_chat_ids:
        return

    text = str(message.get("text", "")).strip()
    if not text:
        return

    _touch_state_timestamp(state, "last_incoming_at")
    append_message_log(cfg.message_log_path, direction="in", chat_id=chat_id, text=text)

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _route_message,
                cfg=cfg,
                state=state,
                chat_id=chat_id,
                text=text,
                running_jobs=running_jobs,
            )
            reply, tool_name, used_model = future.result(timeout=REPLY_TIMEOUT_SECONDS)
    except FutureTimeout:
        _touch_state_timestamp(state, "last_error_at")
        reply = (
            "응답이 지연되고 있습니다.\n"
            "종목 질의는 6자리 종목코드로 다시 요청해 주세요.\n"
            "예: `034220 왜 HOLD야?`, `068270 정보`"
        )
        tool_name = "timeout"
        used_model = False
        append_unhandled_log(
            cfg.unhandled_log_path,
            chat_id=chat_id,
            text=text,
            reason="timeout",
            tool_name=tool_name,
        )
    except Exception:
        traceback.print_exc()
        _touch_state_timestamp(state, "last_error_at")
        reply = "요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        tool_name = "handler_error"
        used_model = False
        append_unhandled_log(
            cfg.unhandled_log_path,
            chat_id=chat_id,
            text=text,
            reason="exception",
            tool_name=tool_name,
        )

    if tool_name == "chat_unhandled":
        append_unhandled_log(
            cfg.unhandled_log_path,
            chat_id=chat_id,
            text=text,
            reason="no_local_route",
            tool_name=tool_name,
        )

    sent_ok = _safe_send_text(
        cfg,
        state,
        chat_id=chat_id,
        text=reply,
        error_action="chat_reply",
    )
    if sent_ok:
        append_message_log(
            cfg.message_log_path,
            direction="out",
            chat_id=chat_id,
            text=reply,
            intent=tool_name,
            used_model=used_model,
            tool_name=tool_name,
        )
    if state.get("shutdown_after_reply"):
        state["shutdown_after_reply"] = False
        save_state(cfg.state_path, state)
        raise SystemExit(0)


def _check_running_jobs(cfg: TelegramBridgeConfig, state: dict[str, Any], running_jobs: dict[int, dict[str, Any]]) -> None:
    finished: list[int] = []
    for job_id, job in running_jobs.items():
        proc = job["process"]
        return_code = proc.poll()
        if return_code is None:
            continue
        log_handle = job.get("log_handle")
        if log_handle:
            log_handle.close()
        log_path = Path(job["log_path"])
        tail = read_log_tail(log_path, max_lines=15)
        action = str(job.get("action") or "")
        action_label_map = {
            "run_fast_alert": "fast alert",
            "run_refresh_data": "증분최신화",
            "run_refresh_incremental": "증분최신화",
            "run_refresh_full": "전체증분최신화",
            "run_refresh_full_incremental": "전체증분최신화",
            "run_streamlit_on": "스트림릿 실행",
            "run_streamlit_off": "스트림릿 종료",
            "run_bridge_off": "브리지 종료",
        }
        action_label = action_label_map.get(action, str(job.get("summary") or "작업").strip())
        if return_code == 0:
            reply = f"job_id={job_id} {action_label} 완료"
            status = "finished"
            error = ""
        else:
            short_error = (tail or "").strip().splitlines()[-1].strip() if str(tail or "").strip() else ""
            reply = f"job_id={job_id} {action_label} 실패"
            if short_error:
                reply = f"{reply}\n{short_error[:180]}"
            status = "failed"
            error = tail
            _touch_state_timestamp(state, "last_error_at")
        progress_run_id = str(job.get("progress_run_id") or "").strip()
        if progress_run_id:
            finished_at = datetime.now().isoformat(timespec="seconds")
            started_at = str(job.get("started_at") or finished_at)
            try:
                duration_seconds = int((datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds())
            except Exception:
                duration_seconds = 0
            progress_status = "completed" if return_code == 0 else "failed"
            progress_detail = "completed" if return_code == 0 else (tail or "failed")
            try:
                existing = json.loads(PIPELINE_PROGRESS_PATH.read_text(encoding="utf-8")) if PIPELINE_PROGRESS_PATH.exists() else {}
            except Exception:
                existing = {}
            if str(existing.get("run_id") or "") == progress_run_id:
                payload = dict(existing)
                payload.update(
                    {
                        "updated_at": finished_at,
                        "finished_at": finished_at,
                        "status": progress_status,
                        "percent": 100 if return_code == 0 else int(existing.get("percent") or 0),
                        "stage": "completed" if return_code == 0 else "failed",
                        "detail": progress_detail,
                        "duration_seconds": duration_seconds,
                        "source": "telegram",
                        "job_id": str(job_id),
                    }
                )
                _write_shared_pipeline_progress(payload)
        sent_ok = _safe_send_text(
            cfg,
            state,
            chat_id=str(job["chat_id"]),
            text=reply,
            error_action="job_result",
        )
        if sent_ok:
            append_message_log(
                cfg.message_log_path,
                direction="out",
                chat_id=str(job["chat_id"]),
                text=reply,
                intent="job_result",
                used_model=False,
                tool_name="job_result",
                job_id=str(job_id),
            )
        append_job_log(
            cfg.job_log_path,
            job_id=job_id,
            chat_id=str(job["chat_id"]),
            action=str(job["action"]),
            status=status if sent_ok else f"{status}_notify_failed",
            summary=str(job["summary"]),
            log_path=str(log_path),
            return_code=str(return_code),
            error=error if sent_ok else "\n".join(filter(None, [error, str(state.get("last_error_message", ""))])),
        )
        finished.append(job_id)
    for job_id in finished:
        running_jobs.pop(job_id, None)
    if finished:
        save_state(cfg.state_path, state)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Telegram bridge.")
    parser.add_argument("--once", action="store_true", help="Poll once and process available messages, then exit.")
    parser.add_argument(
        "--consume-backlog",
        action="store_true",
        help="On first run, process existing Telegram backlog instead of skipping to the latest offset.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_bridge_config()
    if not cfg.bot_token:
        raise SystemExit("NEW_STRATEGY_TELEGRAM_BOT_TOKEN is missing")

    state = load_state(cfg.state_path)
    running_jobs: dict[int, dict[str, Any]] = {}

    if state.get("offset") is None and not args.consume_backlog:
        try:
            bootstrap_updates = get_updates(cfg.bot_token, offset=None, timeout=1)
            if bootstrap_updates:
                state["offset"] = int(bootstrap_updates[-1]["update_id"]) + 1
                save_state(cfg.state_path, state)
        except requests.RequestException:
            pass

    while True:
        _touch_state_timestamp(state, "last_loop_at")
        _check_running_jobs(cfg, state, running_jobs)
        try:
            _maybe_send_early_session_brief(cfg, state)
        except requests.RequestException:
            _touch_state_timestamp(state, "last_error_at")
            save_state(cfg.state_path, state)
            pass
        try:
            updates = get_updates(cfg.bot_token, offset=state.get("offset"), timeout=20)
        except requests.RequestException:
            _touch_state_timestamp(state, "last_error_at")
            save_state(cfg.state_path, state)
            time.sleep(cfg.poll_seconds)
            continue

        for update in updates:
            try:
                _process_update(cfg=cfg, state=state, update=update, running_jobs=running_jobs)
                state["offset"] = int(update["update_id"]) + 1
                save_state(cfg.state_path, state)
            except SystemExit:
                raise
            except Exception:
                traceback.print_exc()
                _touch_state_timestamp(state, "last_error_at")
                save_state(cfg.state_path, state)

        if args.once:
            _check_running_jobs(cfg, state, running_jobs)
            save_state(cfg.state_path, state)
            break

        save_state(cfg.state_path, state)
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    main()
