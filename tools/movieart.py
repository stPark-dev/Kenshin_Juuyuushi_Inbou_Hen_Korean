"""Korean overlays for the movies, rendered from system fonts into assets/movie/.

usage: python tools/movieart.py [--fonts C:/Windows/Fonts]

The build only composites the committed PNGs (tools/movie.py), so it needs no
fonts. Each overlay is a 320x240 RGBA layer: the Korean text where the
Japanese text was (docs/survey.md §3.1.10, D35). Fonts: Malgun Gothic for the
title cards (the source cards use a gothic face), Gungsuh (batang.ttc face 2)
with a black outline for the brush-lettered character name cards.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "assets" / "movie"
W, H = 320, 240
FONTS = {"gothic": ("malgun.ttf", 0), "gothic-bold": ("malgunbd.ttf", 0), "brush": ("batang.ttc", 2)}
WHITE = (255, 255, 255, 255)

# name: [(text, font, size, (x0, y0, x1, y1) box of the Japanese text it replaces)]
CARDS = {
    "ru12_card1": [("원작", "gothic", 27, (57, 95, 114, 122))],
    "ru12_card2": [("바람의 검심", "gothic-bold", 22, (90, 101, 230, 122)),
                   ("―메이지 검객 낭만기―", "gothic-bold", 13, (96, 125, 223, 138))],
    "ru12_card3": [("십용사 음모편", "gothic-bold", 22, (90, 109, 229, 130))],
}


# character name cards: (groups, size, vertical, spans, cross) — each Korean group is
# centred on the extent (lo, hi) of the Japanese group it replaces along the
# text direction, `cross` the middle across it (measured from the stroke masks)
NAMECARDS = {
    "ru12_kaoru": (("카미야", "카오루"), 28, True, ((10, 120), (146, 209)), 37),
    "ru12_yahiko": (("묘진", "야히코"), 42, False, ((76, 182), (221, 309)), 40),
    "ru12_sanosuke": (("사가라", "사노스케"), 40, False, ((19, 112), (155, 318)), 198),
    "ru12_aoshi": (("시노모리", "아오시"), 38, False, ((11, 156), (183, 295)), 193),
    "ru12_saito": (("사이토", "하지메"), 26, True, ((43, 159), (197, 202)), 44),
    "ru12_kenshin": (("히무라", "켄신"), 42, False, ((48, 134), (186, 292)), 201),
}
OUTLINE = 3


def font(fonts, name, size):
    file, index = FONTS[name]
    return ImageFont.truetype(str(Path(fonts) / file), size, index=index)


def text_layer(items, fonts):
    """RGBA layer with each text centred on its box (ink bounding box)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    for text, face, size, (x0, y0, x1, y1) in items:
        f = font(fonts, face, size)
        l, t, r, b = dr.textbbox((0, 0), text, font=f)
        x = (x0 + x1 + 1) / 2 - (l + r) / 2
        y = (y0 + y1 + 1) / 2 - (t + b) / 2
        dr.text((round(x), round(y)), text, font=f, fill=WHITE)
    return im


def name_layer(groups, size, vertical, spans, cross, fonts):
    """White brush-style letters with a black outline; groups kept inside the frame
    and apart (the first one gives way)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    f = font(fonts, "brush", size)
    limit = H if vertical else W
    step = size + 2
    lengths = [len(g) * step if vertical else dr.textlength(g, font=f) for g in groups]
    starts = [(lo + hi) / 2 - n / 2 for (lo, hi), n in zip(spans, lengths)]
    starts[1] = min(starts[1], limit - 4 - lengths[1])
    starts[0] = max(4, min(starts[0], starts[1] - 8 - lengths[0]))
    for text, start in zip(groups, starts):
        if vertical:
            for i, ch in enumerate(text):
                l, t, r, b = dr.textbbox((0, 0), ch, font=f)
                dr.text((round(cross - (l + r) / 2), round(start + i * step - t)), ch, font=f, fill=WHITE,
                        stroke_width=OUTLINE, stroke_fill=(0, 0, 0, 255))
        else:
            l, t, r, b = dr.textbbox((0, 0), text, font=f)
            dr.text((round(start - l), round(cross - (t + b) / 2)), text, font=f, fill=WHITE,
                    stroke_width=OUTLINE, stroke_fill=(0, 0, 0, 255))
    return im


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fonts", default="C:/Windows/Fonts")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, items in CARDS.items():
        text_layer(items, a.fonts).save(OUT / f"{name}.png")
        print(name)
    for name, (groups, size, vertical, spans, cross) in NAMECARDS.items():
        name_layer(groups, size, vertical, spans, cross, a.fonts).save(OUT / f"{name}.png")
        print(name)


if __name__ == "__main__":
    main()
