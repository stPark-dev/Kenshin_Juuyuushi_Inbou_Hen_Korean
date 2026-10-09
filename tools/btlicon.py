"""Battle command icons: the 戦道交逃 / 上中下必 sheet in BTLCODE, redrawn in Hangul.

Established 2026-10-09 (docs/survey.md §3.1.7), DuckStation VRAM-write dump in
battle + BTLCODE disassembly:
- BTLCODE holds a small archive at 0x801E0484 (u32 member offsets from the
  archive start: 16 CLUT sets of 16 colours each x2, then the RLE sheet). The
  battle setup (0x801B80FC, 0x801B24A0) loads member 0 as CLUTs and decodes
  member 3 with the RLE routine at 0x801B0854 to 0x801EA18C, then uploads it to
  VRAM as 64x128 halfwords: a 256x128 4bpp sheet.
- RLE: u32 decoded size, u16 width in bytes, u16 height, u8 escape byte, then
  bytes; the escape byte is followed by value and count (1-255), any other byte
  is a literal. The width and height are not read by the decoder.
- Sheet cells are 24x24 px: rows 0 and 1 hold the commands 戦 道 交 逃 and the
  attack heights 上 中 下 必, each as a small icon (cell x = 48i, idle) and a
  large one (x = 48i + 24, selected). The sprite's CLUT gives each icon its
  colour (上 green, 中 blue, 下 magenta, ...), so only the glyph is redrawn.
- Row 2 holds a 突 emblem by the top gauge (x 192, y 48); it is kept for now.

Glyphs come from Galmuri11 Bold (large, 2 px strokes) and Galmuri9 (small),
white (index 15) with a black (1) and dark (2) drop shadow, on a panel
repainted in the source icons' colours.
"""

import struct
from collections import Counter

BASE = 0x801AF034
ARCHIVE = 0x801E0484
SHEET_MEMBER = 3
WIDTH, HEIGHT = 128, 128  # bytes per row (256 px at 4bpp), rows
FONT_FILES = ("Galmuri11-Bold.bdf", "Galmuri9.bdf")  # (large, small)
# Korean readings of the attack heights, as the dialogue names them (상단, 중단,
# 하단, 필살기); the commands by their first syllable (전투, 도구, 교대, 퇴각:
# 도망 would clash with 도구)
ICONS = (("전", 0, 0), ("도", 48, 0), ("교", 96, 0), ("퇴", 144, 0),
         ("상", 0, 24), ("중", 48, 24), ("하", 96, 24), ("필", 144, 24))


def unrle(data, pos=0):
    """(decoded bytes, packed length) of the RLE stream at `pos`."""
    n = struct.unpack_from("<I", data, pos)[0]
    esc = data[pos + 8]
    p, out = pos + 9, bytearray()
    while len(out) < n:
        c = data[p]
        p += 1
        if c == esc:
            out += bytes([data[p]]) * data[p + 1]
            p += 2
        else:
            out.append(c)
    if len(out) != n:
        raise ValueError(f"RLE run overshoots: {len(out)} bytes, header says {n}")
    return bytes(out), p - pos


def rle(data, width, height, esc=None):
    """Encode like the source: runs of 3 or more, and the escape byte itself, as
    escape/value/count. The default escape is the rarest byte value."""
    if esc is None:
        cnt = Counter(data)
        esc = min(range(256), key=lambda v: cnt.get(v, 0))
    out = bytearray(struct.pack("<IHHB", len(data), width, height, esc))
    i = 0
    while i < len(data):
        v, n = data[i], 1
        while i + n < len(data) and data[i + n] == v and n < 255:
            n += 1
        if n >= 3 or v == esc:
            k = n if n >= 3 else 1
            out += bytes([esc, v, k])
            i += k
        else:
            out.append(v)
            i += 1
    return bytes(out)


def sheet_at(btlcode):
    """File offset of the RLE sheet in BTLCODE."""
    a = ARCHIVE - BASE
    return a + struct.unpack_from("<I", btlcode, a + 4 * SHEET_MEMBER)[0]


def _rows(lines):
    out = [[0 if c == "." else int(c, 16) for c in r] for r in lines]
    if len(out) != 24 or any(len(r) != 24 for r in out):
        raise ValueError("icon template is not 24x24")
    return out


