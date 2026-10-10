"""Field signs: shop signs and plaques drawn in the map tile sheets (*.MDT), redrawn in Hangul.

Established 2026-10-10 (docs/survey.md §3.1.11):
- A map is a pair of bootlz files in its ZROUP GRP: NNNN.MDT, four VRAM uploads
  (u16 x, y, w, h, u32 offset each from byte 4, w = 128 halfwords, h = 256), i.e.
  four 256x256 8bpp tile sheets, and NNNN.MDS, whose palette rows (256 colours
  each) start at 0x5584 (matched against a DuckStation VRAM-write dump of
  ZROUP01).
- The same sign is drawn again in each map file that shows it, often with other
  palette numbers and a few edge pixels different. A sign is found by the
  pattern of equal neighbouring pixels (independent of the numbering), compared
  with a reference copy; real copies differ in at most ~15% of that pattern,
  unrelated art in ~34%.
- The text is the pixels whose colour (reference palette) is far from the board
  colour; a copy's indices are mapped to the reference's by majority at each
  position, so the same strokes are found in every copy. Strokes are filled from
  the nearest board pixel of the row and the Korean is drawn with the copy's
  own ink index, so the palettes are never touched.
"""

import struct
from dataclasses import dataclass

import cv2
import numpy as np

CLUT = 0x5584
MATCH = 0.25  # structure mismatch accepted as the same sign


@dataclass(frozen=True)
class Sign:
    name: str
    ref: str  # map file of the reference copy
    block: int
    row: int  # palette row the reference sign is drawn with (chosen by eye)
    box: tuple  # x0, y0, x1, y1 (exclusive) of the board area holding the text
    text: str
    font: int  # Galmuri size: 9 or 11 (11 is drawn in Galmuri11-Bold)
    vertical: bool = False
    bold: bool = False  # widen the strokes (9 px signs with room)
    dark: object = True  # dark ink on a light board (False: light ink, None: both)
    grow: bool = False  # also erase the pixels around the strokes (an outline)


SIGNS = (
    Sign("jinrikisha", "T001.MDT", 0, 0, (53, 58, 156, 74), "인력거 대기소", 11),
    Sign("yado", "T001.MDT", 1, 2, (148, 107, 173, 127), "여관", 9, bold=True),
    Sign("yaoya", "T001.MDT", 2, 2, (33, 129, 62, 138), "채소", 9, bold=True, dark=False),
    Sign("sakana", "T001.MDT", 2, 2, (160, 160, 183, 174), "생선", 9, bold=True, dark=False),
    Sign("sakaya", "T001.MDT", 2, 2, (2, 242, 30, 254), "술집", 9, bold=True, dark=False),
    Sign("gyunabe", "T001.MDT", 2, 2, (147, 224, 159, 248), "전골", 9, True, True, dark=False),
    Sign("unagi", "T001.MDT", 2, 2, (160, 224, 173, 248), "장어", 9, True, True, dark=False),
    Sign("kahii", "T001.MDT", 3, 0, (5, 120, 91, 135), "카히 찻집", 11),
    Sign("bansho", "T008.MDT", 0, 2, (113, 185, 143, 196), "파출소", 9),
    Sign("ezoshi", "T034.MDT", 2, 2, (68, 53, 83, 93), "그림책", 9, True, True),
    Sign("ezoshi2", "T057.MDT", 1, 2, (211, 105, 223, 137), "그림책", 9, True, True),
    Sign("meikyo", "T118.MDT", 1, 1, (66, 47, 126, 60), "명경지수", 11),
    Sign("komamono", "T175.MDT", 2, 2, (88, 1, 135, 14), "방물가게", 9, bold=True, dark=False),
    Sign("kuji", "T174.MDT", 1, 1, (141, 156, 153, 188), "복권", 9, True, dark=False, grow=True),
    Sign("senkyaku", "IOO3.MDT", 0, 0, (137, 0, 185, 11), "천객만래", 9),
    Sign("yado2", "T025.MDT", 2, 2, (6, 235, 27, 251), "여관", 9, bold=True, dark=False),
    Sign("dango", "I012.MDT", 1, 1, (175, 202, 186, 234), "경단", 9, True, True),
    Sign("akabeko", "T001.MDT", 0, 0, (174, 89, 213, 104), "아카베코", 9, dark=False, grow=True),
    Sign("shinbun", "T016.MDT", 2, 2, (90, 194, 135, 206), "신문사", 9, bold=True),
    Sign("kasshin", "T020.MDT", 1, 1, (211, 199, 252, 210), "활심류", 9, bold=True),
    Sign("keisatsu", "T039.MDT", 0, 1, (161, 145, 204, 159), "경찰서", 11),
)
MARGIN = 3  # board around the text box that the match must also agree on


