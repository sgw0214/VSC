from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd
import requests


@dataclass
class AlertEvent:
    event_type: str
    event_time: datetime
    signal_date: str
    code: str
    name: str
    signal: str
    strategy_id: str
    conviction_score: float
    message: str

    @property
    def dedupe_key(self) -> str:
        return "|".join([self.signal_date, self.event_type, self.signal, self.code, self.strategy_id])


class BaseNotifier:
    channel = "base"

    def is_configured(self) -> bool:
        return False

    def send(self, title: str, message: str) -> None:
        raise NotImplementedError


class TelegramNotifier(BaseNotifier):
    channel = "telegram"

    def __init__(self) -> None:
        self.bot_token = os.getenv("NEW_STRATEGY_TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("NEW_STRATEGY_TELEGRAM_CHAT_ID", "")

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, title: str, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        text = f"{title}\n{message}"
        resp = requests.post(url, json={"chat_id": self.chat_id, "text": text}, timeout=15)
        resp.raise_for_status()


class EmailNotifier(BaseNotifier):
    channel = "email"

    def __init__(self) -> None:
        self.smtp_host = os.getenv("NEW_STRATEGY_EMAIL_HOST", "")
        self.smtp_port = int(os.getenv("NEW_STRATEGY_EMAIL_PORT", "465"))
        self.username = os.getenv("NEW_STRATEGY_EMAIL_USERNAME", "")
        self.password = os.getenv("NEW_STRATEGY_EMAIL_PASSWORD", "")
        self.from_addr = os.getenv("NEW_STRATEGY_EMAIL_FROM", self.username)
        self.to_addr = os.getenv("NEW_STRATEGY_EMAIL_TO", "")

    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.username and self.password and self.to_addr)

    def send(self, title: str, message: str) -> None:
        msg = MIMEText(message, _charset="utf-8")
        msg["Subject"] = title
        msg["From"] = self.from_addr
        msg["To"] = self.to_addr
        with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=20) as server:
            server.login(self.username, self.password)
            server.send_message(msg)


def build_notifiers() -> List[BaseNotifier]:
    available = {
        "telegram": TelegramNotifier(),
        "email": EmailNotifier(),
    }
    preferred = os.getenv("NEW_STRATEGY_NOTIFIER_CHANNELS", "").strip()
    if preferred:
        ordered_names = [name.strip().lower() for name in preferred.split(",") if name.strip()]
    else:
        ordered_names = ["telegram", "email"]
    out: List[BaseNotifier] = []
    for name in ordered_names:
        notifier = available.get(name)
        if notifier and notifier.is_configured():
            out.append(notifier)
    if preferred:
        return out
    for name, notifier in available.items():
        if name not in ordered_names and notifier.is_configured():
            out.append(notifier)
    return out


def load_alert_log(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "sent_at",
                "event_type",
                "signal_date",
                "code",
                "name",
                "signal",
                "strategy_id",
                "channel",
                "dedupe_key",
                "success",
                "error",
                "conviction_score",
            ]
        )
    df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    df["sent_at"] = pd.to_datetime(df["sent_at"], errors="coerce")
    return df


def filter_new_alerts(events: Iterable[AlertEvent], alert_log: pd.DataFrame) -> List[AlertEvent]:
    if alert_log.empty:
        return list(events)

    successful = alert_log.loc[alert_log["success"] == True].copy()
    dedupe_seen = set(successful["dedupe_key"].dropna().astype(str))
    latest_by_code_signal: Dict[str, pd.Timestamp] = {}
    for _, row in successful.dropna(subset=["sent_at"]).iterrows():
        key = f"{row['code']}|{row['signal']}|{row['event_type']}"
        latest_by_code_signal[key] = max(latest_by_code_signal.get(key, row["sent_at"]), row["sent_at"])

    out: List[AlertEvent] = []
    for event in events:
        if event.dedupe_key in dedupe_seen:
            continue
        cooldown = timedelta(hours=1) if event.event_type == "PRE_SIGNAL" else timedelta(days=1)
        key = f"{event.code}|{event.signal}|{event.event_type}"
        last_sent = latest_by_code_signal.get(key)
        if last_sent is not None and event.event_time - last_sent < cooldown:
            continue
        out.append(event)
    return out


def dispatch_alerts(events: Iterable[AlertEvent], notifiers: List[BaseNotifier], alert_log_path: Path) -> pd.DataFrame:
    alert_log = load_alert_log(alert_log_path)
    new_events = filter_new_alerts(events, alert_log)
    if not new_events or not notifiers:
        return alert_log

    rows = []
    for event in new_events:
        title = f"[{event.signal}] {event.name}({event.code})"
        for notifier in notifiers:
            success = True
            error = ""
            try:
                notifier.send(title, event.message)
            except Exception as exc:
                success = False
                error = str(exc)
            rows.append(
                {
                    "sent_at": event.event_time,
                    "event_type": event.event_type,
                    "signal_date": event.signal_date,
                    "code": event.code,
                    "name": event.name,
                    "signal": event.signal,
                    "strategy_id": event.strategy_id,
                    "channel": notifier.channel,
                    "dedupe_key": event.dedupe_key,
                    "success": success,
                    "error": error,
                    "conviction_score": event.conviction_score,
                }
            )
    merged = pd.concat([alert_log, pd.DataFrame(rows)], ignore_index=True)
    merged.to_csv(alert_log_path, index=False, encoding="utf-8-sig")
    return merged