_BLANK = "." * 24
# frames redrawn from the source icons with the glyph taken out; panel cells are
# filled by _panel
LARGE = _rows([_BLANK] * 3 + [
    "..111111........1111111.",
    ".1ff8f881111111118888881",
    ".1ff8f881111111118888881",
    ".1f777771222222227777771",
    ".18511111222222221111871",
] + [".1851" + "2" * 15 + "1871"] * 9 + [
    ".17788882444444428888871",
    ".17777772111111127777771",
    ".17777772111111127777771",
    ".11111111.......11111111",
] + [_BLANK] * 3)
SMALL = _rows([_BLANK] * 5 + [
    "......11111..111111.....",
    ".....1f8f88888888881....",
    "....1ff77777778888881...",
] + ["....185" + "3" * 10 + "1871..."] * 8 + [
    "....17888884147777771...",
    ".....177777414777771....",
    "......111111.111111.....",
] + [_BLANK] * 5)
LARGE_PANEL = ({(x, y) for y in range(8, 17) for x in range(5, 20)} | {(x, 17) for x in range(9, 16)}
               | {(x, y) for y in (6, 7) for x in range(9, 17)})
SMALL_PANEL = {(x, y) for y in range(8, 16) for x in range(7, 17)}


def _bitmap(font, ch):
    g = font[ch]
    w, h = g["bbx"][:2]
    return [[g["bits"][r] >> (w - 1 - x) & 1 for x in range(w)] for r in range(h)]


def icon(ch, large, font):
    """24x24 palette indices of one icon. The large glyph sits on the panel
    bottom (row 16), the small one on row 15, both centred on the panel."""
    t = [r[:] for r in (LARGE if large else SMALL)]
    cells = LARGE_PANEL if large else SMALL_PANEL
    for x, y in cells:  # dark edge on the left (and the open top of the large panel)
        t[y][x] = (2 if x < 7 or y < 8 else 4) if large else (3 if x < 9 else 4)
    m = _bitmap(font, ch)
    h, w = len(m), len(m[0])
    left = (5 + (15 - w) // 2) if large else (7 + (10 - w) // 2)
    top = (17 if large else 16) - h
    g = {(left + x, top + y) for y in range(h) for x in range(w) if m[y][x]}
    near = {(x + 1, y + 1) for x, y in g} - g
    far = {(x + 2, y + 2) for x, y in g} - g - near
    for x, y in far & cells:
        t[y][x] = 2
    for x, y in near | g:
        if not (0 <= x < 24 and 0 <= y < 24):
            raise ValueError(f"icon {ch}: glyph leaves the cell")
        t[y][x] = 15 if (x, y) in g else 1
    return t


def draw(sheet, fonts):
    """Sheet bytes with every ICONS cell redrawn; fonts = (large, small) BDFs."""
    s = bytearray(sheet)
    for ch, cx, cy in ICONS:
        for large in (False, True):
            t = icon(ch, large, fonts[0] if large else fonts[1])
            ox = cx + (24 if large else 0)
            for y in range(24):
                for x in range(24):
                    i, sh = (cy + y) * WIDTH + (ox + x) // 2, 4 * ((ox + x) & 1)
                    s[i] = (s[i] & ~(15 << sh) & 0xFF) | (t[y][x] << sh)
    return bytes(s)


def apply(btlcode, fonts):
    """BTLCODE with the command sheet redrawn, packed into the source's slot (up
    to the next 4-byte boundary after the source stream)."""
    at = sheet_at(btlcode)
    sheet, size = unrle(btlcode, at)
    w, h = struct.unpack_from("<HH", btlcode, at + 4)
    if (w, h, len(sheet)) != (WIDTH, HEIGHT, WIDTH * HEIGHT):
        raise ValueError(f"command sheet is {w}x{h}, {len(sheet)} bytes")
    packed = rle(draw(sheet, fonts), WIDTH, HEIGHT)
    room = -(-size // 4) * 4
    if len(packed) > room:
        raise ValueError(f"command sheet packs to {len(packed)} bytes, room {room}")
    d = bytearray(btlcode)
    n = max(size, len(packed))
    d[at:at + n] = packed.ljust(n, b"\0")
    return bytes(d)