def blocks(mdt):
    out = []
    for i in range(4):
        x, y, w, h, off = struct.unpack_from("<4HI", mdt, 4 + 12 * i)
        out.append((off, w * 2, h) if w and off + w * 2 * h <= len(mdt) else None)
    return out


def block_array(mdt, i):
    off, w, h = blocks(mdt)[i]
    return np.frombuffer(mdt, np.uint8, w * h, off).reshape(h, w)


def clut_rows(mds):
    rows = []
    for k in range(8):
        r = np.frombuffer(mds, "<u2", 256, CLUT + 512 * k) if CLUT + 512 * (k + 1) <= len(mds) else None
        if r is None or r[0] != 0 or (r == 0).mean() > 0.5:
            break
        rows.append(r.astype(np.int32))
    return rows


def luminance(blk, rows):
    """Luminance of a whole sheet, each 16x16 tile under the palette row that draws
    it most smoothly (a tile has one palette row on screen)."""
    out = np.zeros(blk.shape)
    for ty in range(0, blk.shape[0], 16):
        for tx in range(0, blk.shape[1], 16):
            idx = blk[ty:ty + 16, tx:tx + 16]
            best = None
            for r in rows:
                rgb = np.stack([(r & 31), (r >> 5) & 31, (r >> 10) & 31], -1)[idx].astype(float) * 8
                lum = rgb @ [0.299, 0.587, 0.114]
                rough = np.abs(np.diff(lum, axis=0)).mean() + np.abs(np.diff(lum, axis=1)).mean()
                if lum.max() < 24:
                    rough += 50
                if best is None or rough < best[0]:
                    best = (rough, lum)
            out[ty:ty + 16, tx:tx + 16] = best[1]
    return out


def ink_mask(lum, dark):
    """Otsu split of the board's luminance; the ink is the dark or the light side
    (dark=None: both, for strokes with a highlight)."""
    if dark is None:
        return np.abs(lum - np.median(lum)) > 40
    v = np.clip(lum, 0, 255).astype(np.uint8)
    t, _ = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return v <= t if dark else v > t


def _eq(a):
    return (a[:-1, 1:] == a[:-1, :-1]).astype(np.float32), (a[1:, :-1] == a[:-1, :-1]).astype(np.float32)


def scan(tpl, blk):
    """[(mismatch, x, y)] where tpl's equal-neighbour pattern occurs in blk."""
    th, tv = _eq(tpl)
    bh, bv = _eq(blk)
    m = None
    for B, T in ((bh, th), (bv, tv)):
        if B.shape[0] < T.shape[0] or B.shape[1] < T.shape[1]:
            return []
        st = cv2.matchTemplate(B, T, cv2.TM_CCORR)
        se = cv2.boxFilter(B, -1, T.shape[::-1], normalize=False, anchor=(0, 0))[:st.shape[0], :st.shape[1]]
        d = se + T.sum() - 2 * st
        m = d if m is None else m + d
    m /= th.size * 2
    out = []
    while True:
        y, x = np.unravel_index(np.argmin(m), m.shape)
        if m[y, x] > MATCH:
            return out
        out.append((float(m[y, x]), int(x), int(y)))
        m[max(0, y - 6):y + 6, max(0, x - 6):x + 6] = 9


