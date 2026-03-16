from __future__ import annotations

from typing import Any

import requests


SYSTEM_PROMPT = """You are the Telegram bridge assistant for a Korean quantitative investing tool.
You answer in concise Korean.
Priorities:
1. Use provided tool context first.
2. Be concrete and factual.
3. Do not claim actions were executed unless tool context says so.
4. If information is missing, say exactly what is missing.
5. Keep responses short enough for Telegram."""


def build_messages(history: list[dict[str, Any]], user_text: str, context_blocks: list[str]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context_blocks:
        context_text = "\n\n".join(context_blocks)
        messages.append({"role": "system", "content": f"Relevant local context:\n{context_text}"})
    for item in history:
        role = "assistant" if item.get("direction") == "out" else "user"
        text = str(item.get("text", "")).strip()
        if text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": user_text})
    return messages


def generate_reply(
    *,
    api_key: str,
    model: str,
    history: list[dict[str, Any]],
    user_text: str,
    context_blocks: list[str],
) -> str:
    if not api_key:
        return "OPENAI_API_KEY가 없어 자유대화 응답을 만들 수 없습니다. /status, /latest 같은 조회 명령은 계속 사용할 수 있습니다."

    payload = {
        "model": model,
        "messages": build_messages(history, user_text, context_blocks),
        "temperature": 0.2,
        "max_tokens": 500,
    }
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()
