"""LZ codec of the boot executable (SCPS_100.48) and the *.Z32 overlays.

Established 2026-10-09 from the boot code at 0x801E0028: the executable loads at
0x801E0000, unpacks the blob at file 0xA48 (RAM 0x801E0248) to 0x8000FFF8 and
jumps to the u32 at 0x8000FFFC. The unpacked main program (1,705,992 bytes)
matches a town RAM dump, item table at 0x8003A09C included. MAPCODE.Z32,
BTLCODE.Z32 and ROLL.Z32 use the same format from offset 0 and decode to their
exact file length.

Format: u32 output size, then 32-bit words that feed three streams, each word
fetched when its stream first runs dry: flag bits (MSB first), bytes (4 per
word, low byte first) and halfwords (2 per word, low half first).
  0 + byte                      literal
  1 0 + byte b + 2 bits v       match at -(256 - b), length v + 2; v = 3 adds ext to 5
  1 1 + half h                  match at (h & 0x1FFF) - 0x2000, length (h >> 13) + 3;
                                h >> 13 = 7 adds ext to 10
  ext: k one bits and a zero; k > 0 adds 1 + the next k bits.
The encoder writes the words in the order the decoder fetches them, so its output
decodes byte for byte (it does not reproduce the original packing, which it beats
by about 2%).
"""

import struct


def decode(src, pos):
    """Return (output bytes, end position in src)."""
    def word():
        nonlocal pos
        w = struct.unpack_from("<I", src, pos)[0]; pos += 4; return w
    n = word()
    out = bytearray()
    bits = nb = 0          # bit buffer value (32-bit, MSB first), bits left
    byt = nbyt = 0
    hw = nhw = 0
    def bit():
        nonlocal bits, nb
        if nb == 0:
            bits, nb = word(), 32
        nb -= 1
        b = bits >> 31; bits = (bits << 1) & 0xFFFFFFFF
        return b
    def getbits(k):
        v = 0
        for _ in range(k):
            v = v << 1 | bit()
        return v
    def byte():
        nonlocal byt, nbyt
        if nbyt == 0:
            byt, nbyt = word(), 4
        nbyt -= 1
        b = byt & 0xFF; byt >>= 8
        return b
    def half():
        nonlocal hw, nhw
        if nhw == 0:
            hw, nhw = word(), 2
        nhw -= 1
        h = hw & 0xFFFF; hw >>= 16
        return h
    while n > 0:
        if bit() == 0:
            out.append(byte()); n -= 1; continue
        if bit() == 0:
            off = byte() - 256
            v = getbits(2)
            ln = v + 2
            longlen = v == 3
        else:
            h = half()
            v = h >> 13
            off = (h & 0x1FFF) - 0x2000
            ln = v + 3
            longlen = v == 7
        if longlen:
            k = 0
            while bit():
                k += 1
            if k:
                ln += 1 + getbits(k)
        for _ in range(ln):
            out.append(out[off])
        n -= ln
    return bytes(out), pos


class _Writer:
    """Bit, byte and halfword streams interleaved in 32-bit words, each word placed
    where the decoder first needs it."""

    def __init__(self, n):
        self.words = [n]
        self.bw = self.nb = None   # index of current bit word, bits used
        self.yw = self.ny = None
        self.hw = self.nh = None

    def bit(self, b):
        if self.bw is None or self.nb == 32:
            self.words.append(0); self.bw, self.nb = len(self.words) - 1, 0
        self.words[self.bw] |= b << (31 - self.nb); self.nb += 1

    def bits(self, v, k):
        for i in range(k - 1, -1, -1):
            self.bit(v >> i & 1)

    def byte(self, b):
        if self.yw is None or self.ny == 4:
            self.words.append(0); self.yw, self.ny = len(self.words) - 1, 0
        self.words[self.yw] |= b << (8 * self.ny); self.ny += 1

    def half(self, h):
        if self.hw is None or self.nh == 2:
            self.words.append(0); self.hw, self.nh = len(self.words) - 1, 0
        self.words[self.hw] |= h << (16 * self.nh); self.nh += 1

    def ext(self, e):  # extra length after a base: k ones, a zero, then (e - 1) in k bits
        if e == 0:
            self.bit(0); return
        k = max(1, (e - 1).bit_length())
        self.bits((1 << k) - 1, k); self.bit(0); self.bits(e - 1, k)

    def data(self):
        return struct.pack(f"<{len(self.words)}I", *self.words)


