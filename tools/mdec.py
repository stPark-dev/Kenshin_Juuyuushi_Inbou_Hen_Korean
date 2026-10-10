"""PlayStation STR movies (RU*.MOV): MDEC frame decoding and encoding.

Established 2026-10-10 (docs/survey.md §3.1.10):
- Video sectors are mode 2 form 1 with a 32-byte STR header: u16 0x0160,
  u16 0x8001, u16 chunk, u16 chunks, u32 frame (from 1), u32 frame bytes
  (header + bitstream, rounded up to 4), u16 width, u16 height, then a copy of
  the frame header and zeros; 2016 bytes of frame data follow. Audio sectors
  (form 2) sit between them. The movie table (main program 0x8003C554) starts
  a movie at frame * 10 sectors, so a frame's sectors and chunk count stay put.
- Frame data: u16 code count (MDEC codes / 2, rounded up to 32), u16 0x3800,
  u16 qscale, u16 version (3 on this disc), then the bitstream (u16 LE words,
  MSB first) and the end code 1111111111, zero padded.
- Macroblocks column by column, blocks Cr Cb Y1 Y2 Y3 Y4. v3 DC: MPEG-1 size
  code (luma / chroma table) + difference, times 4, predicted per component;
  AC: MPEG-1 table B.14, escape 000001 + 6-bit run + 10-bit level, end of
  block 10. Dequantisation: DC x qt[0], AC x qt x qscale / 8 (MPEG-1 default
  intra matrix).
"""

import numpy as np

ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21,
          28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61,
          54, 47, 55, 62, 63]
QTABLE = [2, 16, 19, 22, 26, 27, 29, 34, 16, 16, 22, 24, 27, 29, 34, 37, 19, 22, 26, 27, 29, 34, 34, 38, 22, 22, 26, 27,
          29, 34, 37, 40, 22, 26, 27, 29, 32, 35, 40, 48, 26, 27, 29, 32, 35, 40, 48, 58, 26, 27, 29, 34, 38, 46, 56, 69,
          27, 29, 35, 38, 46, 56, 69, 83]  # natural order
AC = """11 0 1|011 1 1|0100 0 2|0101 2 1|00101 0 3|00111 3 1|00110 4 1|000110 1 2|000111 5 1|000101 6 1|000100 7 1
0000110 0 4|0000100 2 2|0000111 8 1|0000101 9 1|00100110 0 5|00100001 0 6|00100101 1 3|00100100 3 2|00100111 10 1
00100011 11 1|00100010 12 1|00100000 13 1|0000001010 0 7|0000001100 1 4|0000001011 2 3|0000001111 4 2
0000001001 5 2|0000001110 14 1|0000001101 15 1|0000001000 16 1|000000011101 0 8|000000011000 0 9|000000010011 0 10
000000010000 0 11|000000011011 1 5|000000010100 2 4|000000011100 3 3|000000010010 4 3|000000011110 6 2
000000010101 7 2|000000010001 8 2|000000011111 17 1|000000011010 18 1|000000011001 19 1|000000010111 20 1
000000010110 21 1|0000000011010 0 12|0000000011001 0 13|0000000011000 0 14|0000000010111 0 15|0000000010110 1 6
0000000010101 1 7|0000000010100 2 5|0000000010011 3 4|0000000010010 5 3|0000000010001 9 2|0000000010000 10 2
0000000011111 22 1|0000000011110 23 1|0000000011101 24 1|0000000011100 25 1|0000000011011 26 1
00000000011111 0 16|00000000011110 0 17|00000000011101 0 18|00000000011100 0 19|00000000011011 0 20
00000000011010 0 21|00000000011001 0 22|00000000011000 0 23|00000000010111 0 24|00000000010110 0 25
00000000010101 0 26|00000000010100 0 27|00000000010011 0 28|00000000010010 0 29|00000000010001 0 30
00000000010000 0 31|000000000011000 0 32|000000000010111 0 33|000000000010110 0 34|000000000010101 0 35
000000000010100 0 36|000000000010011 0 37|000000000010010 0 38|000000000010001 0 39|000000000010000 0 40
000000000011111 1 8|000000000011110 1 9|000000000011101 1 10|000000000011100 1 11|000000000011011 1 12
000000000011010 1 13|000000000011001 1 14|0000000000010011 1 15|0000000000010010 1 16|0000000000010001 1 17
0000000000010000 1 18|0000000000010100 6 3|0000000000011010 11 2|0000000000011001 12 2|0000000000011000 13 2
0000000000010111 14 2|0000000000010110 15 2|0000000000010101 16 2|0000000000011111 27 1|0000000000011110 28 1
0000000000011101 29 1|0000000000011100 30 1|0000000000011011 31 1"""
AC_CODES = {}
for _item in AC.replace("\n", "|").split("|"):
    _code, _run, _level = _item.split()
    AC_CODES[_code] = (int(_run), int(_level))
