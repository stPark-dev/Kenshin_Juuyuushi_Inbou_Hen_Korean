"""Korean translation text -> GROUP string bytes.

Translation text uses the same token syntax as the decoded source (^x, cX/CX,
Nx, nx), plus an ASCII space for word spacing, which becomes N; (8 px,
runtime-established; an ASCII 0x20 byte stalls the game's text output).

Dialogue window (runtime-established, ZROUP40): 288 px per line, 16 px per
2-byte character, 8 px per N;. Overlong lines are wrapped at the last space and
continue with a full-width-space indent, as the original text does; the game's
own wrap ignores word boundaries. Only spaces typed in the translation are break
points (N; in the source is also used as column padding). ^N (inserted name)
is budgeted at NAME_PX.

Non-layout tokens (everything except characters, ^c and spaces) must appear in
the same order as in the source string.
"""

import re

import script

SP = "　"
LINE_PX = 288
BREAK_PX = 272  # a line followed by ^c; all 468 source lines of exactly 288px are last lines
TOKEN = re.compile(r"\^.|[cC][0-9a-fA-F]|N[!-~]|n[!-~]| |.", re.S)
NAME_PX = 96  # ^N inserts a character name; budget 6 full-width characters until name entry is surveyed
FIRST_CODE = 0x889F  # first code verified to render Hangul at runtime
LEADS = list(range(0x88, 0xA0)) + list(range(0xE0, 0xEB))


def is_hangul(ch):
    return "가" <= ch <= "힣"


def tokens(text):
    return TOKEN.findall(text)


def _is_layout(tok):
    return tok in ("^c", " ", "N;")


def _tok_width(tok):
    if tok == "^N":
        return NAME_PX
    if tok in (" ", "N;"):
        return 8
    if len(tok) == 1 and ord(tok) >= 0x80:
        return 16
    if len(tok) == 1:
        raise ValueError(f"unexpected character {tok!r}")
    return 0


def width(line):
    return sum(_tok_width(t) for t in tokens(line))


def _wrap(line, last_limit):
    """Split at typed spaces: pieces before a break <= BREAK_PX, the final piece <= last_limit."""
    toks, out = tokens(line), []
    while sum(_tok_width(t) for t in toks) > last_limit:
        acc, cut = 0, None
        for i, t in enumerate(toks):
            acc += _tok_width(t)
            if acc > BREAK_PX:
                break
            if t == " ":  # only typed spaces; N; may be alignment padding from the source
                cut = i
        if cut is None:
            raise ValueError(f"line exceeds {last_limit}px and has no space to break at: {''.join(toks)!r}")
        out.append("".join(toks[:cut]))
        toks = [SP] + toks[cut + 1 :]
    out.append("".join(toks))
    return out


def layout(text, limit=LINE_PX):
    """Lay out ^c-separated lines. A line followed by a break may use BREAK_PX
    (a full 288px line plus ^c leaves a blank line); the last line may use LINE_PX.
    A line without typed spaces may keep the source's width when `limit` exceeds
    LINE_PX (status-style rows padded with N;)."""
    segs, lines = text.split("^c"), []
    for i, seg in enumerate(segs):
        final = LINE_PX if i == len(segs) - 1 else BREAK_PX
        if " " not in tokens(seg):
            allowed = max(final, limit) if limit > LINE_PX else final
            if width(seg) > allowed:
                raise ValueError(f"line exceeds {allowed}px and has no space to break at: {seg!r}")
            lines.append(seg)
        else:
            lines += _wrap(seg, final)
    return "^c".join(lines)


def source_limit(src_raw):
    """Line limit for a translation: 288px, or the widest source line if the
    original consumer already displays wider lines (e.g. status windows)."""
    src = src_raw.decode("cp932")
    return max([LINE_PX] + [width(seg) for seg in src.split("^c")])


def assign_codes(hangul, reserved):
    """Map Hangul syllables (sorted) to unused 2-byte SJIS-range codes from 0x889F up."""
    out, need = {}, sorted(hangul)
    it = iter(need)
    cur = next(it, None)
    for lead in LEADS:
        for trail in range(0x40, 0xFD):
            if cur is None:
                return out
            code = bytes([lead, trail])
            if trail == 0x7F or (lead << 8 | trail) < FIRST_CODE or code in reserved:
                continue
            out[cur] = code
            cur = next(it, None)
    if cur is not None:
        raise ValueError(f"not enough codes for {len(need)} Hangul syllables")
    return out


def encode(text, src_raw, code_of):
    laid = layout(text, source_limit(src_raw))
    toks = tokens(laid)
    src_ctl = [t.raw.decode("ascii") for t in script.tokenize(src_raw) if t.kind != "char" and t.raw not in (b"^c", b"N;")]
    ko_ctl = [t for t in toks if not (len(t) == 1 and t != " ") and not _is_layout(t)]
    if ko_ctl != src_ctl:
        raise ValueError(f"control tokens differ from source: {ko_ctl} != {src_ctl}")
    out = bytearray()
    for t in toks:
        if t == " ":
            out += b"N;"
        elif len(t) == 2:
            out += t.encode("ascii")
        elif is_hangul(t):
            out += code_of[t]
        else:
            if ord(t) < 0x80:
                raise ValueError(f"ASCII character {t!r} is not allowed in translation text")
            try:
                b = t.encode("cp932")
            except UnicodeEncodeError:
                raise ValueError(f"character {t!r} has no Shift-JIS code") from None
            if len(b) != 2:
                raise ValueError(f"character {t!r} is not a 2-byte Shift-JIS character")
            out += b
    script.tokenize(bytes(out))
    return bytes(out)
