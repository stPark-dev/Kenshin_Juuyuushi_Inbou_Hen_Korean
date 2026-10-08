"""String references in GROUPnn.BIN and growth by appending to the string pool.

A string is referenced by its file-relative u32 offset (established at runtime:
script op 0x49 reads u8 window + unaligned u32 and adds the file load address).
Classification looks at every occurrence of a string's offset in [16, h2)
(the 16-byte header holds section offsets; h2 equals the first string offset):

  0x49, window 0..4, u32      text op
  op, 0x70, u32               kind-7 first operand of an op whose first operand is
                              typed (KIND7_OPS); 113 of 217 corpus sites decoded by
                              the control-flow walker, type byte always exactly 0x70
  aligned run of >= 2 u32     string table whose entries are all string starts
A looser "any 0x7? byte" rule is not used: it also matches immediates and ASCII.

movable       every occurrence is one of the known contexts
unknown       at least one occurrence is in an unexplained context
unreferenced  the offset does not occur at all

A replacement that fits its slot is written in place. A longer one is appended
after the pool (4-byte aligned) and all its sites are patched; existing offsets
never change, only h3 (font block position) moves. Anything else is refused.
"""

import struct
from dataclasses import dataclass

import script


@dataclass(frozen=True)
class Ref:
    status: str
    sites: list


KIND7_OPS = frozenset({0x40, 0x41, 0x42, 0x4C, 0x4D, 0x4E, 0x4F, 0x87})
HEADER = 16  # four u32 section offsets; h2 equals the first string offset, never a reference


def _table_sites(d, starts, end):
    sites, o = set(), HEADER
    while o + 4 <= end:
        run, q = [], o
        while q + 4 <= end and struct.unpack_from("<I", d, q)[0] in starts:
            run.append(q)
            q += 4
        if len(run) >= 2:
            sites.update(run)
            o = q
        else:
            o += 4
    return sites


def classify(g):
    d, end = g.data, g.header[2]
    starts = {s.offset for s in g.strings}
    table = _table_sites(d, starts, end)
    out = {}
    for s in g.strings:
        pat = struct.pack("<I", s.offset)
        sites, q = [], d.find(pat, HEADER, end)
        while q >= 0:
            sites.append(q)
            q = d.find(pat, q + 1, end)
        known = all(
            (q >= 2 and d[q - 2] == 0x49 and d[q - 1] <= 4)
            or (q >= 2 and d[q - 1] == 0x70 and d[q - 2] in KIND7_OPS)
            or q in table
            for q in sites
        )
        status = "unreferenced" if not sites else "movable" if known else "unknown"
        out[s.offset] = Ref(status, sites)
    return out


def rebuild(g, replacements, font_codes=None, font_glyphs=None):
    """Return GROUP bytes with `replacements` {offset: raw} applied (no NUL inside raw)."""
    slots = {s.offset: s.slot for s in g.strings}
    for off, raw in replacements.items():
        if off not in slots:
            raise KeyError(off)
        if b"\0" in raw:
            raise ValueError(f"0x{off:x}: replacement contains NUL")
        script.tokenize(raw)  # raises ValueError on unknown or truncated tokens
    h = g.header
    if h[3] % 4:
        raise ValueError("string pool end is not 4-byte aligned")
    cls = classify(g) if any(len(r) >= slots[o] for o, r in replacements.items()) else {}
    out = bytearray(g.data[: h[3]])
    blocked, patched = [], {}
    for off, raw in sorted(replacements.items()):
        if len(raw) < slots[off]:
            out[off : off + slots[off]] = raw + bytes(slots[off] - len(raw))
            continue
        ref = cls[off]
        if ref.status != "movable":
            blocked.append(f"0x{off:x} ({ref.status}, {len(raw)} bytes > slot {slots[off] - 1})")
            continue
        new = len(out)
        out += raw + b"\0"
        out += bytes(-len(out) % 4)
        for q in ref.sites:
            for b in range(q, q + 4):
                if b in patched:
                    raise ValueError(f"reference sites overlap at 0x{b:x} (0x{patched[b]:x} and 0x{off:x})")
                patched[b] = off
            struct.pack_into("<I", out, q, new)
    if blocked:
        raise ValueError("strings do not fit and cannot be moved: " + ", ".join(blocked))
    struct.pack_into("<I", out, 12, len(out))
    codes = g.font_codes if font_codes is None else font_codes
    glyphs = g.font_glyphs if font_glyphs is None else font_glyphs
    return bytes(out) + script.build_font_block(codes, glyphs)