AC_OF = {v: k for k, v in AC_CODES.items()}
DC_LUMA = {"100": 0, "00": 1, "01": 2, "101": 3, "110": 4, "1110": 5, "11110": 6, "111110": 7, "1111110": 8}
DC_CHROMA = {"00": 0, "01": 1, "10": 2, "110": 3, "1110": 4, "11110": 5, "111110": 6, "1111110": 7, "11111110": 8}
DCL_OF = {v: k for k, v in DC_LUMA.items()}
DCC_OF = {v: k for k, v in DC_CHROMA.items()}
END = "1111111111"
EOB, ESCAPE = "10", "000001"
MAGIC = b"\x60\x01\x01\x80"
CHUNK = 2016
KINDS = ("cr", "cb", "y", "y", "y", "y")


def _table(codes):
    return {(len(c), int(c, 2)): r for c, r in codes.items()}


AC_T, DCL_T, DCC_T = _table(AC_CODES), _table(DC_LUMA), _table(DC_CHROMA)
M = np.array([[(np.sqrt(0.125) if u == 0 else 0.5) * np.cos((2 * x + 1) * u * np.pi / 16) for u in range(8)]
              for x in range(8)])  # pixels = M @ coef @ M.T
QT = np.array(QTABLE, dtype=float)


class Bits:
    def __init__(self, data):
        words = np.frombuffer(data[: len(data) // 2 * 2], dtype="<u2")
        self.s = "".join(f"{w:016b}" for w in words)
        self.p = 0

    def get(self, n):
        v = int(self.s[self.p:self.p + n], 2) if n else 0
        self.p += n
        return v

    def lookup(self, table, maxlen):
        for n in range(1, maxlen + 1):
            r = table.get((n, int(self.s[self.p:self.p + n], 2)))
            if r is not None:
                self.p += n
                return r
        raise ValueError(f"bad code at bit {self.p}")


def sectors(raw, rec):
    """[(lba, frame, chunk, chunks, user data)] of a movie's video sectors."""
    out = []
    for lba in range(rec.lba, rec.lba + rec.size // 2048):
        sec = raw[lba * 2352:(lba + 1) * 2352]
        u = sec[24:24 + 2048]
        if sec[18] & 0x20 or u[:4] != MAGIC:
            continue
        out.append((lba, int.from_bytes(u[8:12], "little"), int.from_bytes(u[4:6], "little"),
                    int.from_bytes(u[6:8], "little"), u))
    return out


def frames(raw, rec):
    """{frame: (width, height, frame data)}."""
    acc = {}
    for _, f, chunk, _, u in sectors(raw, rec):
        w, h = int.from_bytes(u[16:18], "little"), int.from_bytes(u[18:20], "little")
        acc.setdefault(f, (w, h, {}))[2][chunk] = u[32:]
    return {f: (w, h, b"".join(c[k] for k in sorted(c))) for f, (w, h, c) in acc.items()}


def _sign(v, n):
    return v - (1 << n) if v >> (n - 1) else v


def decode_blocks(w, h, data):
    """Dequantised coefficients [(kind, mx, my, 8x8)] and the bit length used."""
    q, ver = int.from_bytes(data[4:6], "little"), int.from_bytes(data[6:8], "little")
    if ver != 3:
        raise ValueError(f"bitstream version {ver}, only 3 is handled")
    b = Bits(data[8:])
    prev = {"y": 0, "cb": 0, "cr": 0}
    out = []
    for mx in range((w + 15) // 16):
        for my in range((h + 15) // 16):
            for kind in KINDS:
                coef = np.zeros(64)
                size = b.lookup(DCL_T if kind == "y" else DCC_T, 8)
                diff = 0
                if size:
                    v = b.get(size)
                    diff = v if v >> (size - 1) else v - (1 << size) + 1
                prev[kind] += diff * 4
                coef[0] = prev[kind] * QT[0]
                i = 0
                while True:
                    if b.s[b.p:b.p + 2] == EOB:
                        b.p += 2
                        break
                    if b.s[b.p:b.p + 6] == ESCAPE:
                        b.p += 6
                        run, level = b.get(6), _sign(b.get(10), 10)
                    else:
                        run, level = b.lookup(AC_T, 16)
                        if b.get(1):
                            level = -level
                    i += run + 1
                    if i > 63:
                        raise ValueError("coefficient index past 63")
                    z = ZIGZAG[i]
                    coef[z] = level * QT[z] * q / 8
                out.append((kind, mx, my, coef.reshape(8, 8)))
    return out, b.p


def decode(w, h, data):
    """RGB uint8 array (h, w, 3) of a frame."""
    mbw, mbh = (w + 15) // 16, (h + 15) // 16
    planes = {"y": np.zeros((mbh * 16, mbw * 16)), "cb": np.zeros((mbh * 8, mbw * 8)), "cr": np.zeros((mbh * 8, mbw * 8))}
    blocks, _ = decode_blocks(w, h, data)
    for n, (kind, mx, my, coef) in enumerate(blocks):
        blk = M @ coef @ M.T
        if kind == "y":
            j = n % 6 - 2
            y0, x0 = my * 16 + (j // 2) * 8, mx * 16 + (j % 2) * 8
        else:
            y0, x0 = my * 8, mx * 8
        planes[kind][y0:y0 + 8, x0:x0 + 8] = blk
    return to_rgb(planes)[:h, :w]


def to_rgb(planes):
    y = planes["y"]
    cb = planes["cb"].repeat(2, 0).repeat(2, 1)
    cr = planes["cr"].repeat(2, 0).repeat(2, 1)
    rgb = np.stack([y + 1.402 * cr, y - 0.3437 * cb - 0.7143 * cr, y + 1.772 * cb], -1) + 128
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def from_rgb(rgb):
    p = rgb.astype(float) - 128
    r, g, b = p[..., 0], p[..., 1], p[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb, cr = (b - y) / 1.772, (r - y) / 1.402
    h, w = y.shape

    def half(c):
        return c.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))

    return {"y": y, "cb": half(cb), "cr": half(cr)}


def _bits(v, n):
    return format(v & ((1 << n) - 1), f"0{n}b") if n else ""


def encode(rgb, q):
    """Frame data (header + bitstream) of an RGB frame at qscale q."""
    h, w = rgb.shape[:2]
    if w % 16 or h % 16:
        raise ValueError(f"{w}x{h} is not a whole number of macroblocks")
    planes = from_rgb(rgb)
    out, codes = [], 0
    prev = {"y": 0, "cb": 0, "cr": 0}
    acq = QT * q / 8
    for mx in range(w // 16):
        for my in range(h // 16):
            for n, kind in enumerate(KINDS):
                if kind == "y":
                    y0, x0 = my * 16 + ((n - 2) // 2) * 8, mx * 16 + ((n - 2) % 2) * 8
                else:
                    y0, x0 = my * 8, mx * 8
                coef = (M.T @ planes[kind][y0:y0 + 8, x0:x0 + 8] @ M).reshape(64)
                dc = int(np.clip(round(coef[0] / QT[0] / 4) * 4, -512, 508))
                diff = (dc - prev[kind]) // 4
                prev[kind] = dc
                size = abs(diff).bit_length()
                out.append((DCL_OF if kind == "y" else DCC_OF)[size])
                out.append(_bits(diff if diff >= 0 else diff + (1 << size) - 1, size))
                levels = np.clip(np.rint(coef / acq), -512, 511).astype(int)
                run = 0
                for i in range(1, 64):
                    lv = levels[ZIGZAG[i]]
                    if lv == 0:
                        run += 1
                        continue
                    code = AC_OF.get((run, abs(lv)))
                    out.append(code + ("1" if lv < 0 else "0") if code else ESCAPE + _bits(run, 6) + _bits(lv, 10))
                    run = 0
                    codes += 1
                out.append(EOB)
                codes += 2
    bits = "".join(out) + END
    bits += "0" * (-len(bits) % 16)
    body = np.array([int(bits[i:i + 16], 2) for i in range(0, len(bits), 16)], dtype="<u2").tobytes()
    count = -(-((codes + 1) // 2) // 32) * 32
    head = count.to_bytes(2, "little") + b"\x00\x38" + q.to_bytes(2, "little") + (3).to_bytes(2, "little")
    return head + body


def fit(rgb, room, q=1):
    """(frame data, q) at the lowest qscale from `q` up that fits `room` bytes."""
    while q < 64:
        data = encode(rgb, q)
        if len(data) <= room:
            return data, q
        q += 1
    raise ValueError("frame does not fit even at qscale 63")


def chunk_sectors(raw, rec, frame, data):
    """{lba: new user data} placing frame data in the frame's own video sectors."""
    secs = [s for s in sectors(raw, rec) if s[1] == frame]
    room = len(secs) * CHUNK
    if len(data) > room:
        raise ValueError(f"frame {frame}: {len(data)} bytes, room {room}")
    padded = data + bytes(room - len(data))
    size = -(-len(data) // 4) * 4
    out = {}
    for lba, _, chunk, _, u in secs:
        head = bytearray(u[:32])
        head[12:16] = size.to_bytes(4, "little")
        head[20:28] = data[:8]
        out[lba] = bytes(head) + padded[chunk * CHUNK:(chunk + 1) * CHUNK]
    return out
