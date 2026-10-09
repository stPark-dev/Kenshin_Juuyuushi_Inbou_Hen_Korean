"""Title menu words: はじめから / つづきから in TITLE.BIN, redrawn in Hangul.

Established 2026-10-09 (docs/survey.md §3.1.8), DuckStation VRAM-write dump at
the title menu + TITLE.BIN layout:
- TITLE.BIN starts with 8 u32 entry offsets. Entries 0-2 and 6-7 are plain 8bpp
  pictures (u32 type, u16 w, u16 h, 256-colour CLUT, then tiles of u16 x, y, w, h
  + pixels): 0 the logo, 1 the copyright lines, 2 the background, 6-7 the hero
  portraits.
- Entry 3 is the menu: u32 member offsets x4 (from the entry start), u32 4, u32 4,
  the 256-colour CLUT (0 clear, 1 white, 2 black), sprite tables (members 0-2)
  and member 3, a bootlz-packed 96x128 8bpp sheet. The sheet is four 96x32
  strips; each word is 16 rows drawn as two sprites, rows 0-7 of one strip over
  rows 0-7 of the next (はじめから: strips 0 and 1, つづきから: strips 2 and 3).
- The words are white glyphs with 2 px vertical strokes and 1 px horizontal
  ones, outlined in black on all 8 sides.

Korean words are drawn in Galmuri14 widened by one pixel, the same way. Member 3
is the entry's last member: a smaller packed sheet is zero-padded to the source
slot, a larger one moves the entries after it and the offset table is rewritten.
"""

import struct

import bootlz

ENTRY = 3
SHEET_MEMBER = 3
WIDTH, HEIGHT, STRIP, HALF = 96, 128, 32, 8
WORDS = ("처음부터", "이어하기")  # はじめから, つづきから
WHITE, BLACK = 1, 2
TEXT_RIGHT = 76  # the source words end by this column; keep them near the cursor


def entries(title):
    """[(offset, end)] of the 8 entries in table order."""
    offs = struct.unpack_from("<8I", title)
    bounds = sorted(offs) + [len(title)]
    return [(o, bounds[bounds.index(o) + 1]) for o in offs]


def _glyph(font, ch):
    g = font[ch]
    w, h, xo, _ = g["bbx"]
    return [[g["bits"][r] >> (w - 1 - x) & 1 for x in range(w)] for r in range(h)], xo


def word(text, font):
    """16 rows x WIDTH of palette indices for one word, glyphs on rows 1-14."""
    ink = set()
    x = 0
    for ch in text:
        m, xo = _glyph(font, ch)
        for y, row in enumerate(m):
            for gx, b in enumerate(row):
                if b:
                    ink |= {(x + xo + gx, 1 + y), (x + xo + gx + 1, 1 + y)}
        x += xo + len(m[0]) + 2
    width = max(px for px, _ in ink) + 2
    shift = TEXT_RIGHT - width
    out = [[0] * WIDTH for _ in range(16)]
    for px, py in ink:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                out[py + dy][px + dx + shift] = BLACK
    for px, py in ink:
        out[py][px + shift] = WHITE
    return out


def sheet(font):
    s = bytearray(WIDTH * HEIGHT)
    for i, text in enumerate(WORDS):
        rows = word(text, font)
        for y, row in enumerate(rows):
            top = (2 * i + y // HALF) * STRIP + y % HALF
            s[top * WIDTH:(top + 1) * WIDTH] = bytes(row)
    return bytes(s)


def apply(title, font):
    """TITLE.BIN with the menu sheet redrawn and the entries after it moved."""
    spans = entries(title)
    at, end = spans[ENTRY]
    member = at + struct.unpack_from("<I", title, at + 4 * SHEET_MEMBER)[0]
    old, stop = bootlz.decode(title, member)
    if len(old) != WIDTH * HEIGHT or stop > end:
        raise ValueError(f"menu sheet is {len(old)} bytes, packed to 0x{stop:x}")
    packed = bootlz.encode(sheet(font))
    slot = max(end - member, len(packed) + (-len(packed) % 4))  # entries move only to grow
    grow = slot - (end - member)
    body = title[:member] + packed.ljust(slot, b"\0") + title[end:]
    offs = [o + grow if o >= end else o for o, _ in spans]
    return struct.pack("<8I", *offs) + body[32:]
