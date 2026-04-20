from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
import pandas as pd

from new_strategy.price_level_map import build_price_level_map
from new_strategy.telegram_bridge_tools import (
    _count_signal,
    _current_price_payload,
    _market_state_label,
    _operating_intensity_label,
    _postclose_decision_latest_row,
    _postclose_operational_signal_df,
)


OUT_DIR = Path(r"E:\VSC\python\new_strategy\output\strategy_v2\telegram_bridge\brief_images")
FONT_REG = Path(r"C:\Windows\Fonts\malgun.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")

WIDTH = 1720
MARGIN = 40
HEADER_H = 210
ROW_H = 76


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REG), size=size)


def _text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, size: int = 22, bold: bool = False, fill: str = "#0f172a") -> None:
    draw.text(xy, text, font=_font(size, bold=bold), fill=fill)


def _rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, fill: str, outline: str = "#dbe3f0", width: int = 1, radius: int = 18) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _badge(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, bg: str, fg: str) -> tuple[int, int, int, int]:
    font = _font(19, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + 28
    h = bbox[3] - bbox[1] + 14
    box = (xy[0], xy[1], xy[0] + w, xy[1] + h)
    draw.rounded_rectangle(box, radius=14, fill=bg)
    draw.text((xy[0] + 14, xy[1] + 6), text, font=font, fill=fg)
    return box


def _action_palette(action: str) -> tuple[str, str]:
    if "留ㅻ룄" in action or "異뺤냼" in action:
        return "#fee2e2", "#b91c1c"
    if "蹂댁쑀" in action:
        return "#dbeafe", "#1d4ed8"
    return "#fef3c7", "#b45309"


def _holding_palette(kind: str) -> tuple[str, str]:
    if kind == "蹂댁쑀":
        return "#ecfeff", "#155e75"
    return "#f5f3ff", "#6d28d9"


def _safe_int_price(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"
    try:
        return f"{float(value):,.0f}"
    except Exception:
        return "-"


def _dist_text(current_price: float | None, ma_price: float | None, window: int | None, prefix: str) -> str:
    if current_price is None or ma_price is None or ma_price == 0 or window is None:
        return "-"
    dist = float(current_price) / float(ma_price) - 1.0
    return f"{prefix}{int(window)} {dist:+.1%}"


def _row_payload(row: pd.Series) -> dict[str, str]:
    code = str(row.get("code") or "").zfill(6)
    name = str(row.get("name") or code)
    is_holding = bool(row.get("is_real_holding", False))
    signal_ko = str(row.get("signal_ko") or row.get("display_signal") or row.get("signal") or "-")

    price_payload = _current_price_payload(code)
    current_price_num = price_payload.get("numeric")
    current_price = _safe_int_price(current_price_num)

    levels = build_price_level_map(code, buy_price=None)
    monthly_window = levels.get("monthly_window")
    monthly_ma_price = levels.get("monthly_ma_price")
    weekly_window = levels.get("weekly_window")
    weekly_ma_price = levels.get("weekly_ma_price")

    month_dist = _dist_text(current_price_num, monthly_ma_price, monthly_window, "??)
    week_dist = _dist_text(current_price_num, weekly_ma_price, weekly_window, "二?)
    dist_text = f"{month_dist} / {week_dist}"

    if is_holding:
        price_ref = f"二?int(weekly_window) if weekly_window else '-'}??{_safe_int_price(weekly_ma_price)}"
        holding_text = "蹂댁쑀"
    else:
        buy_suggest = monthly_ma_price * 1.02 if monthly_ma_price not in (None, 0) else None
        price_ref = f"?쒖븞 {_safe_int_price(buy_suggest)}"
        holding_text = "?좉퇋"

    return {
        "holding": holding_text,
        "name": name,
        "code": code,
        "action": signal_ko,
        "current": current_price,
        "dist": dist_text,
        "price_ref": price_ref,
    }


def render_postclose_brief_image(chat_id: str = "") -> Path | None:
    df = _postclose_operational_signal_df(chat_id)
    if df.empty:
        return None

    decision = _postclose_decision_latest_row()
    counts = df["display_signal"].fillna("").astype(str).str.upper().value_counts().to_dict()

    rows = [_row_payload(row) for _, row in df.iterrows()]
    height = HEADER_H + 120 + len(rows) * ROW_H + 70

    img = Image.new("RGB", (WIDTH, height), "#f8fafc")
    draw = ImageDraw.Draw(img)

    _rounded(draw, (MARGIN, MARGIN, WIDTH - MARGIN, height - MARGIN), fill="#ffffff", outline="#e2e8f0", width=2, radius=28)
    _text(draw, (MARGIN + 30, MARGIN + 24), "?ν썑 釉뚮━??, size=42, bold=True)

    latest_date = "-"
    if "date" in df.columns:
        dt = pd.to_datetime(df["date"], errors="coerce").dropna()
        if not dt.empty:
            latest_date = str(dt.max().date())
    _text(draw, (MARGIN + 30, MARGIN + 80), f"湲곗???{latest_date} 쨌 ?듭씪 ?됰룞 ?뺣━", size=22, fill="#475569")

    market_label = _market_state_label(decision.get("market_regime")) if decision is not None else "unknown"
    exposure_label = "-"
    if decision is not None:
        try:
            exposure_label = _operating_intensity_label(float(decision.get("exposure", 0.0)))
        except Exception:
            exposure_label = "-"

    _badge(draw, (MARGIN + 30, MARGIN + 120), f"?쒖옣 {market_label}", bg="#fee2e2" if "諛⑹뼱" in market_label else "#ecfeff", fg="#b91c1c" if "諛⑹뼱" in market_label else "#155e75")
    _badge(draw, (MARGIN + 210, MARGIN + 120), f"?댁슜媛뺣룄 {exposure_label}", bg="#dbeafe", fg="#1d4ed8")
    _badge(
        draw,
        (MARGIN + 400, MARGIN + 120),
        f"蹂댁쑀 {_count_signal(counts, 'HOLD')} / 愿??{_count_signal(counts, 'BUY_WATCH')} / 異뺤냼 {_count_signal(counts, 'SELL_WATCH')} / 留ㅻ룄 {_count_signal(counts, 'SELL')}",
        bg="#f8fafc",
        fg="#334155",
    )

    table_x = MARGIN + 30
    table_y = HEADER_H
    table_w = WIDTH - MARGIN * 2 - 60
    col_widths = [120, 290, 250, 180, 430, table_w - 120 - 290 - 250 - 180 - 430]
    headers = ["援щ텇", "醫낅ぉ", "?≪뀡", "?꾩옱媛", "??二??닿꺽瑜?, "媛寃?湲곗?"]

    x = table_x
    for header, col_w in zip(headers, col_widths):
        _rounded(draw, (x, table_y, x + col_w - 8, table_y + 54), fill="#f8fafc", outline="#e2e8f0", width=1, radius=14)
        _text(draw, (x + 14, table_y + 13), header, size=22, bold=True)
        x += col_w

    start_y = table_y + 68
    for idx, row in enumerate(rows):
        y0 = start_y + idx * ROW_H
        y1 = y0 + ROW_H - 10
        _rounded(draw, (table_x, y0, table_x + table_w - 8, y1), fill="#ffffff", outline="#e5e7eb", width=1, radius=14)

        x = table_x
        hbg, hfg = _holding_palette(row["holding"])
        abg, afg = _action_palette(row["action"])
        _badge(draw, (x + 10, y0 + 18), row["holding"], bg=hbg, fg=hfg)
        x += col_widths[0]
        _text(draw, (x + 12, y0 + 14), row["name"], size=23, bold=True)
        _text(draw, (x + 12, y0 + 42), row["code"], size=16, fill="#64748b")
        x += col_widths[1]
        _badge(draw, (x + 10, y0 + 18), row["action"], bg=abg, fg=afg)
        x += col_widths[2]
        _text(draw, (x + 12, y0 + 22), row["current"], size=23, bold=True)
        x += col_widths[3]
        _text(draw, (x + 12, y0 + 22), row["dist"], size=21, fill="#0f172a")
        x += col_widths[4]
        _text(draw, (x + 12, y0 + 22), row["price_ref"], size=21, fill="#0f172a")

    note_y = start_y + len(rows) * ROW_H + 10
    _text(
        draw,
        (table_x, note_y),
        "留ㅼ닔?쒖븞媛 = 理쒖쟻 ?붿씠?됱꽑 횞 1.02",
        size=18,
        fill="#64748b",
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"postclose_brief_{latest_date.replace('-', '') or 'latest'}.png"
    img.save(out)
    return out


