from __future__ import annotations

import argparse
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from new_strategy.telegram_bridge_config import TelegramBridgeConfig, load_bridge_config
from new_strategy.telegram_bridge_memory import (
    append_job_log,
    append_message_log,
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
    record_manual_trade_text,
    recent_alerts_text,
    recent_trades_text,
    regime_explain_text,
    signal_detail_text,
    start_job,
    tomorrow_plan_text,
    unhandled_requests_text,
    why_no_buy_text,
)


REPLY_TIMEOUT_SECONDS = 8


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


def send_text(bot_token: str, chat_id: str, text: str) -> None:
    _telegram_api(bot_token, "sendMessage", {"chat_id": chat_id, "text": text})


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
        "signal_query": lambda: latest_signals_text(),
        "tomorrow_query": tomorrow_plan_text,
        "buy_query": lambda: latest_signals_text(signal_filter="BUY"),
        "sell_query": lambda: latest_signals_text(signal_filter="SELL"),
        "hold_query": lambda: latest_signals_text(signal_filter="HOLD"),
        "watch_query": lambda: latest_signals_text(signal_filter="WATCH"),
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
    proc, log_handle = start_job(job_spec, log_path)
    running_jobs[job_id] = {
        "process": proc,
        "log_handle": log_handle,
        "chat_id": chat_id,
        "job_id": job_id,
        "action": job_spec.action,
        "summary": job_spec.summary,
        "log_path": str(log_path),
        "started_at": datetime.now().isoformat(),
    }
    append_job_log(
        cfg.job_log_path,
        job_id=job_id,
        chat_id=chat_id,
        action=job_spec.action,
        status="started",
        summary=job_spec.summary,
        command=" ".join(job_spec.command),
        log_path=str(log_path),
    )
    return "\n".join(
        [
            f"작업을 시작했습니다. job_id={job_id}",
            job_spec.summary,
            "백그라운드에서 실행하고 완료되면 결과를 다시 알려드립니다.",
        ]
    )


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

    if intent.name == "confirm_job":
        return _handle_confirmation(cfg=cfg, state=state, chat_id=chat_id, intent=intent, running_jobs=running_jobs), "confirm_job", False

    if intent.name == "reject_job":
        return _handle_rejection(cfg=cfg, state=state, chat_id=chat_id, intent=intent), "reject_job", False

    if intent.name == "confirm_latest":
        return _handle_latest_confirmation(cfg=cfg, state=state, chat_id=chat_id, running_jobs=running_jobs), "confirm_latest", False

    if intent.name == "reject_latest":
        return _handle_latest_rejection(cfg=cfg, state=state, chat_id=chat_id), "reject_latest", False

    if intent.name in {"run_fast_alert", "run_refresh_data", "run_refresh_full", "run_streamlit_on", "run_streamlit_off", "run_bridge_off"}:
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

    send_text(cfg.bot_token, chat_id, reply)
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


def _check_running_jobs(cfg: TelegramBridgeConfig, running_jobs: dict[int, dict[str, Any]]) -> None:
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
        if return_code == 0:
            reply = "\n".join([f"job_id={job_id} 완료", job["summary"], tail or "(로그 없음)"])
            status = "finished"
            error = ""
        else:
            reply = "\n".join([f"job_id={job_id} 실패", job["summary"], tail or "(로그 없음)"])
            status = "failed"
            error = tail
        send_text(cfg.bot_token, str(job["chat_id"]), reply)
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
            status=status,
            summary=str(job["summary"]),
            log_path=str(log_path),
            return_code=str(return_code),
            error=error,
        )
        finished.append(job_id)
    for job_id in finished:
        running_jobs.pop(job_id, None)


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
        _check_running_jobs(cfg, running_jobs)
        try:
            updates = get_updates(cfg.bot_token, offset=state.get("offset"), timeout=20)
        except requests.RequestException:
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

        if args.once:
            _check_running_jobs(cfg, running_jobs)
            break

        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    main()
