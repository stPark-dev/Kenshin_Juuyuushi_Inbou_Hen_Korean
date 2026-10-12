"""World map place names: the label sheet in AMAPDAT.BIN and the location table in MAPCODE.

Established 2026-10-12 (docs/survey.md §3.1.12):
- SYSTEM.GRP AMAPDAT.BIN: u32 offsets from byte 0; the entry at 0x4231C is a
  16-colour CLUT (1 white, 2 grey, 3 dark: text, shading, outline) and the entry
  at 0x4233C is u32 0x01000020 (32 halfwords x 256) followed by a raw 4bpp sheet,
  128 x 256 pixels: one 16 px row of place names per sheet row.
- MAPCODE.Z32 0x801DF408 (file offset TABLE): 16-byte location records, record 0
  empty, 1..25 the places: u16 x, u16 y (map), u8 area, u8 width in 16 px
  cells, u8 u, u8 v (sheet), 4 link bytes, u32 pointer. The label drawing code
  (0x801DF218) reads the u16 at +6 as the sprite's u,v and byte +5 << 4 as its
  width; the height is 16. Some labels are parts of a sheet row (竹林 of
  日光町竹林, 横浜 and 室山 of 南の沼室山横浜).

The Korean labels are drawn in Galmuri11-Bold (the weight of the original
letters) with a one pixel outline and packed into
the sheet anew; each record gets its own width, u and v. Labels are left-aligned
in their cells like the original letters; the grey shading (colour 2) is not used.
Nothing else draws from the sheet (the unused 町 of row 1 is dropped).
"""

import struct

import numpy as np

import kfont
import mainprog

SHEET_AT = 0x4233C + 4  # pixels; the u32 before them is SHEET_HEAD
SHEET_HEAD = 0x01000020
SHEET_W, SHEET_H = 128, 256
SHEET_BYTES = SHEET_W * SHEET_H // 2
TABLE = 0x801DF408 - mainprog.MAPCODE_BASE
POINTER = (0x801D0000, 0x801E0000)
FILL, EDGE = 1, 3
GAP, SPACE = 1, 4  # px between glyphs, width of a space

# record order 1..25 (Japanese source in the comments)
LABELS = (
    "아소산",  # 麻生の山
    "닛코",  # 日光
    "시부카와 마을",  # 渋川町
    "외딴집",  # 一軒家
    "시오바라 마을",  # 塩原村
    "미호 계곡",  # 美浦の渓谷
    "수호신산",  # 鎮守の山
    "시모츠마 마을",  # 下妻町
    "이시오카 산 입구",  # 石岡の山入り口
    "이시오카 동굴",  # 石岡の洞窟
    "니이자 마을",  # 新座村
    "모바라 숲",  # 茂原の森
    "아비코 숲",  # 我孫子の森
    "남쪽 늪",  # 南の沼
    "도쿄",  # 東京
    "마귀할멈 골짜기",  # 鬼婆の谷
    "대나무 숲",  # 竹林
    "가도",  # 街道
    "요코하마",  # 横浜
    "고개",  # 峠
    "시모니타 숲",  # 下仁田の林
    "하가쿠레산",  # 葉隠山
    "무로야마",  # 室山
    "선착장",  # 船着き場
    "스카이산",  # 皇海山
)


def records(mapcode):
    """[(record index, width cells, u, v)] for the 25 places; refuses an unexpected table."""
    if mapcode[TABLE:TABLE + 16] != bytes(16):
        raise ValueError("MAPCODE location table: record 0 is not empty")
    out = []
    for i in range(1, len(LABELS) + 1):
        p = TABLE + 16 * i
        n, u, v = mapcode[p + 5], mapcode[p + 6], mapcode[p + 7]
        ptr = struct.unpack_from("<I", mapcode, p + 12)[0]
        if not (POINTER[0] <= ptr < POINTER[1]) or n == 0 or v % 16:
            raise ValueError(f"MAPCODE location table: record {i} is not a place")
        out.append((i, n, u, v))
    return out


def label(text, font):
    """Outlined label: 16 rows, FILL text, EDGE outline, 0 transparent."""
    box = kfont.hangul_box(font)
    left = (kfont.CELL - box[0]) // 2
    cols = []
    for ch in text:
        if ch == " ":
            cols.append(np.zeros((kfont.CELL, SPACE), bool))
            continue
        cell = np.array(kfont.pixels(kfont.render(font[ch], box)), bool)
        cols += [cell[:, left:left + box[0]], np.zeros((kfont.CELL, GAP), bool)]
    text_px = np.pad(np.hstack(cols[:-1]), ((0, 0), (1, 1)))
    if text_px[0].any() or text_px[-1].any():
        raise ValueError(f"{text!r}: no room for the outline above or below")
    grown = text_px.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(text_px, dy, 0), dx, 1)
    return np.where(text_px, FILL, np.where(grown, EDGE, 0)).astype(np.uint8)


def pack(widths):
    """[(u, v, cells)] placing labels of the given pixel widths in the sheet, first fit, widest first."""
    free = [0] * (SHEET_H // 16)
    out = [None] * len(widths)
    for i in sorted(range(len(widths)), key=lambda i: -widths[i]):
        n = -(-widths[i] // 16)
        row = next((r for r, x in enumerate(free) if x + n * 16 <= SHEET_W), None)
        if row is None:
            raise ValueError(f"label {i} ({widths[i]} px) does not fit in the place-name sheet")
        out[i] = (free[row], row * 16, n)
        free[row] += n * 16
    return out


def sheet(amap):
    """The place-name sheet as a 256x128 array of colour numbers."""
    if struct.unpack_from("<I", amap, SHEET_AT - 4)[0] != SHEET_HEAD:
        raise ValueError("AMAPDAT: the place-name sheet header is not 128x256 4bpp")
    a = np.frombuffer(amap, np.uint8, SHEET_BYTES, SHEET_AT)
    return np.stack([a & 15, a >> 4], -1).reshape(SHEET_H, SHEET_W)


def apply(amap, mapcode, font):
    """(AMAPDAT, MAPCODE) with the Korean labels drawn and the table pointing at them."""
    records(mapcode)  # validate both inputs before writing
    sheet(amap)
    pics = [label(t, font) for t in LABELS]
    slots = pack([p.shape[1] for p in pics])
    px = np.zeros((SHEET_H, SHEET_W), np.uint8)
    new_map = bytearray(mapcode)
    for i, (p, (u, v, n)) in enumerate(zip(pics, slots), 1):
        px[v:v + 16, u:u + p.shape[1]] = p
        new_map[TABLE + 16 * i + 5:TABLE + 16 * i + 8] = bytes((n, u, v))
    packed = (px[:, 0::2] | (px[:, 1::2] << 4)).astype(np.uint8).tobytes()
    new_amap = amap[:SHEET_AT] + packed + amap[SHEET_AT + SHEET_BYTES:]
    return new_amap, bytes(new_map)
