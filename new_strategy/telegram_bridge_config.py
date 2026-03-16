from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from new_strategy.paths import output_path


def _parse_chat_ids(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class TelegramBridgeConfig:
    bot_token: str
    allowed_chat_ids: list[str]
    openai_api_key: str
    model: str
    poll_seconds: int
    history_turns: int
    bridge_dir: Path
    state_path: Path
    message_log_path: Path
    job_log_path: Path
    unhandled_log_path: Path
    jobs_dir: Path


def load_bridge_config() -> TelegramBridgeConfig:
    bridge_dir = output_path("strategy_v1", "telegram_bridge")
    bridge_dir.mkdir(parents=True, exist_ok=True)

    allowed = os.getenv("NEW_STRATEGY_TELEGRAM_BRIDGE_ALLOWED_CHAT_IDS", "").strip()
    if not allowed:
        allowed = os.getenv("NEW_STRATEGY_TELEGRAM_CHAT_ID", "").strip()

    cfg = TelegramBridgeConfig(
        bot_token=os.getenv("NEW_STRATEGY_TELEGRAM_BOT_TOKEN", "").strip(),
        allowed_chat_ids=_parse_chat_ids(allowed),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        model=os.getenv("NEW_STRATEGY_TELEGRAM_BRIDGE_MODEL", "gpt-4.1-mini").strip(),
        poll_seconds=max(2, int(os.getenv("NEW_STRATEGY_TELEGRAM_BRIDGE_POLL_SECONDS", "10"))),
        history_turns=max(2, int(os.getenv("NEW_STRATEGY_TELEGRAM_BRIDGE_HISTORY_TURNS", "12"))),
        bridge_dir=bridge_dir,
        state_path=bridge_dir / "telegram_bridge_state.json",
        message_log_path=bridge_dir / "telegram_bridge_message_log.csv",
        job_log_path=bridge_dir / "telegram_bridge_job_log.csv",
        unhandled_log_path=bridge_dir / "telegram_bridge_unhandled_log.csv",
        jobs_dir=bridge_dir / "jobs",
    )
    cfg.jobs_dir.mkdir(parents=True, exist_ok=True)
    return cfg
