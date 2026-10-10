"""Overlay text: MAPCODE.Z32 (field) and BTLCODE.Z32 (battle) strings, and MAPCODE's font.

Both overlays load at 0x801AF034 (bootlz format, docs/survey.md §3.1.5).
Established 2026-10-09 by scanning every aligned u32 and lui/addiu pair:
- MAPCODE menu strings (character names, skill descriptions, menu labels, shop,
  memory card and name-entry text) at 0x801CAFBD-0x801CC026 are each reached by
  exactly one u32 in pointer tables, so they are repacked into the space the
  movable strings occupied (pointer tables in between are left alone).
- BTLCODE battle messages at 0x801E3FC4-0x801E4056: one u32 each, same treatment.
- A few strings are named by code (lui/addiu) or by index (BTLCODE's 16-byte
  battle name records); those are rewritten in place and must fit their slot.
Translations: text/ko/MAPCODE.json, text/ko/BTLCODE.json, ids "<OVL>:<hex addr>".
Menu text is full-width, a space becomes U+3000 (exetext.encode).
"""

import re
import struct

import textio
from mainprog import font_list

BASE = 0x801AF034
MOVABLE = {"MAPCODE": [(0x801CAFBD, 0x801CC026)], "BTLCODE": [(0x801E3FC4, 0x801E4056)]}
# address, slot bytes (string + padding, terminator excluded)
FIXED = {
    "MAPCODE": [(0x801CC028, 14), (0x801DD3D2, 24)],
    "BTLCODE": [(0x801C7968 + 16 * i, 12) for i in range(8)],
}
# limit in characters: the source length; skill descriptions may use the
# 14-cell box they share with item descriptions
DESC_RANGE, DESC_LIMIT = (0x801CB20C, 0x801CB840), 14
MAPCODE_FONT_LIST, MAPCODE_FONT_GLYPHS, MAPCODE_FONT_COUNT = 0x801CEAC4, 0x801CEDFC, 400

_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+")


def _u32_refs(data):
    refs = {}
    for i in range(0, len(data) - 3, 4):
        refs.setdefault(struct.unpack_from("<I", data, i)[0], []).append(BASE + i)
    return refs


def movable(name, data):
    """[(addr, raw, [ref sites])] for strings reached through pointer tables: every
    u32 in the overlay whose value starts a full-width string inside the range
    (a string may follow a pointer table with no terminator in between)."""
    refs = _u32_refs(data)
    out = []
    for lo, hi in MOVABLE[name]:
        for a in sorted(v for v in refs if lo <= v < hi):
            o = a - BASE
            e = data.index(b"\0", o)
            if e > o and _STR.fullmatch(data[o:e]):
                out.append((a, data[o:e], refs[a]))
    for (a, raw, _), (b, _, _) in zip(out, out[1:]):
        if b <= a + len(raw):
            raise ValueError(f"{name}: strings at 0x{a:x} and 0x{b:x} overlap")
    return out


def fixed(name, data):
    out = []
    for a, slot in FIXED[name]:
        raw = data[a - BASE:a - BASE + slot].rstrip(b"\0")
        out.append((a, raw, slot))
    return out


def extract(name, data):
    rows = []
    for a, raw, _ in movable(name, data):
        rows.append({"id": f"{name}:{a:x}", "offset": f"{name}:{a:x}", "src": raw.decode("cp932"),
                     "hash": textio.src_hash(raw), "slot": None,
                     "limit": max(DESC_LIMIT, len(raw) // 2) if DESC_RANGE[0] <= a < DESC_RANGE[1] else len(raw) // 2})
    for a, raw, slot in fixed(name, data):
        rows.append({"id": f"{name}:{a:x}", "offset": f"{name}:{a:x}", "src": raw.decode("cp932"),
                     "hash": textio.src_hash(raw), "limit": slot // 2, "slot": slot})
    return rows


def apply(name, data, texts):
    """Return overlay bytes with `texts` {id: raw} applied. Battle name records are
    padded to their 6 cells with full-width spaces like the source; other fixed
    slots end with zeros."""
    d = bytearray(data)
    mov = movable(name, data)
    for a, raw, slot in fixed(name, data):
        new = texts.get(f"{name}:{a:x}")
        if new is None:
            continue
        if len(new) > slot:
            raise ValueError(f"{name}:{a:x}: {len(new)} bytes, slot {slot}")
        if name == "BTLCODE":
            new = new + b"\x81\x40" * ((slot - len(new)) // 2)
        d[a - BASE:a - BASE + slot] = new.ljust(slot, b"\0")
    # free space: the slots the movable strings had (terminator included)
    spans = sorted((a, a + len(raw) + 1) for a, raw, _ in mov)
    free = []
    for a, b in spans:
        if free and free[-1][1] == a:
            free[-1][1] = b
        else:
            free.append([a, b])
    for a, b in free:
        d[a - BASE:b - BASE] = bytes(b - a)
    final = [(a, texts.get(f"{name}:{a:x}", raw), sites) for a, raw, sites in mov]
    where = {}
    for raw in sorted({r for _, r, _ in final}, key=lambda r: (-len(r), r)):  # ties by bytes: same output every run
        for p in free:
            if p[0] + len(raw) + 1 <= p[1]:
                where[raw] = p[0]
                p[0] += len(raw) + 1
                break
        else:
            raise ValueError(f"{name}: menu text does not fit ({len(raw)} bytes left over)")
        d[where[raw] - BASE:where[raw] - BASE + len(raw)] = raw
    for _, raw, sites in final:
        for s in sites:
            struct.pack_into("<I", d, s - BASE, where[raw])
    return bytes(d)


def mapcode_font(data):
    """MAPCODE's built-in font: {code: glyph} in list order (list and glyph array are
    found by the field text routine through lui/addiu at 0x801CD5F4/0x801CD600)."""
    codes = font_list(data, MAPCODE_FONT_LIST - BASE)  # CRLF line breaks take no glyph
    if len(codes) != MAPCODE_FONT_COUNT:
        raise ValueError(f"MAPCODE font: {len(codes)} characters, expected {MAPCODE_FONT_COUNT}")
    g = MAPCODE_FONT_GLYPHS - BASE
    return {c: data[g + 32 * i:g + 32 * i + 32] for i, c in enumerate(codes)}


def set_mapcode_font(data, glyphs):
    """Rewrite MAPCODE's font in place with at most 400 {code: glyph}."""
    if len(glyphs) > MAPCODE_FONT_COUNT:
        raise ValueError(f"MAPCODE font: {len(glyphs)} glyphs, room for {MAPCODE_FONT_COUNT}")
    d = bytearray(data)
    lst = b"".join(glyphs) + b"\0\0"
    d[MAPCODE_FONT_LIST - BASE:MAPCODE_FONT_GLYPHS - BASE] = lst.ljust(MAPCODE_FONT_GLYPHS - MAPCODE_FONT_LIST, b"\0")
    g = MAPCODE_FONT_GLYPHS - BASE
    d[g:g + 32 * MAPCODE_FONT_COUNT] = bytes(32 * MAPCODE_FONT_COUNT)
    for i, c in enumerate(glyphs):
        d[g + 32 * i:g + 32 * i + 32] = glyphs[c]
    return bytes(d)
