from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from new_strategy.paths import data_path, strategy_output_path


APP_DIR = strategy_output_path()
BRIDGE_DIR = APP_DIR / "telegram_bridge"
POSITIONS_PATH = BRIDGE_DIR / "manual_portfolio_positions.csv"
TRADES_PATH = BRIDGE_DIR / "manual_portfolio_trades.csv"
PRICE_SNAPSHOT_PATH = APP_DIR / "price_panel_latest_snapshot.csv"
STRATEGY_META_PATH = APP_DIR / "strategy_metadata.json"

_NUMERIC_CODE_RE = re.compile(r"^\d+$")
_TRADE_RE = re.compile(r"^\s*(매수|매도|buy|sell)(?:\s+|$)", flags=re.IGNORECASE)


@dataclass
class ParsedTrade:
    side: str
    code: str
    quantity: float
    price: float
    blocked_reason: str = ""


def normalize_code(code: str) -> str:
    raw = str(code or "").strip().upper()
    if _NUMERIC_CODE_RE.fullmatch(raw):
        return raw.zfill(6)
    return raw


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(str(value).replace(",", "").replace("원", "").replace("주", ""))
    except Exception:
        return None


def parse_trade_text(text: str) -> ParsedTrade | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    match = _TRADE_RE.match(raw)
    if not match:
        return None

    side_token = match.group(1)
    side = "BUY" if side_token.lower() in {"매수", "buy"} else "SELL"
    remainder = raw[match.end():].strip()
    if not remainder:
        return None

    parts = remainder.split()
    if len(parts) < 3:
        return None

    price = _safe_float(parts[-2])
    quantity = _safe_float(parts[-1])
    if price is None or quantity is None or quantity <= 0 or price <= 0:
        return None

    code_token = " ".join(parts[:-2]).strip()
    if not code_token:
        return None

    code = normalize_code(code_token)
    if not (_NUMERIC_CODE_RE.fullmatch(code) or (len(code) == 6 and code.isalnum())):
        latest = _latest_signal_df()
        price_df = _get_latest_price_snapshot()
        universe = pd.concat([latest[["code", "name"]], price_df[["code", "name"]]], ignore_index=True) if (not latest.empty or not price_df.empty) else pd.DataFrame(columns=["code", "name"])
        if not universe.empty:
            names = universe["name"].astype(str).str.replace(" ", "", regex=False)
            target = str(code_token).strip().replace(" ", "")
            hit = universe[names == target]
            if hit.empty:
                hit = universe[names.str.contains(re.escape(target), na=False)]
            if not hit.empty:
                hit = hit.drop_duplicates(subset=["code"]).sort_values(["code"])
                code = normalize_code(str(hit.iloc[0]["code"]))
            else:
                return None

    if not quantity or not price or quantity <= 0 or price <= 0:
        return None
    name = _lookup_name(code)
    blocked_reason = _trade_guard_reason(side, code, name, price, quantity)
    return ParsedTrade(side=side, code=code, quantity=quantity, price=price, blocked_reason=blocked_reason)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_positions() -> pd.DataFrame:
    columns = ["chat_id", "code", "name", "quantity", "avg_price", "realized_pnl", "last_trade_at", "updated_at"]
    if not POSITIONS_PATH.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(POSITIONS_PATH, dtype={"chat_id": str, "code": str}, low_memory=False)
    for col in ["quantity", "avg_price", "realized_pnl"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "code" in df.columns:
        df["code"] = df["code"].astype(str).map(normalize_code)
    return df


def _read_trades() -> pd.DataFrame:
    columns = [
        "created_at",
        "chat_id",
        "side",
        "code",
        "name",
        "quantity",
        "price",
        "avg_price_before",
        "avg_price_after",
        "realized_pnl",
    ]
    if not TRADES_PATH.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(TRADES_PATH, dtype={"chat_id": str, "code": str}, low_memory=False)
    for col in ["quantity", "price", "avg_price_before", "avg_price_after", "realized_pnl"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "code" in df.columns:
        df["code"] = df["code"].astype(str).map(normalize_code)
    return df


def _latest_signal_df() -> pd.DataFrame:
    candidates = [APP_DIR / "signal_daily_fast_latest.csv", APP_DIR / "signal_daily_latest.csv"]
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return pd.DataFrame()
    latest_path = max(existing, key=lambda path: path.stat().st_mtime)
    df = pd.read_csv(latest_path, dtype={"code": str}, low_memory=False)
    if not df.empty:
        df["code"] = df["code"].astype(str).map(normalize_code)
    return df


def _get_latest_price_snapshot() -> pd.DataFrame:
    price_path = data_path("price_panel.csv")
    if not price_path.exists():
        return pd.DataFrame(columns=["code", "name", "date", "close"])
    if PRICE_SNAPSHOT_PATH.exists() and PRICE_SNAPSHOT_PATH.stat().st_mtime >= price_path.stat().st_mtime:
        df = pd.read_csv(PRICE_SNAPSHOT_PATH, dtype={"code": str}, low_memory=False)
        if not df.empty:
            df["code"] = df["code"].astype(str).map(normalize_code)
        return df

    df = pd.read_csv(price_path, usecols=["code", "name", "date", "close"], dtype={"code": str}, low_memory=False)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["code", "date"])
    latest = df.groupby("code", as_index=False).tail(1).copy()
    latest["code"] = latest["code"].astype(str).map(normalize_code)
    latest.to_csv(PRICE_SNAPSHOT_PATH, index=False, encoding="utf-8-sig")
    return latest


def _lookup_name(code: str) -> str:
    norm = normalize_code(code)
    for df in (_latest_signal_df(), _get_latest_price_snapshot()):
        if not df.empty:
            hit = df[df["code"] == norm]
            if not hit.empty and "name" in hit.columns:
                return str(hit.iloc[0]["name"])
    return norm


def _lookup_reference_price(code: str) -> float | None:
    norm = normalize_code(code)
    price_df = _get_latest_price_snapshot()
    if price_df.empty:
        return None
    hit = price_df[price_df["code"] == norm]
    if hit.empty or pd.isna(hit.iloc[0].get("close")):
        return None
    return float(hit.iloc[0]["close"])


def _is_integer_like(value: float) -> bool:
    return abs(value - round(value)) < 1e-9


def _trade_guard_reason(side: str, code: str, name: str, price: float, quantity: float) -> str:
    reference_price = _lookup_reference_price(code)
    if reference_price is None:
        return ""

    entered_gap = abs(price / reference_price - 1.0)
    swapped_price = quantity
    swapped_qty = price
    swapped_gap = abs(swapped_price / reference_price - 1.0) if swapped_price > 0 else float("inf")

    looks_swapped = (
        entered_gap >= 0.80
        and swapped_gap <= 0.30
        and quantity >= 100
        and _is_integer_like(swapped_qty)
        and swapped_qty >= 1
    )
    if not looks_swapped:
        return ""

    side_label = "매수" if side == "BUY" else "매도"
    return (
        f"{name}({code}) 입력을 그대로 해석하면 가격 {price:,.0f}원, 수량 {quantity:,.0f}주입니다.\n"
        f"- 최근 기준가: {reference_price:,.0f}원\n"
        f"- 가격과 수량 순서가 바뀐 것으로 보입니다.\n"
        f"- 다시 입력: `{side_label} {name} {swapped_price:,.0f} {int(round(swapped_qty))}`"
    )


def record_manual_trade(chat_id: str, parsed: ParsedTrade) -> str:
    if parsed.blocked_reason:
        return parsed.blocked_reason

    positions = _read_positions()
    code = normalize_code(parsed.code)
    name = _lookup_name(code)
    now = datetime.now().isoformat(timespec="seconds")

    mask = (positions.get("chat_id", pd.Series(dtype=str)).astype(str) == str(chat_id)) & (positions.get("code", pd.Series(dtype=str)) == code)
    exists = bool(mask.any()) if not positions.empty else False

    quantity_before = 0.0
    avg_before = 0.0
    realized_before = 0.0
    if exists:
        row = positions.loc[mask].iloc[0]
        quantity_before = float(row["quantity"])
        avg_before = float(row["avg_price"])
        realized_before = float(row.get("realized_pnl", 0.0))

    realized_trade = 0.0
    if parsed.side == "BUY":
        quantity_after = quantity_before + parsed.quantity
        avg_after = ((quantity_before * avg_before) + (parsed.quantity * parsed.price)) / quantity_after if quantity_after > 0 else 0.0
        realized_after = realized_before
    else:
        if quantity_before <= 0:
            return f"{name}({code})는 현재 실보유 수량이 없어 매도 기록을 남길 수 없습니다."
        if parsed.quantity > quantity_before + 1e-9:
            return f"{name}({code}) 보유 수량은 {quantity_before:g}주입니다. 그보다 많이 매도할 수 없습니다."
        quantity_after = quantity_before - parsed.quantity
        avg_after = avg_before if quantity_after > 0 else 0.0
        realized_trade = (parsed.price - avg_before) * parsed.quantity
        realized_after = realized_before + realized_trade

    updated_row = {
        "chat_id": str(chat_id),
        "code": code,
        "name": name,
        "quantity": round(quantity_after, 6),
        "avg_price": round(avg_after, 6),
        "realized_pnl": round(realized_after, 6),
        "last_trade_at": now,
        "updated_at": now,
    }

    if exists:
        positions = positions.loc[~mask].copy()
    if quantity_after > 0:
        positions = pd.concat([positions, pd.DataFrame([updated_row])], ignore_index=True)
    positions = positions.sort_values(["chat_id", "code"]).reset_index(drop=True)
    _write_csv(POSITIONS_PATH, list(updated_row.keys()), positions.to_dict(orient="records"))

    trades = _read_trades()
    trade_row = {
        "created_at": now,
        "chat_id": str(chat_id),
        "side": parsed.side,
        "code": code,
        "name": name,
        "quantity": round(parsed.quantity, 6),
        "price": round(parsed.price, 6),
        "avg_price_before": round(avg_before, 6),
        "avg_price_after": round(avg_after, 6),
        "realized_pnl": round(realized_trade, 6),
    }
    trades = pd.concat([trades, pd.DataFrame([trade_row])], ignore_index=True)
    _write_csv(TRADES_PATH, list(trade_row.keys()), trades.to_dict(orient="records"))

    side_label = "매수" if parsed.side == "BUY" else "매도"
    lines = [
        f"{name}({code}) {side_label} 기록을 저장했습니다.",
        f"- 수량: {parsed.quantity:g}주",
        f"- 가격: {parsed.price:,.0f}원",
        f"- 보유 수량: {quantity_after:g}주",
    ]
    if quantity_after > 0:
        lines.append(f"- 평균단가: {avg_after:,.0f}원")
    else:
        lines.append("- 평균단가: 없음")
    if parsed.side == "SELL":
        lines.append(f"- 이번 실현손익: {realized_trade:,.0f}원")
        lines.append(f"- 누적 실현손익: {realized_after:,.0f}원")
    return "\n".join(lines)


def _read_strategy_meta() -> dict[str, Any]:
    if not STRATEGY_META_PATH.exists():
        return {}
    try:
        return json.loads(STRATEGY_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _display_sell_threshold() -> float:
    meta = _read_strategy_meta()
    try:
        return float(meta.get("config", {}).get("sell_threshold", 0.35))
    except Exception:
        return 0.35


def _display_signal(signal: Any, conviction_score: Any, risk_flag: Any) -> str:
    signal_text = str(signal or "").upper()
    score = pd.to_numeric(pd.Series([conviction_score]), errors="coerce").iloc[0]
    risk_text = "" if pd.isna(risk_flag) else str(risk_flag).strip()
    if signal_text == "BUY":
        return "BUY"
    if signal_text == "SELL":
        return "SELL"
    if signal_text == "WATCH":
        return "BUY_WATCH"
    if signal_text == "HOLD" and (risk_text or (pd.notna(score) and float(score) <= (_display_sell_threshold() + 0.12))):
        return "SELL_WATCH"
    return "HOLD"


def _signal_label(signal: Any) -> str:
    mapping = {
        "BUY": "매수",
        "BUY_WATCH": "소액매수검토",
        "HOLD": "보유유지",
        "SELL_WATCH": "비중축소검토",
        "SELL": "매도",
    }
    return mapping.get(str(signal or "").upper(), str(signal or "n/a"))


def portfolio_snapshot(chat_id: str) -> pd.DataFrame:
    positions = _read_positions()
    if positions.empty:
        return positions
    positions = positions[positions["chat_id"].astype(str) == str(chat_id)].copy()
    positions = positions[positions["quantity"] > 0].copy()
    if positions.empty:
        return positions

    prices = _get_latest_price_snapshot()
    if not prices.empty:
        positions = positions.merge(prices[["code", "date", "close"]], on="code", how="left")
    else:
        positions["date"] = pd.NaT
        positions["close"] = pd.NA

    signals = _latest_signal_df()
    if not signals.empty:
        merge_cols = [col for col in ["code", "signal", "conviction_score", "reason_1", "reason_2", "reason_3", "risk_flag", "stop_rule", "target_exit_rule"] if col in signals.columns]
        positions = positions.merge(signals[merge_cols], on="code", how="left")
        positions["display_signal"] = positions.apply(
            lambda row: _display_signal(row.get("signal"), row.get("conviction_score"), row.get("risk_flag")),
            axis=1,
        )
    else:
        positions["display_signal"] = pd.NA

    positions["market_value"] = positions["quantity"] * pd.to_numeric(positions["close"], errors="coerce")
    positions["cost_value"] = positions["quantity"] * pd.to_numeric(positions["avg_price"], errors="coerce")
    positions["unrealized_pnl"] = positions["market_value"] - positions["cost_value"]
    positions["unrealized_return"] = positions["market_value"] / positions["cost_value"] - 1.0
    return positions.sort_values(["code"]).reset_index(drop=True)


def portfolio_summary_text(chat_id: str) -> str:
    snap = portfolio_snapshot(chat_id)
    if snap.empty:
        return "실보유 종목이 없습니다."

    total_cost = pd.to_numeric(snap["cost_value"], errors="coerce").sum()
    total_value = pd.to_numeric(snap["market_value"], errors="coerce").sum()
    total_unrealized = pd.to_numeric(snap["unrealized_pnl"], errors="coerce").sum()
    total_realized = pd.to_numeric(snap["realized_pnl"], errors="coerce").sum()
    display_signal = snap.get("display_signal", snap.get("signal", pd.Series(dtype=str))).fillna("").astype(str).str.upper()
    sell_warn = int(display_signal.isin(["SELL", "SELL_WATCH"]).sum())

    lines = [
        f"실보유 {len(snap)}종목",
        f"- 매입금액: {total_cost:,.0f}원",
        f"- 평가금액: {total_value:,.0f}원" if pd.notna(total_value) else "- 평가금액: n/a",
        f"- 평가손익: {total_unrealized:,.0f}원" if pd.notna(total_unrealized) else "- 평가손익: n/a",
        f"- 누적 실현손익: {total_realized:,.0f}원",
        f"- 전략 매도/축소 신호: {sell_warn}종목",
    ]
    for _, row in snap.head(10).iterrows():
        now_price = "n/a" if pd.isna(row.get("close")) else f"{float(row['close']):,.0f}원"
        now_ret = "n/a" if pd.isna(row.get("unrealized_return")) else f"{float(row['unrealized_return']):+.2%}"
        signal = _signal_label(row.get("display_signal") or row.get("signal") or "n/a")
        lines.append(
            f"- {row['code']} {row['name']} | {float(row['quantity']):g}주 | 평균 {float(row['avg_price']):,.0f}원 | 현재 {now_price} | 수익률 {now_ret} | 전략신호 {signal}"
        )
    return "\n".join(lines)


def portfolio_status_line(chat_id: str) -> str:
    snap = portfolio_snapshot(chat_id)
    if snap.empty:
        return "실보유 없음"
    total_unrealized = pd.to_numeric(snap["unrealized_pnl"], errors="coerce").sum()
    display_signal = snap.get("display_signal", snap.get("signal", pd.Series(dtype=str))).fillna("").astype(str).str.upper()
    sell_warn = int(display_signal.isin(["SELL", "SELL_WATCH"]).sum())
    return f"실보유 {len(snap)}종목, 평가손익 {total_unrealized:,.0f}원, 전략 매도/축소 신호 {sell_warn}종목"


def manual_trade_history_text(chat_id: str, limit: int = 8) -> str:
    trades = _read_trades()
    if trades.empty:
        return "실거래 기록이 없습니다."
    trades = trades[trades["chat_id"].astype(str) == str(chat_id)].copy()
    if trades.empty:
        return "실거래 기록이 없습니다."
    trades = trades.sort_values("created_at", ascending=False).head(limit)
    lines = ["최근 실거래 기록"]
    for _, row in trades.iterrows():
        side = "매수" if str(row.get("side", "")).upper() == "BUY" else "매도"
        pnl = float(row.get("realized_pnl", 0.0))
        pnl_text = f", 실현손익 {pnl:,.0f}원" if side == "매도" else ""
        lines.append(
            f"- {row['created_at']} | {side} | {row['code']} {row['name']} | {float(row['quantity']):g}주 @ {float(row['price']):,.0f}원{pnl_text}"
        )
    return "\n".join(lines)


def position_detail_line(chat_id: str, code: str) -> str | None:
    snap = portfolio_snapshot(chat_id)
    if snap.empty:
        return None
    norm = normalize_code(code)
    hit = snap[snap["code"] == norm]
    if hit.empty:
        return None
    row = hit.iloc[0]
    current_price = "n/a" if pd.isna(row.get("close")) else f"{float(row['close']):,.0f}원"
    ret = "n/a" if pd.isna(row.get("unrealized_return")) else f"{float(row['unrealized_return']):+.2%}"
    pnl = "n/a" if pd.isna(row.get("unrealized_pnl")) else f"{float(row['unrealized_pnl']):,.0f}원"
    return (
        f"실보유 {float(row['quantity']):g}주, 평균단가 {float(row['avg_price']):,.0f}원, "
        f"현재 {current_price}, 평가손익 {pnl}, 수익률 {ret}"
    )