@dataclass
class Reference:
    sign: Sign
    tpl: np.ndarray  # indices of the box plus MARGIN
    ink: np.ndarray  # ink mask over tpl
    origin: tuple  # (x, y) of tpl in its sheet
    core: np.ndarray = None  # the strokes themselves (ink less the grown outline)
    ink_index: int = 0  # stroke colour of the reference: the most extreme common one


def reference(sign, mdt, mds):
    x0, y0, x1, y1 = sign.box
    blk = block_array(mdt, sign.block)
    m = MARGIN
    ty0, tx0 = max(0, y0 - m), max(0, x0 - m)
    tpl = blk[ty0:y1 + m, tx0:x1 + m].copy()
    r = clut_rows(mds)[sign.row]
    rgb = np.stack([(r & 31), (r >> 5) & 31, (r >> 10) & 31], -1)[tpl].astype(float) * 8
    lum = rgb @ [0.299, 0.587, 0.114]
    ink = np.zeros(tpl.shape, bool)
    inner = (slice(y0 - ty0, y1 - ty0), slice(x0 - tx0, x1 - tx0))
    ink[inner] = ink_mask(lum[inner], sign.dark)
    core = ink.copy()
    if sign.grow:
        ink[inner] = cv2.dilate(ink.astype(np.uint8), np.ones((3, 3), np.uint8))[inner] > 0
    vals, counts = np.unique(tpl[core], return_counts=True)
    common = [v for v, c in zip(vals, counts) if c >= 0.1 * counts.sum()]
    lum_of = {v: lum[core & (tpl == v)].mean() for v in common}
    pick = (min if sign.dark is not False else max)(common, key=lum_of.get)
    return Reference(sign, tpl, ink, (tx0, ty0), core, int(pick))


