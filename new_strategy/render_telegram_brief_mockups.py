from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path(r"C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\telegram_bridge\mockups")
FONT_REG = Path(r"C:\Windows\Fonts\malgun.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")

WIDTH = 1600
HEIGHT = 960
MARGIN = 42
CARD_RADIUS = 22


def fnt(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REG), size=size)


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, *, size: int = 24, bold: bool = False, fill: str = "#0f172a") -> None:
    draw.text(xy, value, font=fnt(size, bold=bold), fill=fill)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, fill: str, outline: str = "#dbe3f0", width: int = 1, radius: int = CARD_RADIUS) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def badge(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, bg: str, fg: str) -> tuple[int, int, int, int]:
    font_obj = fnt(19, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font_obj)
    w = bbox[2] - bbox[0] + 28
    h = bbox[3] - bbox[1] + 16
    box = (xy[0], xy[1], xy[0] + w, xy[1] + h)
    draw.rounded_rectangle(box, radius=16, fill=bg)
    draw.text((xy[0] + 14, xy[1] + 8), text, font=font_obj, fill=fg)
    return box


def action_palette(action: str) -> tuple[str, str]:
    if "매도" in action or "축소" in action:
        return "#fee2e2", "#b91c1c"
    if "보유" in action:
        return "#dbeafe", "#1d4ed8"
    return "#fef3c7", "#b45309"


def holding_palette(kind: str) -> tuple[str, str]:
    if kind == "보유":
        return "#ecfeff", "#155e75"
    return "#f5f3ff", "#6d28d9"


def mock_rows(kind: str) -> list[dict[str, str]]:
    if kind == "premarket":
        return [
            {"holding": "보유", "name": "신영증권", "action": "보유유지", "current": "201,500", "dist": "월 +189.2% / 주 +86.9%", "price_ref": "주106선 108,300"},
            {"holding": "보유", "name": "LG전자", "action": "소액매도검토", "current": "113,000", "dist": "월 +17.0% / 주 -6.8%", "price_ref": "주7선 121,400"},
            {"holding": "신규", "name": "덴티움", "action": "소액매수검토", "current": "53,800", "dist": "월 +7.3% / 주 +2.6%", "price_ref": "제안 53,800(예시)"},
            {"holding": "신규", "name": "동서", "action": "소액매수검토", "current": "27,250", "dist": "월 +1.8% / 주 +6.8%", "price_ref": "제안 27,250(예시)"},
        ]
    if kind == "open":
        return [
            {"holding": "보유", "name": "신영증권", "action": "보유유지", "current": "203,200", "dist": "월 +190.5% / 주 +84.1%", "price_ref": "주106선 110,100"},
            {"holding": "보유", "name": "LG전자", "action": "소액매도검토", "current": "111,900", "dist": "월 +15.4% / 주 -7.5%", "price_ref": "주7선 120,900"},
            {"holding": "신규", "name": "덴티움", "action": "소액매수검토", "current": "54,100", "dist": "월 +6.9% / 주 +3.1%", "price_ref": "제안 54,100(예시)"},
        ]
    return [
        {"holding": "보유", "name": "신영증권", "action": "익일보유", "current": "201,500", "dist": "월 +189.2% / 주 +86.9%", "price_ref": "주106선 108,300"},
        {"holding": "보유", "name": "LG전자", "action": "익일소액매도검토", "current": "113,000", "dist": "월 +17.0% / 주 -6.8%", "price_ref": "주7선 121,400"},
        {"holding": "신규", "name": "덴티움", "action": "익일관심유지", "current": "53,800", "dist": "월 +7.3% / 주 +2.6%", "price_ref": "제안 53,800(예시)"},
        {"holding": "신규", "name": "동서", "action": "익일관심유지", "current": "27,250", "dist": "월 +1.8% / 주 +6.8%", "price_ref": "제안 27,250(예시)"},
    ]


