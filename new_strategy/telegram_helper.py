from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

import requests


def get_updates(bot_token: str) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.json()


def extract_chats(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    chats: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("result", []):
        message = item.get("message") or item.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        chats[str(chat_id)] = {
            "chat_id": chat_id,
            "type": chat.get("type"),
            "title": chat.get("title") or "",
            "username": chat.get("username") or "",
            "first_name": chat.get("first_name") or "",
            "last_name": chat.get("last_name") or "",
        }
    return list(chats.values())


def send_message(bot_token: str, chat_id: str, text: str) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram helper for new_strategy.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_updates = sub.add_parser("get-updates", help="Fetch raw updates from Telegram Bot API.")
    p_updates.add_argument("--bot-token", default=os.getenv("NEW_STRATEGY_TELEGRAM_BOT_TOKEN", ""))

    p_chats = sub.add_parser("list-chats", help="List chat ids seen by the bot.")
    p_chats.add_argument("--bot-token", default=os.getenv("NEW_STRATEGY_TELEGRAM_BOT_TOKEN", ""))

    p_send = sub.add_parser("send-test", help="Send a test message.")
    p_send.add_argument("--bot-token", default=os.getenv("NEW_STRATEGY_TELEGRAM_BOT_TOKEN", ""))
    p_send.add_argument("--chat-id", default=os.getenv("NEW_STRATEGY_TELEGRAM_CHAT_ID", ""))
    p_send.add_argument("--text", default="new_strategy telegram test")

    p_env = sub.add_parser("show-env", help="Print PowerShell env commands.")
    p_env.add_argument("--bot-token", default=os.getenv("NEW_STRATEGY_TELEGRAM_BOT_TOKEN", ""))
    p_env.add_argument("--chat-id", default=os.getenv("NEW_STRATEGY_TELEGRAM_CHAT_ID", ""))

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "get-updates":
        if not args.bot_token:
            raise SystemExit("bot token is missing")
        print(json.dumps(get_updates(args.bot_token), ensure_ascii=False, indent=2))
        return

    if args.command == "list-chats":
        if not args.bot_token:
            raise SystemExit("bot token is missing")
        updates = get_updates(args.bot_token)
        print(json.dumps(extract_chats(updates), ensure_ascii=False, indent=2))
        return

    if args.command == "send-test":
        if not args.bot_token:
            raise SystemExit("bot token is missing")
        if not args.chat_id:
            raise SystemExit("chat id is missing")
        print(json.dumps(send_message(args.bot_token, args.chat_id, args.text), ensure_ascii=False, indent=2))
        return

    if args.command == "show-env":
        if args.bot_token:
            print(f"$env:NEW_STRATEGY_TELEGRAM_BOT_TOKEN=\"{args.bot_token}\"")
        if args.chat_id:
            print(f"$env:NEW_STRATEGY_TELEGRAM_CHAT_ID=\"{args.chat_id}\"")
        print("$env:NEW_STRATEGY_NOTIFIER_CHANNELS=\"telegram\"")


if __name__ == "__main__":
    main()
