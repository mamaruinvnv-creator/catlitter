# -*- coding: utf-8 -*-
"""Compose the Xiaohongshu 3:4 cover from the wordless base illustration."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE = "_xhs_base.png"
OUT = "xhs-cover.png"
W, H = 1536, 2048

INK = (43, 43, 51)
ORANGE = (232, 116, 43)
ORANGE_SOFT = (255, 241, 230)
TEAL = (47, 184, 166)
TEAL_SOFT = (230, 247, 244)
GRAY = (110, 112, 120)
WHITE = (255, 255, 255)

FB = "C:/Windows/Fonts/msyhbd.ttc"      # Microsoft YaHei Bold
FR = "C:/Windows/Fonts/msyh.ttc"        # Microsoft YaHei
FE_B = "C:/Windows/Fonts/segoeuib.ttf"  # Segoe UI Bold


def f(path, size):
    return ImageFont.truetype(path, size)


def text_w(draw, s, font):
    b = draw.textbbox((0, 0), s, font=font)
    return b[2] - b[0]


def center_text(draw, cx, y, s, font, fill):
    w = text_w(draw, s, font)
    draw.text((cx - w / 2, y), s, font=font, fill=fill)


def pill(draw, cx, y, text, font, fill_bg, fill_fg, padx=34, pady=16, radius=40):
    tw = text_w(draw, text, font)
    b = draw.textbbox((0, 0), text, font=font)
    th = b[3] - b[1]
    w = tw + padx * 2
    h = th + pady * 2
    x0 = cx - w / 2
    draw.rounded_rectangle([x0, y, x0 + w, y + h], radius=radius, fill=fill_bg)
    draw.text((cx - tw / 2, y + pady - b[1] / 2), text, font=font, fill=fill_fg)
    return h


def main():
    im = Image.open(BASE).convert("RGB")
    draw = ImageDraw.Draw(im)
    cx = W / 2

    # ---- top tag pill ----
    tag_font = f(FB, 40)
    pill(draw, cx, 120, "开源工具  ·  Python 零依赖", tag_font, TEAL, WHITE,
         padx=40, pady=14, radius=36)

    # ---- main title (two lines, second line highlighted) ----
    t1 = f(FB, 150)
    center_text(draw, cx, 250, "删死代码", t1, INK)
    # highlight stroke behind second line
    line2 = "再也不怕翻车"
    t2 = f(FB, 150)
    lw = text_w(draw, line2, t2)
    lx = cx - lw / 2
    ly = 430
    # soft orange highlighter bar
    bar = Image.new("RGBA", im.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    bd.rounded_rectangle([lx - 24, ly + 26, lx + lw + 24, ly + 150],
                         radius=28, fill=(232, 116, 43, 46))
    im = Image.alpha_composite(im.convert("RGBA"), bar).convert("RGB")
    draw = ImageDraw.Draw(im)
    center_text(draw, cx, ly, line2, t2, ORANGE)

    # ---- subtitle ----
    sub = f(FR, 52)
    center_text(draw, cx, 640, "猫砂 CatLitter：先铲进可恢复垃圾袋", sub, GRAY)

    # ---- bottom three steps in one horizontal row (clean whitespace below art) ----
    steps = [
        ("① scan 只读扫描", TEAL_SOFT, TEAL),
        ("② scoop 铲进垃圾袋", ORANGE_SOFT, ORANGE),
        ("③ restore 字节还原", TEAL_SOFT, TEAL),
    ]
    sf = f(FB, 40)
    gap = 24
    sizes = []
    for text, bg, fg in steps:
        tw = text_w(draw, text, sf)
        b = draw.textbbox((0, 0), text, font=sf)
        w = tw + 40 * 2
        h = (b[3] - b[1]) + 16 * 2
        sizes.append((w, h))
    total_w = sum(w for w, _ in sizes) + gap * (len(steps) - 1)
    x = (W - total_w) / 2
    y = 1806
    for (text, bg, fg), (w, h) in zip(steps, sizes):
        draw.rounded_rectangle([x, y, x + w, y + h], radius=40, fill=bg)
        tw = text_w(draw, text, sf)
        b = draw.textbbox((0, 0), text, font=sf)
        draw.text((x + (w - tw) / 2, y + 16 - b[1] / 2), text, font=sf, fill=fg)
        x += w + gap

    # ---- footer repo line (YaHei has the star glyph) ----
    ff = f(FB, 38)
    foot = "github.com/mamaruinvnv-creator/catlitter  ★ 求 Star"
    center_text(draw, cx, 1936, foot, ff, (150, 150, 158))

    im.save(OUT, quality=95)
    print("saved", OUT, im.size)


if __name__ == "__main__":
    main()