def _ext_bits(e):
    return 1 if e == 0 else 2 * max(1, (e - 1).bit_length()) + 1


def _cost(off, ln):
    """Bits for a match, or None if it cannot be coded."""
    if off <= 256 and 2 <= ln <= 4:
        return 12
    best = None
    if off <= 256 and ln >= 5:
        best = 12 + _ext_bits(ln - 5)
    if off <= 8192 and ln >= 3:
        c = 18 if ln <= 9 else 18 + _ext_bits(ln - 10)
        best = c if best is None else min(best, c)
    return best


MAXLEN = 0x10000


def _match(d, i, heads, chain, depth=48):
    n = len(d)
    best_len, best_off = 0, 0
    if i + 2 > n:
        return 0, 0
    # offset 1 run (cheap check, common in zero fill)
    if i >= 1 and d[i] == d[i - 1]:
        ln = 1
        while i + ln < n and ln < MAXLEN and d[i + ln] == d[i - 1]:
            ln += 1
        best_len, best_off = ln, 1
    if i + 3 <= n:
        key = d[i:i + 3]
        j = heads.get(key, -1)
        cnt = 0
        while j >= 0 and i - j <= 8192 and cnt < depth:
            if d[j + best_len:j + best_len + 1] == d[i + best_len:i + best_len + 1] or best_len == 0:
                ln = 0
                while i + ln < n and ln < MAXLEN and d[j + ln] == d[i + ln]:
                    ln += 1
                if ln > best_len:
                    best_len, best_off = ln, i - j
            j = chain[j]
            cnt += 1
    # two-byte match within the short window
    if best_len < 2:
        for j in range(i - 1, max(-1, i - 257), -1):
            if d[j] == d[i] and d[j + 1] == d[i + 1]:
                return 2, i - j
    return best_len, best_off


def encode(d):
    d = bytes(d)
    n = len(d)
    w = _Writer(n)
    heads, chain = {}, [-1] * n

    def insert(p):
        if p + 3 <= n:
            k = d[p:p + 3]
            chain[p] = heads.get(k, -1)
            heads[k] = p

    def usable(off, ln):
        # shorten until codable; short matches are limited to 4 bytes unless extended
        while ln >= 2 and _cost(off, ln) is None:
            ln -= 1
        return ln

    i = 0
    while i < n:
        ln, off = _match(d, i, heads, chain)
        ln = usable(off, ln) if ln >= 2 else 0
        if ln >= 2:  # lazy: prefer a literal if the next position gives a clearly longer match
            insert(i)
            ln2, off2 = _match(d, i + 1, heads, chain) if i + 1 < n else (0, 0)
            ln2 = usable(off2, ln2) if ln2 >= 2 else 0
            if ln2 > ln + 1:
                w.bit(0); w.byte(d[i]); i += 1
                continue
            c = _cost(off, ln)
            if off <= 256 and 2 <= ln <= 4:
                w.bit(1); w.bit(0); w.byte(256 - off); w.bits(ln - 2, 2)
            elif off <= 256 and ln >= 5 and (off > 8192 or c == 12 + _ext_bits(ln - 5)):
                w.bit(1); w.bit(0); w.byte(256 - off); w.bits(3, 2); w.ext(ln - 5)
            else:
                code = min(ln - 3, 7)
                w.bit(1); w.bit(1); w.half(code << 13 | (0x2000 - off))
                if code == 7:
                    w.ext(ln - 10)
            for p in range(i + 1, i + ln):
                insert(p)
            i += ln
        else:
            insert(i)
            w.bit(0); w.byte(d[i]); i += 1
    return w.data()
