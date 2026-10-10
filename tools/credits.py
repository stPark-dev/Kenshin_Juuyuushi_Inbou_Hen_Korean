"""Ending credits: the text and font inside ROLL.Z32 (SYSTEM.GRP), redrawn in Hangul.

Established 2026-10-10 (docs/survey.md §3.1.9): ROLL.Z32 is a bootlz overlay
loaded at 0x801AF034. The credits are Shift-JIS text with CRLF line ends and a
NUL at the end; one line at a time is drawn into a 512 px wide 4bpp buffer from
the left (at most 64 half-width columns, a 2-byte code takes 2), which is shown
squeezed to half its width while it scrolls up. 2-byte codes (lead 0x80-0x9F,
0xE0-0xFF) are looked up in ROLL's own font (code list of 32 per CRLF line, then
16x16 glyphs, the kfont layout) by the main program's 0x80033B20; half-width
bytes use an 8x16 font in ROLL. The text, the list and the glyphs are each
reached through one lui/addiu pair; the table after them is left in place.

Hangul (D34): a syllable is drawn twice as wide and split into two 2-byte codes,
the left and the right half, so that it shows at the size of dialogue text
(16 syllables per line at most). Kept text (people and company names, D34)
uses the source glyphs.

Translations: text/ko/ROLL.json, ids "ROLL:<line number from 1>". A translation
keeps the line count; "{a:b}" copies characters a..b of the source line (Python
slice), so names are kept without writing them into the translation file.
"""

import re
import struct

import kfont
import koenc
import textio

BASE = 0x801AF034
TEXT, FONT_LIST, FONT_GLYPHS, TABLE = 0x801B1ED0, 0x801B305C, 0x801B33DC, 0x801B69E0
# (lui, addiu) of the three references
TEXT_REF, LIST_REF, GLYPH_REF = (0x801AF8DC, 0x801AF8E0), (0x801B0D84, 0x801B0D88), (0x801B0D8C, 0x801B0D90)
COLUMNS = 64  # half-width columns of the line buffer
PER_LINE = 32  # codes per CRLF line of the font list
SLICE = re.compile(r"\{(\d*):(\d*)\}")


def _off(addr):
    return addr - BASE


def _hi_lo(data, ref):
    hi = struct.unpack_from("<I", data, _off(ref[0]))[0] & 0xFFFF
    lo = struct.unpack_from("<h", data, _off(ref[1]))[0]
    return (hi << 16) + lo


def _set_hi_lo(d, ref, addr):
    for at, val in zip(ref, ((addr + 0x8000) >> 16, addr & 0xFFFF)):
        word = struct.unpack_from("<I", d, _off(at))[0]
        struct.pack_into("<I", d, _off(at), word & 0xFFFF0000 | val)


def check(data):
    got = [_hi_lo(data, r) for r in (TEXT_REF, LIST_REF, GLYPH_REF)]
    if got != [TEXT, FONT_LIST, FONT_GLYPHS]:
        raise ValueError(f"ROLL references {[hex(a) for a in got]} differ from the surveyed layout")


def lines(data):
    """Source lines (raw bytes, CRLF and NUL excluded)."""
    end = data.index(b"\0", _off(TEXT))
    return data[_off(TEXT):end].split(b"\r\n")


def is_wide(b):
    return 0x80 <= b <= 0x9F or b >= 0xE0


def codes(raw):
    """2-byte codes of a line in order."""
    out, i = [], 0
    while i < len(raw):
        if is_wide(raw[i]):
            out.append(raw[i:i + 2])
            i += 2
        else:
            i += 1
    return out


def columns(raw):
    return sum(2 if is_wide(b) else 1 for b in _lead_bytes(raw))


def _lead_bytes(raw):
    i = 0
    while i < len(raw):
        yield raw[i]
        i += 2 if is_wide(raw[i]) else 1


def font(data):
    """{code: glyph} of ROLL's font."""
    out, at = [], _off(FONT_LIST)
    while data[at] not in (0, 0x1A):
        c = data[at:at + 2]
        if c != b"\r\n":
            out.append(bytes(c))
        at += 2
    g = _off(FONT_GLYPHS)
    return {c: data[g + 32 * i:g + 32 * i + 32] for i, c in enumerate(out)}


