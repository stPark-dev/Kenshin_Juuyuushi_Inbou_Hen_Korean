"""GROUPnn.BIN script text and scene font block.

Layout, established on all 58 GROUP files of SCPS-10048:
  u32 h0, h1, h2, h3 section offsets; h2..h3 is the string pool
  (NUL-terminated, each string starts 4-byte aligned), h3..end is the scene
  font block: u32 L, SJIS code list (first-appearance order), a 0000
  terminator padded to 4 bytes so L = align4(4 + 2n + 2), then n 32-byte
  glyphs (16x16 1bpp, u16 LE rows, bit 15 = leftmost, rows stored y^1).

Token grammar inside strings (raw bytes are kept; meanings partly unknown):
  ^x      control (^c = line break; first segment is the speaker)
  cX, CX  colour (X = hex digit)
  Nx      horizontal space (N; = 8 px, established at runtime)
  nx      argument token, meaning unknown
  2-byte  Shift-JIS character
"""

import struct
from dataclasses import dataclass

HEX = b"0123456789abcdefABCDEF"


@dataclass(frozen=True)
class Token:
    kind: str
    raw: bytes


@dataclass(frozen=True)
class StringEntry:
    offset: int
    raw: bytes
    slot: int  # bytes available from offset up to the next string


@dataclass(frozen=True)
class Group:
    data: bytes
    header: tuple
    strings: tuple
    font_codes: list
    font_glyphs: list


def _is_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def tokenize(raw):
    toks, i = [], 0
    while i < len(raw):
        b = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else None
        if nxt is None:
            raise ValueError(f"truncated token at byte {i}: {raw[i:]!r}")
        if b == 0x5E:
            kind = "ctl"
        elif b in b"cC" and nxt in HEX:
            kind = "color"
        elif b == 0x4E and 0x21 <= nxt <= 0x7E:
            kind = "space"
        elif b == 0x6E and 0x21 <= nxt <= 0x7E:
            kind = "arg"
        elif _is_lead(b) and 0x40 <= nxt <= 0xFC and nxt != 0x7F:
            kind = "char"
        else:
            raise ValueError(f"unknown byte 0x{b:02x} at {i}")
        toks.append(Token(kind, raw[i : i + 2]))
        i += 2
    return toks


def font_block_size(n):
    return (4 + 2 * n + 2 + 3) & ~3


def parse_group(data):
    data = bytes(data)
    if len(data) < 16:
        raise ValueError("GROUP shorter than its header")
    h = struct.unpack_from("<4I", data, 0)
    if not (16 <= h[0] <= h[1] <= h[2] <= h[3] <= len(data) - 4):
        raise ValueError(f"bad section offsets {[hex(x) for x in h]}")
    starts, o = [], h[2]
    while o < h[3]:
        if data[o] == 0:
            o += 1
            continue
        end = data.find(b"\0", o, h[3])
        if end < 0:
            raise ValueError(f"string at 0x{o:x} is not terminated inside the pool")
        starts.append((o, end))
        o = end
    strings = tuple(
        StringEntry(s, data[s:e], (starts[i + 1][0] if i + 1 < len(starts) else h[3]) - s)
        for i, (s, e) in enumerate(starts)
    )
    L = struct.unpack_from("<I", data, h[3])[0]
    n, rem = divmod(len(data) - h[3] - L, 32)
    if L < 4 or rem or n < 0 or font_block_size(n) != L:
        raise ValueError(f"font block L={L} does not match {len(data) - h[3]} bytes")
    base = h[3]
    codes = [data[base + 4 + 2 * i : base + 6 + 2 * i] for i in range(n)]
    glyphs = [data[base + L + 32 * i : base + L + 32 * (i + 1)] for i in range(n)]
    return Group(data, h, strings, codes, glyphs)


def build_font_block(codes, glyphs):
    if len(codes) != len(glyphs) or any(len(c) != 2 for c in codes) or any(len(g) != 32 for g in glyphs):
        raise ValueError("font codes and glyphs must pair as 2-byte codes and 32-byte glyphs")
    L = font_block_size(len(codes))
    return struct.pack("<I", L) + b"".join(codes) + bytes(L - 4 - 2 * len(codes)) + b"".join(glyphs)


def serialize_group(g):
    h = g.header
    out = bytearray(g.data[: h[3]])
    for s in g.strings:
        if len(s.raw) >= s.slot:
            raise ValueError(f"0x{s.offset:x}: string does not fit its slot")
        out[s.offset : s.offset + s.slot] = s.raw + bytes(s.slot - len(s.raw))
    return bytes(out) + build_font_block(g.font_codes, g.font_glyphs)