def _tiles(shape, x, y):
    """Tile number of each pixel of a window placed at (x, y) in its sheet."""
    h, w = shape
    yy, xx = np.mgrid[y:y + h, x:x + w]
    return (yy // 16) * 64 + xx // 16


def _fill(win, ink, tiles):
    """Ink pixels take the nearest board pixel of their row (then column) in the same tile."""
    out = win.copy()
    h, w = win.shape
    for y, x in zip(*np.nonzero(ink)):
        for d in range(1, 16):
            for yy, xx in ((y, x - d), (y, x + d), (y - d, x), (y + d, x)):
                if 0 <= yy < h and 0 <= xx < w and not ink[yy, xx] and tiles[yy, xx] == tiles[y, x]:
                    out[y, x] = win[yy, xx]
                    break
            else:
                continue
            break
    return out


def glyph_mask(text, font, vertical, bold=False):
    """Bitmap (bool) of the text in a Galmuri BDF font; a space is 3 px; bold
    widens every stroke by one pixel to the right."""
    cells = []
    for ch in text:
        if ch == " ":
            cells.append(np.zeros((1, 3), bool) if not vertical else np.zeros((3, 1), bool))
            continue
        g = font[ch]
        w, h, xo, yo = g["bbx"]
        a = np.array([[bits >> (w - 1 - x) & 1 for x in range(w)] for bits in g["bits"]], bool)
        if bold:
            a = np.pad(a, ((0, 0), (0, 1)))
            a[:, 1:] |= a[:, :-1].copy()
        cells.append(a)
    if vertical:
        width = max(c.shape[1] for c in cells)
        rows = []
        for c in cells:
            pad = (width - c.shape[1]) // 2
            rows += [np.pad(c, ((0, 0), (pad, width - c.shape[1] - pad))), np.zeros((1, width), bool)]
        return np.vstack(rows[:-1])
    height = max(c.shape[0] for c in cells)
    cols = []
    for c in cells:
        cols += [np.pad(c, ((height - c.shape[0], 0), (0, 0))), np.zeros((height, 1), bool)]
    return np.hstack(cols[:-1])


def redraw(win, ref, mapping, text_mask, x, y):
    """New indices for a copy `win` found at (x, y) of its sheet (shape of ref.tpl)."""
    to_ref = np.vectorize(lambda v: mapping.get(int(v), -1))(win)
    ink = ref.ink & (np.isin(to_ref, np.unique(ref.tpl[ref.ink])) | (to_ref == -1))
    tiles = _tiles(win.shape, x, y)
    out = _fill(win, ink, tiles)
    # one ink index: a sign is one object drawn with one palette row
    core = ink & ref.core
    if not core.any():
        raise ValueError(f"{ref.sign.name}: no ink found")
    same = core & (to_ref == ref.ink_index)
    v, c = np.unique(win[same if same.any() else core], return_counts=True)
    ink_here = int(v[np.argmax(c)])
    x0, y0, x1, y1 = ref.sign.box
    rx, ry = ref.origin
    oy, ox = y0 - ry, x0 - rx
    bh, bw = y1 - y0, x1 - x0
    gh, gw = text_mask.shape
    if gh > bh or gw > bw:
        raise ValueError(f"{ref.sign.name}: text {gw}x{gh} does not fit {bw}x{bh}")
    ty, tx = oy + (bh - gh) // 2, ox + (bw - gw) // 2
    for gy, gx in zip(*np.nonzero(text_mask)):
        py, px = ty + gy, tx + gx
        out[py, px] = ink_here
    return out


def mapping_at(win, tpl):
    votes = {}
    for a, b in zip(win.ravel().tolist(), tpl.ravel().tolist()):
        d = votes.setdefault(a, {})
        d[b] = d.get(b, 0) + 1
    return {a: max(d, key=d.get) for a, d in votes.items()}


def apply(mdt, refs, masks):
    """(new MDT bytes, [(sign, block, x, y, mismatch)]) with every sign found redrawn."""
    d = bytearray(mdt)
    found = []
    for i, b in enumerate(blocks(mdt)):
        if b is None:
            continue
        off, w, h = b
        blk = np.frombuffer(bytes(d), np.uint8, w * h, off).reshape(h, w).copy()
        changed = False
        done = []  # text boxes already redrawn: two templates can match one sign
        for ref in refs:
            th, tw = ref.tpl.shape
            bx0, by0, bx1, by1 = ref.sign.box
            ox, oy = bx0 - ref.origin[0], by0 - ref.origin[1]
            bw, bh = bx1 - bx0, by1 - by0
            for mis, x, y in scan(ref.tpl, blk):
                box = (x + ox, y + oy, bw, bh)
                if any(box[0] < dx + dw and dx < box[0] + bw and box[1] < dy + dh and dy < box[1] + bh
                       for dx, dy, dw, dh in done):
                    continue
                done.append(box)
                win = blk[y:y + th, x:x + tw]
                new = redraw(win, ref, mapping_at(win, ref.tpl), masks[ref.sign.name], x, y)
                blk[y:y + th, x:x + tw] = new
                found.append((ref.sign.name, i, x, y, round(mis, 3)))
                changed = True
        if changed:
            d[off:off + w * h] = blk.tobytes()
    return bytes(d), found


def load_refs(sources, fonts):
    """References and text masks; sources: {map file name: (MDT bytes, MDS bytes)},
    fonts: (Galmuri11-Bold, Galmuri9)."""
    by_size = {11: fonts[0], 9: fonts[1]}
    refs = [reference(s, *sources[s.ref]) for s in SIGNS]
    masks = {s.name: glyph_mask(s.text, by_size[s.font], s.vertical, s.bold) for s in SIGNS}
    return refs, masks


def grp_edits(grp, refs, masks, bootlz):
    """{entry index: new packed MDT} for the maps of one ZROUP GRP, and the signs found."""
    out, found = {}, []
    for i, e in enumerate(grp.entries):
        if not e.name.endswith(".MDT"):
            continue
        mdt = bootlz.decode(e.data, 0)[0]
        new, f = apply(mdt, refs, masks)
        if f:
            out[i] = bootlz.encode(new)
            found += [(e.name,) + x for x in f]
    return out, found
