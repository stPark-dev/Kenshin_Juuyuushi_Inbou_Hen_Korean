"""Hangul glyphs from a BDF font in the game's 16x16 1bpp glyph format.

Game format (established: NAMEFONT and scene font blocks, runtime-checked with
Hangul): 16 rows of u16 little-endian, bit 15 = leftmost pixel, rows stored in
swapped pairs (row y at index y ^ 1). Glyphs are placed in the font's Hangul
bounding box, centred in the 16x16 cell, bottom-aligned on the box baseline.
"""

import struct

CELL = 16


def load_bdf(path):
    glyphs, cur = {}, None
    with open(path, encoding="latin-1") as f:
        for line in f:
            p = line.split()
            if not p:
                continue
            if p[0] == "ENCODING":
                cur = {"code": int(p[1])}
            elif p[0] == "BBX" and cur is not None:
                cur["bbx"] = tuple(map(int, p[1:5]))
            elif p[0] == "BITMAP" and cur is not None:
                cur["rows"] = []
            elif p[0] == "ENDCHAR" and cur is not None:
                if 0 <= cur["code"] < 0x110000 and "bbx" in cur:
                    w = cur["bbx"][0]
                    cur["bits"] = [r >> (len(h) * 4 - w) if len(h) * 4 >= w else r for r, h in cur["rows"]]
                    glyphs[chr(cur["code"])] = cur
                cur = None
            elif cur is not None and "rows" in cur:
                cur["rows"].append((int(p[0], 16), p[0]))
    return glyphs


def hangul_box(font):
    hg = [g for ch, g in font.items() if "가" <= ch <= "힣"]
    if not hg:
        raise ValueError("font has no Hangul syllables")
    return max(g["bbx"][0] for g in hg), max(g["bbx"][1] + g["bbx"][3] for g in hg)


def render(glyph, box):
    wmax, hmax = box
    if wmax > CELL or hmax > CELL:
        raise ValueError(f"box {box} exceeds the {CELL}x{CELL} cell")
    w, h, xo, yo = glyph["bbx"]
    top = (CELL - hmax) // 2 + (hmax - (yo + h))
    left = (CELL - wmax) // 2 + xo
    rows = [0] * CELL
    for r, bits in enumerate(glyph["bits"]):
        for x in range(w):
            if bits >> (w - 1 - x) & 1:
                yy, xx = top + r, left + x
                if not (0 <= yy < CELL and 0 <= xx < CELL):
                    raise ValueError(f"glyph U+{glyph['code']:04X} pixel ({xx},{yy}) outside the cell")
                rows[yy] |= 1 << (CELL - 1 - xx)
    out = bytearray(32)
    for y in range(CELL):
        struct.pack_into("<H", out, 2 * (y ^ 1), rows[y])
    return bytes(out)


def pixels(glyph_bytes):
    rows = [struct.unpack_from("<H", glyph_bytes, 2 * (y ^ 1))[0] for y in range(CELL)]
    return [[rows[y] >> (CELL - 1 - x) & 1 for x in range(CELL)] for y in range(CELL)]
