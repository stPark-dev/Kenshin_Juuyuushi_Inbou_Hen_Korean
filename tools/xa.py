"""CD-XA ADPCM audio (the sound interleaved in the RU*.MOV movies).

An audio sector is mode 2 form 2: subheader (file, channel, submode, coding) at
byte 16 of the raw sector, 18 sound groups of 128 bytes from byte 24. Coding
bit 0 = stereo, bit 2 = 18.9 kHz (else 37.8 kHz), bit 4 = 8-bit (else 4-bit).
A 4-bit group: 16 header bytes (shift/filter per sound unit), then 28 words of
4 bytes; unit u takes nibble u of each word; stereo alternates units L, R.
"""

import numpy as np

K0 = (0, 60, 115, 98)
K1 = (0, 0, -52, -55)


def is_audio(sector):
    return bool(sector[18] & 0x04)


def rate(coding):
    return 18900 if coding & 0x04 else 37800


def decode(sectors):
    """(samples int16 [n, channels], rate) of raw 2352-byte audio sectors, in order."""
    coding = sectors[0][19]
    stereo = coding & 1
    if coding & 0x10:
        raise ValueError("8-bit XA is not handled")
    hist = [[0, 0], [0, 0]]
    out = [[], []]
    for s in sectors:
        for g in range(18):
            grp = s[24 + 128 * g:24 + 128 * (g + 1)]
            for u in range(8):
                hdr = grp[4 + u]
                shift, filt = hdr & 0x0F, (hdr >> 4) & 0x03
                ch = u & 1 if stereo else 0
                h = hist[ch]
                for i in range(28):
                    nib = (grp[16 + 4 * i + u // 2] >> (4 * (u & 1))) & 0x0F
                    v = (nib - 16 if nib & 8 else nib) << 12
                    v = (v >> shift) + ((h[0] * K0[filt] + h[1] * K1[filt] + 32) >> 6)
                    v = max(-32768, min(32767, v))
                    h[1], h[0] = h[0], v
                    out[ch].append(v)
    chans = 2 if stereo else 1
    return np.array(out[:chans], np.int16).T, rate(coding)