def extract(data):
    rows = []
    for i, raw in enumerate(lines(data)):
        if codes(raw):  # only lines with full-width text can need a translation
            rows.append({"id": f"ROLL:{i + 1:03d}", "offset": i, "src": raw.decode("cp932"),
                         "hash": textio.src_hash(raw), "slot": None, "limit": COLUMNS})
    return rows


def expand(text, src):
    """Translation text with its {a:b} slices of the source line filled in."""
    return SLICE.sub(lambda m: src[int(m[1]) if m[1] else None:int(m[2]) if m[2] else None], text)


def encode(text, src, code_of):
    """Line bytes for a translation; a Hangul syllable becomes its two half codes."""
    if "\r" in text or "\n" in text:
        raise ValueError("a translation is one line")
    out = bytearray()
    for ch in expand(text, src):
        if koenc.is_hangul(ch):
            out += code_of[ch, 0] + code_of[ch, 1]
        else:
            try:
                out += ch.encode("cp932")
            except UnicodeEncodeError:
                raise ValueError(f"character {ch!r} has no Shift-JIS code") from None
    if columns(out) > COLUMNS:
        raise ValueError(f"{columns(out)} columns, the line holds {COLUMNS}")
    return bytes(out)


def halves(glyph, box):
    """(left, right) 16x16 glyphs of a Hangul glyph drawn twice as wide."""
    px = kfont.pixels(kfont.render(glyph, box))
    wide = [[b for b in row for _ in (0, 1)] for row in px]
    return tuple(_pack([row[h * 16:h * 16 + 16] for row in wide]) for h in (0, 1))


def _pack(rows):
    out = bytearray(32)
    for y, row in enumerate(rows):
        v = sum(b << (15 - x) for x, b in enumerate(row))
        struct.pack_into("<H", out, 2 * (y ^ 1), v)
    return bytes(out)


def apply(data, texts, galmuri, box, fallback=None):
    """ROLL bytes with {line index: translation} applied and the font rebuilt from the
    final text. Text, list and glyphs go back to back in the space the three had;
    whatever does not fit goes after the end of the file, which then grows."""
    check(data)
    src = lines(data)
    hangul = {ch for t in texts.values() for ch in expand(t, "") if koenc.is_hangul(ch)}
    missing = sorted(c for c in hangul if c not in galmuri)
    if missing:
        raise ValueError(f"Hangul font has no glyph for {''.join(missing)}")
    kept = [raw for i, raw in enumerate(src) if i not in texts]
    kept += [expand(t, src[i].decode("cp932")).encode("cp932", "ignore") for i, t in texts.items()]
    reserved = {c for raw in kept for c in codes(raw)}
    code_of = koenc.assign_codes({(c, h) for c in hangul for h in (0, 1)}, reserved)
    new = [encode(texts[i], raw.decode("cp932"), code_of) if i in texts else raw for i, raw in enumerate(src)]
    old = font(data)
    glyph = {}
    for c in sorted(hangul):
        glyph[code_of[c, 0]], glyph[code_of[c, 1]] = halves(galmuri[c], box)
    order = []
    for raw in new:
        for c in codes(raw):
            if c not in order:
                order.append(c)
    for c in order:
        if c not in glyph:
            g = old.get(c) or (fallback or {}).get(c)
            if g is None:
                raise ValueError(f"no glyph for {c.decode('cp932', 'replace')}")
            glyph[c] = g
    text = b"\r\n".join(new) + b"\0"
    lst = b"".join(b"".join(order[i:i + PER_LINE]) + (b"\r\n" if i + PER_LINE < len(order) else b"")
                   for i in range(0, len(order), PER_LINE)) + b"\0\0"
    glyphs = b"".join(glyph[c] for c in order)
    d = bytearray(data)
    lo, hi = _off(TEXT), _off(TABLE)
    d[lo:hi] = bytes(hi - lo)
    at = {}
    for name, blob in (("text", text), ("list", lst), ("glyphs", glyphs)):
        p = lo + (-lo % 4)
        if p + len(blob) <= hi:
            lo = p + len(blob)
        else:
            d += bytes(-len(d) % 4)
            p = len(d)
            d += bytes(len(blob))
        d[p:p + len(blob)] = blob
        at[name] = BASE + p
    for ref, name in ((TEXT_REF, "text"), (LIST_REF, "list"), (GLYPH_REF, "glyphs")):
        _set_hi_lo(d, ref, at[name])
    return bytes(d), {"lines": len(texts), "glyphs": len(order), "hangul": len(hangul),
                      "size": len(d), "grew": len(d) - len(data)}
