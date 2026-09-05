"""Compose the CatLitter social preview / promo banner from the wordless base art."""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

BASE = "assets/_base.png"
INK = (31, 45, 43)
TEAL = (15, 138, 126)
ORANGE = (199, 124, 18)
GRAY = (107, 125, 121)
CREAM = (246, 248, 247)

FONT_CN_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_EN_BLACK = "C:/Windows/Fonts/seguibl.ttf"
FONT_EN_BOLD = "C:/Windows/Fonts/segoeuib.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def centered_text(draw, y, runs, total_width=None, canvas_w=2048):
    """runs: list of (text, font, fill). Draw on one line, centered as a group."""
    if total_width is None:
        total_width = sum(draw.textlength(t, font=f) for t, f, _ in runs)
    x = (canvas_w - total_width) / 2
    for text, f, fill in runs:
        draw.text((x, y), text, font=f, fill=fill)
        x += draw.textlength(text, font=f)


def compose() -> Image.Image:
    im = Image.open(BASE).convert("RGB")
    draw = ImageDraw.Draw(im)
    w, h = im.size

    # soft cream band on top so title always reads clearly
    band = Image.new("RGBA", (w, 360), CREAM + (235,))
    im.paste(Image.alpha_composite(im.convert("RGBA").crop((0, 0, w, 360)), band).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(im)

    # title row: 猫砂 + CatLitter
    f_cn = font(FONT_CN_BOLD, 118)
    f_en = font(FONT_EN_BLACK, 118)
    title_runs = [("猫砂 ", f_cn, INK), ("CatLitter", f_en, TEAL)]
    tw = sum(draw.textlength(t, font=f) for t, f, _ in title_runs)
    centered_text(draw, 46, title_runs, tw, w)

    # accent underline
    draw.rounded_rectangle(
        [(w - tw) / 2 + 6, 184, (w - tw) / 2 + 150, 194], radius=5, fill=ORANGE
    )

    # Chinese subtitle
    f_sub = font(FONT_CN_BOLD, 50)
    sub = "像铲猫砂一样，把冗余代码铲进可恢复的垃圾袋"
    sw = draw.textlength(sub, font=f_sub)
    draw.text(((w - sw) / 2, 218), sub, font=f_sub, fill=INK)

    # English subtitle
    f_en_sub = font(FONT_EN_BOLD, 38)
    en_sub = "Auto-detect projects · scoop dead code · restore byte-for-byte"
    ew = draw.textlength(en_sub, font=f_en_sub)
    draw.text(((w - ew) / 2, 292), en_sub, font=f_en_sub, fill=GRAY)

    # bottom pill bar
    pills = ["Zero-dependency", "Python 3.11+", "AST-based", "MIT License"]
    f_pill = font(FONT_EN_BOLD, 30)
    gap = 34
    pill_w = [draw.textlength(p, font=f_pill) + 56 for p in pills]
    total = sum(pill_w) + gap * (len(pills) - 1)
    x = (w - total) / 2
    y = h - 78
    for p, pw in zip(pills, pill_w):
        draw.rounded_rectangle([x, y, x + pw, y + 56], radius=28,
                               outline=TEAL, width=3, fill=(223, 241, 239))
        tw2 = draw.textlength(p, font=f_pill)
        draw.text((x + (pw - tw2) / 2, y + 9), p, font=f_pill, fill=TEAL)
        x += pw + gap

    return im


def cover_resize(im: Image.Image, tw: int, th: int) -> Image.Image:
    w, h = im.size
    scale = max(tw / w, th / h)
    nw, nh = round(w * scale), round(h * scale)
    im2 = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - tw) // 2, (nh - th) // 2
    return im2.crop((left, top, left + tw, top + th))


def main() -> None:
    banner = compose()
    banner.save("assets/promo-wide.png", optimize=True)
    social = cover_resize(banner, 1280, 640)
    social.save("assets/og-social.png", optimize=True)
    print("saved assets/promo-wide.png", banner.size)
    print("saved assets/og-social.png", social.size)


if __name__ == "__main__":
    main()
