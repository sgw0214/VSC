from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_STATE = {
    "offset": None,
    "next_job_id": 1000,
    "pending_confirmations": {},
    "pending_notes": {},
    "scheduled_briefs": {},
    "last_loop_at": "",
    "last_incoming_at": "",
    "last_outgoing_at": "",
    "last_error_at": "",
    "last_early_session_brief_at": "",
}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_STATE.copy()
    return {**DEFAULT_STATE, **json.loads(path.read_text(encoding="utf-8"))}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def reserve_job_id(state: dict[str, Any]) -> int:
    next_job_id = int(state.get("next_job_id", 1000))
    state["next_job_id"] = next_job_id + 1
    return next_job_id


def _append_csv(path: Path, row: dict[str, Any], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def append_message_log(
    path: Path,
    *,
    direction: str,
    chat_id: str,
    text: str,
    intent: str = "",
    used_model: bool = False,
    tool_name: str = "",
    job_id: str = "",
) -> None:
    row = {
        "created_at": datetime.now().isoformat(),
        "direction": direction,
        "chat_id": str(chat_id),
        "text": text,
        "intent": intent,
        "used_model": used_model,
        "tool_name": tool_name,
        "job_id": job_id,
    }
    _append_csv(
        path,
        row,
        ["created_at", "direction", "chat_id", "text", "intent", "used_model", "tool_name", "job_id"],
    )


def append_job_log(
    path: Path,
    *,
    job_id: int,
    chat_id: str,
    action: str,
    status: str,
    summary: str,
    command: str = "",
    log_path: str = "",
    return_code: str = "",
    error: str = "",
) -> None:
    row = {
        "created_at": datetime.now().isoformat(),
        "job_id": int(job_id),
        "chat_id": str(chat_id),
        "action": action,
        "status": status,
        "summary": summary,
        "command": command,
        "log_path": log_path,
        "return_code": return_code,
        "error": error,
    }
    _append_csv(
        path,
        row,
        ["created_at", "job_id", "chat_id", "action", "status", "summary", "command", "log_path", "return_code", "error"],
    )


def append_unhandled_log(
    path: Path,
    *,
    chat_id: str,
    text: str,
    reason: str,
    tool_name: str = "",
) -> None:
    row = {
        "created_at": datetime.now().isoformat(),
        "chat_id": str(chat_id),
        "text": text,
        "reason": reason,
        "tool_name": tool_name,
    }
    _append_csv(
        path,
        row,
        ["created_at", "chat_id", "text", "reason", "tool_name"],
    )


def append_note_log(
    path: Path,
    *,
    chat_id: str,
    text: str,
    note_type: str = "record",
) -> None:
    row = {
        "created_at": datetime.now().isoformat(),
        "chat_id": str(chat_id),
        "note_type": note_type,
        "text": text,
    }
    _append_csv(
        path,
        row,
        ["created_at", "chat_id", "note_type", "text"],
    )


def load_recent_messages(path: Path, chat_id: str, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype={"chat_id": str}, low_memory=False)
    if df.empty:
        return []
    view = df[df["chat_id"] == str(chat_id)].tail(limit)
    return view.to_dict(orient="records")


def load_recent_unhandled(path: Path, chat_id: str, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype={"chat_id": str}, low_memory=False)
    if df.empty:
        return []
    view = df[df["chat_id"] == str(chat_id)].tail(limit)
    return view.to_dict(orient="records")


def load_recent_notes(path: Path, chat_id: str, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype={"chat_id": str}, low_memory=False)
    if df.empty:
        return []
    view = df[df["chat_id"] == str(chat_id)].tail(limit)
    return view.to_dict(orient="records")
