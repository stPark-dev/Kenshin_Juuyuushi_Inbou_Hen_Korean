"""Movie text replacement: decode the frames that show Japanese text, put the
Korean overlays (assets/movie, tools/movieart.py) in its place, re-encode them
into their own sectors.

Established 2026-10-10 (docs/survey.md §3.1.10, D35). Only RU12 (opening) and
RU13 (battle tutorial) show text. A frame keeps its sectors (the movie table
seeks by frame), so a re-encoded frame must fit its chunks; the encoder raises
qscale until it does.

Title cards: white text on black that fades (card 1 also zooms from 3x) and,
for the last one, cross-fades into the field. Each frame is fitted as
alpha * scale(J) (+ the field), J being the card at full strength; the Korean
card K is J with the replaced text blacked out and the overlay on top, and the
frame becomes alpha * scale(K) on black, or F + alpha * (K - J) over the field.
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import mdec

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "movie"


@dataclass(frozen=True)
class Card:
    first: int
    last: int
    ref: int  # a frame with the card at full strength
    erase: tuple  # (x0, y0, x1, y1) of the Japanese text that is replaced, inclusive
    overlay: str
    zoom: tuple = ()  # frames whose card is scaled about the centre
    field: int = 0  # first frame drawn over the field (cross-fade), 0 = none


RU12_CARDS = (
    Card(1, 60, 30, (55, 93, 116, 124), "ru12_card1", zoom=tuple(range(1, 16))),
    Card(62, 93, 76, (88, 99, 232, 140), "ru12_card2"),
    Card(95, 140, 112, (88, 107, 231, 132), "ru12_card3", field=122),
)


def overlay(name):
    im = np.asarray(Image.open(ASSETS / f"{name}.png").convert("RGBA")).astype(float)
    return im[..., :3], im[..., 3:] / 255


def scaled(img, s, w=320, h=240):
    m = np.array([[s, 0, w / 2 - s * w / 2], [0, s, h / 2 - s * h / 2]])
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR)


def _fit_scale(frame, ref):
    """(scale, alpha) with frame ~ alpha * scaled(ref, scale)."""
    best = None
    for s in np.arange(1.0, 3.005, 0.01):
        r = scaled(ref, s)
        d = (r * r).sum()
        a = (frame * r).sum() / d if d else 0.0
        err = ((frame - a * r) ** 2).sum()
        if best is None or err < best[0]:
            best = (err, s, a)
    return best[1], best[2]


def cards(get, specs):
    """{frame: new RGB} for title cards; `get(frame)` returns a decoded frame (float)."""
    out = {}
    for c in specs:
        j = get(c.ref)
        rgb, alpha = overlay(c.overlay)
        k = j.copy()
        x0, y0, x1, y1 = c.erase
        k[y0:y1 + 1, x0:x1 + 1] = 0
        k = k * (1 - alpha) + rgb * alpha
        clean = get(c.last + 1) if c.field else None
        for f in range(c.first, c.last + 1):
            frame = get(f)
            if c.field and f >= c.field:
                d = j - clean
                a = float(np.clip(((frame - clean) * d).sum() / (d * d).sum(), 0, 1))
                new = frame + a * (k - j)
            elif f in c.zoom:
                s, a = _fit_scale(frame, j)
                new = a * scaled(k, s)
            else:
                a = (frame * j).sum() / (j * j).sum()
                new = a * k
            out[f] = np.clip(np.rint(new), 0, 255).astype(np.uint8)
    return out


def apply(raw, rec, edits):
    """{lba: user data} re-encoding the edited frames {frame: RGB} of a movie."""
    frames = mdec.frames(raw, rec)
    secs = mdec.sectors(raw, rec)
    room = {}
    for _, f, _, _, _ in secs:
        room[f] = room.get(f, 0) + mdec.CHUNK
    users = {}
    for f, rgb in sorted(edits.items()):
        q0 = int.from_bytes(frames[f][2][4:6], "little")
        data, _ = mdec.fit(rgb, room[f], max(1, q0))
        users.update(mdec.chunk_sectors(raw, rec, f, data))
    return users


def decoder(raw, rec):
    frames = mdec.frames(raw, rec)
    cache = {}

    def get(f):
        if f not in cache:
            w, h, data = frames[f]
            cache[f] = mdec.decode(w, h, data).astype(float)
        return cache[f]

    return get


# Dialogue boxes (RU12): the movie shows the game's text window over the field.
# Rows: the speaker at (17, 172), text at x 33 from y 188 and 203 (16 px cells,
# 15 px pitch); a third text line scrolls the speaker out (frame 664). Japanese
# strokes are found with a top-hat in the text rows and inpainted; the Korean
# is drawn in Galmuri14 (the game's Korean font), revealed in step with the
# source's typing. A fade-out into the next shot is fitted as
# (1 - t) * last frame + t * next frame.
@dataclass(frozen=True)
class Line:
    first: int
    last: int
    fade: int = 0  # last frame of the cross-fade after `last`, 0 = cut


RU12_LINES = (Line(161, 223), Line(243, 310), Line(313, 357), Line(393, 445, 456),
              Line(567, 624), Line(625, 695), Line(696, 716), Line(717, 735, 747),
              Line(831, 865), Line(867, 935), Line(944, 990, 1001))
TEXT_ROWS = (12, 170, 308, 222)  # x0, y0, x1, y1 (exclusive) searched for Japanese strokes
ROW_TOPS, NAME_X, TEXT_X = (172, 188, 203), 17, 33
INK, SHADOW = (232, 232, 232), (24, 24, 24)


def strokes(frame):
    """Mask of the Japanese text strokes (and their shadow) in the text rows."""
    x0, y0, x1, y1 = TEXT_ROWS
    lum = cv2.cvtColor(frame[y0:y1, x0:x1].astype(np.uint8), cv2.COLOR_RGB2GRAY)
    m = (cv2.morphologyEx(lum, cv2.MORPH_TOPHAT, np.ones((7, 7), np.uint8)) > 40).astype(np.uint8)
    m = cv2.dilate(m, np.ones((3, 3), np.uint8))
    dark = cv2.morphologyEx(lum, cv2.MORPH_BLACKHAT, np.ones((5, 5), np.uint8)) > 35
    m = np.maximum(m, (dark & (cv2.dilate(m, np.ones((3, 3), np.uint8)) > 0)).astype(np.uint8))
    full = np.zeros(frame.shape[:2], np.uint8)
    full[y0:y1, x0:x1] = m
    return full


def erase(frame):
    m = strokes(frame)
    return cv2.inpaint(frame.astype(np.uint8), m, 3, cv2.INPAINT_TELEA).astype(float), int(m.sum())


class Glyphs:
    """Galmuri14 placed like kfont.render (Hangul box centred in a 16 px cell,
    shared baseline) but free to hang below the cell (，．); ASCII space = 8 px."""

    def __init__(self, font):
        import kfont
        self.font = font
        self.bw, self.bh = kfont.hangul_box(font)
        self.cache = {}

    def points(self, ch):
        if ch not in self.cache:
            g = self.font[ch]
            w, h, xo, yo = g["bbx"]
            top = (16 - self.bh) // 2 + (self.bh - (yo + h))
            left = (16 - self.bw) // 2 + xo
            pts = [(top + r, left + x) for r, bits in enumerate(g["bits"]) for x in range(w) if bits >> (w - 1 - x) & 1]
            self.cache[ch] = (np.array([p[0] for p in pts], int), np.array([p[1] for p in pts], int))
        return self.cache[ch]

    def width(self, text):
        return sum(8 if c == " " else 16 for c in text)

    def draw(self, img, x, y, text):
        for ch in text:
            if ch != " ":
                ys, xs = self.points(ch)
                img[y + ys + 1, x + xs + 1] = SHADOW
                img[y + ys, x + xs] = INK
            x += 8 if ch == " " else 16


def _rows(name, lines, shown):
    """[(x, y, text)] with `shown` characters of the text typed."""
    rows, left = [], shown
    for ln in lines:
        rows.append(ln[:max(0, left)])
        left -= len(ln)
    rows = [r for r in rows if r] or [""]
    allrows = [(NAME_X, name)] + [(TEXT_X, r) for r in rows]
    allrows = allrows[-3:]
    return [(x, ROW_TOPS[i], t) for i, (x, t) in enumerate(allrows)]


def dialogue(get, specs, texts, glyphs):
    """{frame: new RGB}; texts: [(speaker, korean with newlines)] per Line."""
    out = {}
    for spec, (name, ko) in zip(specs, texts):
        lines = ko.split("\n")
        if len(lines) > 3 or any(glyphs.width(ln) > 272 for ln in lines):
            raise ValueError(f"frame {spec.first}: Korean line too long for the window")
        total = sum(len(ln) for ln in lines)
        clean, counts = {}, {}
        for f in range(spec.first, spec.last + 1):
            clean[f], counts[f] = erase(get(f))
        # typing progress: strokes in the text rows grow as characters appear
        base = min(counts.values())
        top = max(counts.values()) - base or 1
        seen = 0
        for f in range(spec.first, spec.last + 1):
            seen = max(seen, counts[f] - base)
            shown = total if f == spec.last else round(total * seen / top)
            img = clean[f]
            for x, y, t in _rows(name, lines, shown):
                glyphs.draw(img, x, y, t)
            out[f] = img
        if spec.fade:
            d, d_ko, n = get(spec.last), out[spec.last], get(spec.fade + 1)
            diff = n - d
            for f in range(spec.last + 1, spec.fade + 1):
                frame = get(f)
                t = float(np.clip(((frame - d) * diff).sum() / (diff * diff).sum(), 0, 1))
                out[f] = frame + (1 - t) * (d_ko - d)
    return {f: np.clip(np.rint(v), 0, 255).astype(np.uint8) for f, v in out.items()}


# Character name cards (RU12): white brush letters with a black outline at a
# fixed place, fading in and out over moving shots. The strokes are the white
# pixels next to dark ones inside the card's box, kept only where they stay in
# every frame around the reference (the letters do not move, the shot does);
# the mask grows over the outline. Opacity per frame is the core-to-outline
# contrast relative to the reference; the masked area is inpainted and the
# Korean card drawn at that opacity.
@dataclass(frozen=True)
class NameCard:
    first: int  # frames with the card (measured opacity above the noise floor)
    last: int
    ref: int
    box: tuple  # x0, y0, x1, y1 inclusive
    overlay: str


RU12_NAMES = (NameCard(466, 537, 500, (6, 8, 68, 212), "ru12_kaoru"),
              NameCard(747, 811, 780, (72, 8, 312, 66), "ru12_yahiko"),
              NameCard(1040, 1137, 1080, (4, 172, 318, 232), "ru12_sanosuke"),
              NameCard(1207, 1357, 1300, (4, 172, 298, 224), "ru12_aoshi"),
              NameCard(1358, 1454, 1420, (8, 4, 68, 232), "ru12_saito"),
              NameCard(1462, 1528, 1500, (32, 172, 318, 232), "ru12_kenshin"))


def _core(frame, box):
    a = frame.astype(np.uint8)
    lum = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
    dark = cv2.dilate((lum < 70).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    core = (a.min(axis=2) > 185) & dark
    x0, y0, x1, y1 = box
    keep = np.zeros_like(core)
    keep[y0:y1 + 1, x0:x1 + 1] = True
    return core & keep


def _contrast(frame, core, ring):
    lum = frame.mean(axis=2)
    return lum[core].mean() - lum[ring].mean()


def namecards(get, specs):
    out = {}
    for c in specs:
        core = np.ones((240, 320), bool)
        for f in range(c.ref - 4, c.ref + 5):
            core &= _core(get(f), c.box)
        ell = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        mask = cv2.dilate(core.astype(np.uint8), ell)
        ring = (cv2.dilate(core.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~core
        full = _contrast(get(c.ref), core, ring)
        rgb, alpha = overlay(c.overlay)
        frames = [(f, _contrast(get(f), core, ring) / full) for f in range(c.first, c.last + 1)]
        for f, a in frames:
            a = float(np.clip(a, 0, 1))
            clean = cv2.inpaint(get(f).astype(np.uint8), mask, 5, cv2.INPAINT_TELEA).astype(float)
            out[f] = clean * (1 - a * alpha) + rgb * a * alpha
    return {f: np.clip(np.rint(v), 0, 255).astype(np.uint8) for f, v in out.items()}


# Closing logo (RU12 1629-1740): the logo zooms in from about 4x over the cast
# picture (frame 1628), which then cross-fades into the title screen picture
# (TITLE.BIN entry 2, the same art); from 1664 the frame is still. The Korean
# shot is drawn whole from those layers, the Korean title logo (title_ko.png,
# D33) zooming on the timing fitted to the source.
LOGO_ART, LOGO_FIRST, LOGO_LAST = 1628, 1629, 1740
LOGO_BOX = (10, 14, 306, 178)
LOGO_SCALE = ((1629, 4.2), (1634, 3.6), (1640, 1.7), (1646, 1.5), (1652, 1.3), (1658, 1.1), (1661, 1.0))
LOGO_ALPHA = ((1629, 0.0), (1631, 0.3), (1636, 1.0))
ART_FADE = ((1655, 0.0), (1664, 1.0))


def _ramp(keys, f):
    xs, ys = zip(*keys)
    return float(np.interp(f, xs, ys))


def title_background(title):
    """TITLE.BIN entry 2 (320x240 8bpp picture) as RGB."""
    import struct

    import titlemenu
    at, end = titlemenu.entries(title)[2]
    _, w, h = struct.unpack_from("<IHH", title, at)
    clut = np.array(struct.unpack_from("<256H", title, at + 8), np.uint32)
    rgb = np.stack([(clut & 31) << 3, (clut >> 5 & 31) << 3, (clut >> 10 & 31) << 3], -1)
    img = np.zeros((h, w, 3))
    p = at + 520
    while p < end:
        x, y, tw, th = struct.unpack_from("<4H", title, p)
        p += 8
        img[y:y + th, x:x + tw] = rgb[np.frombuffer(title, np.uint8, tw * th, p).reshape(th, tw)]
        p += tw * th
    return img


def closing_logo(get, background, logo_png):
    src = Image.open(logo_png).convert("RGBA")
    src = src.crop(src.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox())
    x0, y0, x1, y1 = LOGO_BOX
    fit = min((x1 - x0) / src.width, (y1 - y0) / src.height)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    art = get(LOGO_ART)
    out, still = {}, None
    for f in range(LOGO_FIRST, LOGO_LAST + 1):
        if still is not None:
            out[f] = still
            continue
        b = _ramp(ART_FADE, f)
        img = (1 - b) * art + b * background
        s, a = _ramp(LOGO_SCALE, f) * fit, _ramp(LOGO_ALPHA, f)
        if a > 0:
            w, h = max(1, round(src.width * s)), max(1, round(src.height * s))
            lg = src.resize((w, h), Image.LANCZOS)
            layer = Image.new("RGBA", (320, 240))
            layer.paste(lg, (round(cx - w / 2), round(cy - h / 2)))
            la = np.asarray(layer).astype(float)
            al = la[..., 3:] / 255 * a
            img = img * (1 - al) + la[..., :3] * al
        img = np.clip(np.rint(img), 0, 255).astype(np.uint8)
        out[f] = img
        if b >= 1 and _ramp(LOGO_SCALE, f) == 1.0 and a >= 1:
            still = img
    return out


LOGO_PNG = Path(__file__).resolve().parent.parent / "title_ko.png"


def ru12(raw, disc, title, galmuri, ko):
    """{lba: user data} for the Korean opening; ko = text/ko/MOVIE.json entries to use."""
    rec = disc.files["RU12.MOV"]
    get = decoder(raw, rec)
    texts = []
    for line in RU12_LINES:
        e = ko.get(f"RU12:{line.first}")
        if e is None:
            raise ValueError(f"RU12:{line.first}: no translation")
        texts.append((e["speaker"], e["ko"]))
    edits = cards(get, RU12_CARDS)
    edits.update(dialogue(get, RU12_LINES, texts, Glyphs(galmuri)))
    edits.update(namecards(get, RU12_NAMES))
    edits.update(closing_logo(get, title_background(title), LOGO_PNG))
    return apply(raw, rec, edits), len(edits)