def render(kind: str, title: str, subline: str, footer: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (WIDTH, HEIGHT), "#f8fafc")
    draw = ImageDraw.Draw(img)

    rounded(draw, (MARGIN, MARGIN, WIDTH - MARGIN, HEIGHT - MARGIN), fill="#ffffff", outline="#e2e8f0", width=2, radius=28)
    draw_text(draw, (MARGIN + 30, MARGIN + 26), title, size=40, bold=True)
    draw_text(draw, (MARGIN + 30, MARGIN + 82), subline, size=21, fill="#475569")

    badge(draw, (MARGIN + 30, MARGIN + 124), "시장 방어구간", bg="#fee2e2", fg="#b91c1c")
    badge(draw, (MARGIN + 210, MARGIN + 124), "운용강도 40%", bg="#dbeafe", fg="#1d4ed8")

    table_x = MARGIN + 30
    table_y = MARGIN + 190
    table_w = WIDTH - MARGIN * 2 - 60
    col_widths = [140, 240, 250, 180, 360, table_w - 140 - 240 - 250 - 180 - 360]
    headers = ["구분", "종목", "액션", "현재가", "월/주 이격률", "가격 기준"]

    x = table_x
    for header, cw in zip(headers, col_widths):
        rounded(draw, (x, table_y, x + cw - 8, table_y + 58), fill="#f8fafc", outline="#e2e8f0", width=1, radius=14)
        draw_text(draw, (x + 16, table_y + 14), header, size=23, bold=True)
        x += cw

    row_h = 92
    start_y = table_y + 74
    rows = mock_rows(kind)
    for idx, row in enumerate(rows):
        y0 = start_y + idx * row_h
        y1 = y0 + row_h - 12
        rounded(draw, (table_x, y0, table_x + table_w - 8, y1), fill="#ffffff", outline="#e5e7eb", width=1, radius=14)

        x = table_x
        hbg, hfg = holding_palette(row["holding"])
        abg, afg = action_palette(row["action"])
        badge(draw, (x + 12, y0 + 24), row["holding"], bg=hbg, fg=hfg)
        x += col_widths[0]
        draw_text(draw, (x + 16, y0 + 27), row["name"], size=25, bold=True)
        x += col_widths[1]
        badge(draw, (x + 12, y0 + 24), row["action"], bg=abg, fg=afg)
        x += col_widths[2]
        draw_text(draw, (x + 16, y0 + 27), row["current"], size=25, bold=True)
        x += col_widths[3]
        draw_text(draw, (x + 16, y0 + 27), row["dist"], size=22, bold=False)
        x += col_widths[4]
        draw_text(draw, (x + 16, y0 + 27), row["price_ref"], size=22, bold=False)

    note_y = start_y + len(rows) * row_h + 14
    rounded(draw, (table_x, note_y, table_x + table_w - 8, note_y + 86), fill="#f8fafc", outline="#e5e7eb", width=1, radius=14)
    draw_text(draw, (table_x + 18, note_y + 16), "메모", size=20, bold=True)
    draw_text(draw, (table_x + 18, note_y + 46), "매수제안가는 현재 mockup 예시값입니다. 실제 적용 시 가격 규칙 산식으로 별도 정의가 필요합니다.", size=18, fill="#475569")

    draw_text(draw, (table_x, HEIGHT - MARGIN - 34), footer, size=17, fill="#64748b")

    out = OUT_DIR / f"telegram_brief_mockup_{kind}.png"
    img.save(out)
    return out


def main() -> None:
    paths = [
        render("premarket", "프리장 브리핑 시안", "오늘 아침 우선순위를 바로 읽는 간단 표형 시안", "프리장: 보유 점검과 신규 관심만 우선 확인"),
        render("open", "본장 브리핑 시안", "장 시작 후 즉시 대응 대상을 정리하는 간단 표형 시안", "본장: 보유/축소 우선, 신규는 과열 확인"),
        render("postclose", "장후 브리핑 시안", "내일 기준 행동을 정리하는 익일 표형 시안", "장후: 익일보유 / 익일관심 / 익일소액매도 정리"),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
