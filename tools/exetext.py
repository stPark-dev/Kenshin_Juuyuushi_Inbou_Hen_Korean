"""Main-program text: item names, item descriptions and skill names, and the menu font.

Established 2026-10-09 (docs/survey.md §3.1.5): each table is u32 pointers into a
string pool right after it, and code (main, MAPCODE, BTLCODE) only ever uses the
table bases, so the three pools form one space the strings can be repacked into.
The menu font is 16x16 1bpp glyphs (NAMEFONT layout) at FONT_GLYPHS and a code
list that the lookup at 0x80033B10 finds through `lui a1 / addiu a1` (0x80033B10,
0x80033B14). The glyph array keeps its address; the list moves behind the glyphs
or, when the glyphs fill the area, into free pool space.

Translations: text/ko/MAIN.json, ids "MAIN:<table>:<index>", same entry format as
the scene files. A menu string is all full-width: a space becomes U+3000.
"""

import re
import struct

import koenc
import textio
from mainprog import BASE, FONT_GLYPHS, FONT_LIST

# name, table address, entries, max characters. Item names (source max 6) end
# before the count column and descriptions (source max 14) fill their box; a
# skill name ends before its cost column after 6 characters (runtime, 2026-10-09),
# so a skill may only be longer where its source already is (enemy skills).
TABLES = (("item", 0x8003A09C, 175, 6), ("desc", 0x8003A940, 175, 14), ("skill", 0x80029A10, 138, 6))
POOLS = ((0x8003A358, 0x8003A940), (0x8003ABFC, 0x8003BAE0), (0x80029C38, 0x8002A140))
FONT_END = 0x800395AC  # list terminator end; data follows
LIST_LUI, LIST_ADDIU = 0x80033B10, 0x80033B14


def _cstr(main, addr):
    o = addr - BASE
    return main[o:main.index(b"\0", o)]


def strings(main):
    """[(id, raw)] in table order."""
    out = []
    for name, at, n, _ in TABLES:
        for i, p in enumerate(struct.unpack_from(f"<{n}I", main, at - BASE)):
            out.append((f"MAIN:{name}:{i:03d}", _cstr(main, p)))
    return out


def extract(main):
    limit = {name: lim for name, _, _, lim in TABLES}
    return [{"id": sid, "offset": sid, "src": raw.decode("cp932"), "hash": textio.src_hash(raw),
             "limit": max(limit[sid.split(":")[1]], len(raw) // 2)} for sid, raw in strings(main)]


def encode(text, code_of, limit):
    """Korean menu text -> bytes. Every character is one 16 px cell."""
    if len(text) > limit:
        raise ValueError(f"{text!r}: {len(text)} characters, limit {limit}")
    out = b""
    for c in text.replace(" ", "　"):
        if koenc.is_hangul(c):
            out += code_of[c]
        else:
            b = c.encode("cp932")
            if len(b) != 2:
                raise ValueError(f"{text!r}: {c!r} is not a full-width character")
            out += b
    return out


def font_codes(main):
    o = FONT_LIST - BASE
    codes = []
    while main[o:o + 1] not in (b"\0", b"\x1a"):
        if main[o:o + 2] != b"\r\n":
            codes.append(bytes(main[o:o + 2]))
        o += 2
    return codes


def _lui_addiu(addr):
    hi = (addr + 0x8000) >> 16 & 0xFFFF
    lo = addr & 0xFFFF
    return 0x3C050000 | hi, 0x24A50000 | lo  # lui a1 / addiu a1, a1


def apply(main, texts, glyphs):
    """Return the main program with `texts` {id: raw} replacing table strings and the
    menu font rebuilt from `glyphs` {code: 32 bytes} (any order, kept as given).
    The glyphs and their list go first; strings fill the pools, then whatever the
    font leaves of its area."""
    old = struct.unpack_from("<2I", main, LIST_LUI - BASE)
    if old != _lui_addiu(FONT_LIST):
        raise ValueError("font lookup code is not the expected lui/addiu pair")
    m = bytearray(main)
    codes = list(glyphs)
    area = FONT_END - FONT_GLYPHS
    lst = b"".join(codes) + b"\0\0"
    if 32 * len(codes) > area:
        raise ValueError(f"menu font: {len(codes)} glyphs, room for {area // 32}")
    m[FONT_GLYPHS - BASE:FONT_END - BASE] = bytes(area)
    for i, c in enumerate(codes):
        m[FONT_GLYPHS - BASE + 32 * i:FONT_GLYPHS - BASE + 32 * i + 32] = glyphs[c]
    free = [list(p) for p in POOLS]
    for a, b in POOLS:
        m[a - BASE:b - BASE] = bytes(b - a)
    glyph_end = FONT_GLYPHS + 32 * len(codes)
    if glyph_end + len(lst) <= FONT_END:
        list_at = glyph_end
        free.append([glyph_end + len(lst), FONT_END])
    else:
        list_at = None

    def alloc(size, align=1):
        for p in free:
            start = -(-p[0] // align) * align
            if start + size <= p[1]:
                p[0] = start + size
                return start
        raise ValueError(f"menu text does not fit: no room for {size} more bytes "
                         f"({sum(max(0, q - p) for p, q in free)} bytes left in pieces)")

    if list_at is None:
        list_at = alloc(len(lst), 2)
    m[list_at - BASE:list_at - BASE + len(lst)] = lst
    struct.pack_into("<2I", m, LIST_LUI - BASE, *_lui_addiu(list_at))
    # strings: first-fit, longest first, identical strings shared
    final = {sid: texts.get(sid, raw) for sid, raw in strings(main)}
    where = {}
    for raw in sorted(set(final.values()), key=lambda r: (-len(r), r)):  # ties by bytes: same output every run
        where[raw] = alloc(len(raw) + 1)
        m[where[raw] - BASE:where[raw] - BASE + len(raw)] = raw
    for name, at, n, _ in TABLES:
        for i in range(n):
            struct.pack_into("<I", m, at - BASE + 4 * i, where[final[f"MAIN:{name}:{i:03d}"]])
    return bytes(m)


_STRING = re.compile(rb"(?<=\x00)(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e])+(?=\x00)")


def _string_codes(data, base, skip=()):
    out = set()
    for x in _STRING.finditer(data):
        if any(a <= x.start() + base < b for a, b in skip):
            continue
        s = x.group()
        try:
            t = s.decode("cp932")
        except UnicodeDecodeError:
            continue
        if not any(ord(c) > 0x3000 for c in t):
            continue
        i = 0
        while i < len(s):
            if s[i] >= 0x81:
                out.add(s[i:i + 2])
                i += 2
            else:
                i += 1
    return out


def kept_codes(main, btlcode):
    """Menu-font characters that must stay: every non-kanji (kana, digits,
    punctuation), and any character of another string in the main program or of
    a BTLCODE string (battle has no other font). MAPCODE strings are covered by
    MAPCODE's own font, rebuilt alongside (ovltext). The string scan is
    conservative: code bytes that happen to decode as text only keep extra
    characters."""
    font = font_codes(main)
    skip = list(POOLS) + [(FONT_GLYPHS, FONT_END)]
    other = _string_codes(main, BASE, skip) | _string_codes(btlcode, 0)
    return [c for c in font if c[0] < 0x88 or c in other]
