"""CD-ROM Mode 2 Form 1 raw sector (2352 bytes) assembly with EDC/ECC.

Layout: sync(12) header(4: BCD MSF + mode) subheader(8, two copies)
        user data(2048) EDC(4, LE) ECC P(172) ECC Q(104)
EDC covers subheader+data (0x10..0x818). ECC covers 0x0C..0x818 with the
header treated as zero, as Mode 2 requires. Batch functions operate on
(N, 2352) uint8 arrays so the whole disc can be regenerated quickly.
"""

import numpy as np

RAW = 2352
SYNC = bytes([0x00] + [0xFF] * 10 + [0x00])
EDC_POS, P_POS, Q_POS = 0x818, 0x81C, 0x8C8


def _tables():
    f = np.zeros(256, np.uint8)
    b = np.zeros(256, np.uint8)
    edc = np.zeros(256, np.uint32)
    for i in range(256):
        j = ((i << 1) ^ (0x11D if i & 0x80 else 0)) & 0xFF
        f[i] = j
        b[i ^ j] = i
        e = i
        for _ in range(8):
            e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
        edc[i] = e
    return f, b, edc


ECC_F, ECC_B, EDC_TABLE = _tables()


def _ecc_index(major_count, minor_count, major_mult, minor_inc):
    size = major_count * minor_count
    idx = np.zeros((major_count, minor_count), np.int64)
    for major in range(major_count):
        k = (major >> 1) * major_mult + (major & 1)
        for minor in range(minor_count):
            idx[major, minor] = k
            k += minor_inc
            if k >= size:
                k -= size
    return idx


P_INDEX = _ecc_index(86, 24, 2, 86)
Q_INDEX = _ecc_index(52, 43, 86, 88)


def _bcd(v):
    return (v // 10) << 4 | v % 10


def header(lba):
    a = lba + 150
    return bytes([_bcd(a // 4500), _bcd(a // 75 % 60), _bcd(a % 75), 2])


def is_form1(raw):
    if len(raw) < 24 or raw[:12] != SYNC or raw[15] != 2:
        return False
    sub = raw[16:24]
    return sub[:4] == sub[4:] and not sub[2] & 0x20


def _ecc_block(src, index, dest_off, out):
    a = np.zeros((src.shape[0], index.shape[0]), np.uint8)
    b = np.zeros_like(a)
    for minor in range(index.shape[1]):
        t = src[:, index[:, minor]]
        a ^= t
        b ^= t
        a = ECC_F[a]
    a = ECC_B[ECC_F[a] ^ b]
    n = index.shape[0]
    out[:, dest_off : dest_off + n] = a
    out[:, dest_off + n : dest_off + 2 * n] = a ^ b


def complete_form1(sectors):
    """Return a copy of (N, 2352) sectors with EDC and ECC filled in."""
    s = np.array(sectors, dtype=np.uint8, copy=True)
    if s.ndim != 2 or s.shape[1] != RAW:
        raise ValueError("expected an (N, 2352) array")
    edc = np.zeros(s.shape[0], np.uint32)
    for col in range(0x10, EDC_POS):
        edc = (edc >> 8) ^ EDC_TABLE[(edc ^ s[:, col]) & 0xFF]
    s[:, EDC_POS : EDC_POS + 4] = edc[:, None].view(np.uint8).reshape(-1, 4)
    hdr = s[:, 12:16].copy()
    s[:, 12:16] = 0
    _ecc_block(s[:, 12:], P_INDEX, P_POS, s)
    _ecc_block(s[:, 12:], Q_INDEX, Q_POS, s)
    s[:, 12:16] = hdr
    return s


def build_form1(lba, subheader, data):
    if len(subheader) != 8 or len(data) != 2048:
        raise ValueError("Form 1 needs an 8-byte subheader and 2048 data bytes")
    raw = bytearray(RAW)
    raw[:12] = SYNC
    raw[12:16] = header(lba)
    raw[16:24] = subheader
    raw[24:EDC_POS] = data
    return complete_form1(np.frombuffer(bytes(raw), np.uint8).reshape(1, RAW))[0].tobytes()
