from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path(r"E:\VSC\python\new_strategy\output\strategy_v2\telegram_bridge\mockups")
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
    if "留ㅻ룄" in action or "異뺤냼" in action:
        return "#fee2e2", "#b91c1c"
    if "蹂댁쑀" in action:
        return "#dbeafe", "#1d4ed8"
    return "#fef3c7", "#b45309"


def holding_palette(kind: str) -> tuple[str, str]:
    if kind == "蹂댁쑀":
        return "#ecfeff", "#155e75"
    return "#f5f3ff", "#6d28d9"


def mock_rows(kind: str) -> list[dict[str, str]]:
    if kind == "premarket":
        return [
            {"holding": "蹂댁쑀", "name": "?좎쁺利앷텒", "action": "蹂댁쑀?좎?", "current": "201,500", "dist": "??+189.2% / 二?+86.9%", "price_ref": "二?06??108,300"},
            {"holding": "蹂댁쑀", "name": "LG?꾩옄", "action": "?뚯븸留ㅻ룄寃??, "current": "113,000", "dist": "??+17.0% / 二?-6.8%", "price_ref": "二???121,400"},
            {"holding": "?좉퇋", "name": "?댄떚?", "action": "?뚯븸留ㅼ닔寃??, "current": "53,800", "dist": "??+7.3% / 二?+2.6%", "price_ref": "?쒖븞 53,800(?덉떆)"},
            {"holding": "?좉퇋", "name": "?숈꽌", "action": "?뚯븸留ㅼ닔寃??, "current": "27,250", "dist": "??+1.8% / 二?+6.8%", "price_ref": "?쒖븞 27,250(?덉떆)"},
        ]
    if kind == "open":
        return [
            {"holding": "蹂댁쑀", "name": "?좎쁺利앷텒", "action": "蹂댁쑀?좎?", "current": "203,200", "dist": "??+190.5% / 二?+84.1%", "price_ref": "二?06??110,100"},
            {"holding": "蹂댁쑀", "name": "LG?꾩옄", "action": "?뚯븸留ㅻ룄寃??, "current": "111,900", "dist": "??+15.4% / 二?-7.5%", "price_ref": "二???120,900"},
            {"holding": "?좉퇋", "name": "?댄떚?", "action": "?뚯븸留ㅼ닔寃??, "current": "54,100", "dist": "??+6.9% / 二?+3.1%", "price_ref": "?쒖븞 54,100(?덉떆)"},
        ]
    return [
        {"holding": "蹂댁쑀", "name": "?좎쁺利앷텒", "action": "?듭씪蹂댁쑀", "current": "201,500", "dist": "??+189.2% / 二?+86.9%", "price_ref": "二?06??108,300"},
        {"holding": "蹂댁쑀", "name": "LG?꾩옄", "action": "?듭씪?뚯븸留ㅻ룄寃??, "current": "113,000", "dist": "??+17.0% / 二?-6.8%", "price_ref": "二???121,400"},
        {"holding": "?좉퇋", "name": "?댄떚?", "action": "?듭씪愿?ъ쑀吏", "current": "53,800", "dist": "??+7.3% / 二?+2.6%", "price_ref": "?쒖븞 53,800(?덉떆)"},
        {"holding": "?좉퇋", "name": "?숈꽌", "action": "?듭씪愿?ъ쑀吏", "current": "27,250", "dist": "??+1.8% / 二?+6.8%", "price_ref": "?쒖븞 27,250(?덉떆)"},
    ]


def render(kind: str, title: str, subline: str, footer: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (WIDTH, HEIGHT), "#f8fafc")
    draw = ImageDraw.Draw(img)

    rounded(draw, (MARGIN, MARGIN, WIDTH - MARGIN, HEIGHT - MARGIN), fill="#ffffff", outline="#e2e8f0", width=2, radius=28)
    draw_text(draw, (MARGIN + 30, MARGIN + 26), title, size=40, bold=True)
    draw_text(draw, (MARGIN + 30, MARGIN + 82), subline, size=21, fill="#475569")

    badge(draw, (MARGIN + 30, MARGIN + 124), "?쒖옣 諛⑹뼱援ш컙", bg="#fee2e2", fg="#b91c1c")
    badge(draw, (MARGIN + 210, MARGIN + 124), "?댁슜媛뺣룄 40%", bg="#dbeafe", fg="#1d4ed8")

    table_x = MARGIN + 30
    table_y = MARGIN + 190
    table_w = WIDTH - MARGIN * 2 - 60
    col_widths = [140, 240, 250, 180, 360, table_w - 140 - 240 - 250 - 180 - 360]
    headers = ["援щ텇", "醫낅ぉ", "?≪뀡", "?꾩옱媛", "??二??닿꺽瑜?, "媛寃?湲곗?"]

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
    draw_text(draw, (table_x + 18, note_y + 16), "硫붾え", size=20, bold=True)
    draw_text(draw, (table_x + 18, note_y + 46), "留ㅼ닔?쒖븞媛???꾩옱 mockup ?덉떆媛믪엯?덈떎. ?ㅼ젣 ?곸슜 ??媛寃?洹쒖튃 ?곗떇?쇰줈 蹂꾨룄 ?뺤쓽媛 ?꾩슂?⑸땲??", size=18, fill="#475569")

    draw_text(draw, (table_x, HEIGHT - MARGIN - 34), footer, size=17, fill="#64748b")

    out = OUT_DIR / f"telegram_brief_mockup_{kind}.png"
    img.save(out)
    return out


def main() -> None:
    paths = [
        render("premarket", "?꾨━??釉뚮━???쒖븞", "?ㅻ뒛 ?꾩묠 ?곗꽑?쒖쐞瑜?諛붾줈 ?쎈뒗 媛꾨떒 ?쒗삎 ?쒖븞", "?꾨━?? 蹂댁쑀 ?먭?怨??좉퇋 愿?щ쭔 ?곗꽑 ?뺤씤"),
        render("open", "蹂몄옣 釉뚮━???쒖븞", "???쒖옉 ??利됱떆 ?????곸쓣 ?뺣━?섎뒗 媛꾨떒 ?쒗삎 ?쒖븞", "蹂몄옣: 蹂댁쑀/異뺤냼 ?곗꽑, ?좉퇋??怨쇱뿴 ?뺤씤"),
        render("postclose", "?ν썑 釉뚮━???쒖븞", "?댁씪 湲곗? ?됰룞???뺣━?섎뒗 ?듭씪 ?쒗삎 ?쒖븞", "?ν썑: ?듭씪蹂댁쑀 / ?듭씪愿??/ ?듭씪?뚯븸留ㅻ룄 ?뺣━"),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()

