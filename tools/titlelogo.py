"""Title logo: TITLE.BIN entry 0 replaced by the Korean logo (title_ko.png).

Entry 0 (docs/survey.md §3.1.8) is a plain 8bpp picture: u32 type, u16 w, u16 h,
a 256-colour CLUT (colour 0 = 0x0000 is see-through), then 128-wide tiles of
u16 x, y, w, h + pixels. The source logo fills (10, 5)-(307, 155) of its 320x161
canvas; the Korean logo's opaque part is scaled into the same box (both are about
1.98:1), alpha cut at 128, and the opaque pixels reduced to 255 colours. Opaque
black is stored as 0x8000 so that it does not turn see-through.
"""

import struct

from PIL import Image

ENTRY = 0
BOX = (10, 5, 307, 155)  # opaque extent of the source logo
ALPHA_CUT = 128


def _entry(title):
    offs = struct.unpack_from("<8I", title)
    bounds = sorted(offs) + [len(title)]
    at = offs[ENTRY]
    return at, bounds[bounds.index(at) + 1]


def _rgb15(r, g, b):
    v = (r >> 3) | (g >> 3) << 5 | (b >> 3) << 10
    return v or 0x8000


def picture(png, w, h):
    """(CLUT halfwords x256, w*h indices) of the logo on a w x h canvas."""
    im = Image.open(png).convert("RGBA")
    im = im.crop(im.getchannel("A").point(lambda v: 255 if v >= ALPHA_CUT else 0).getbbox())
    bw, bh = BOX[2] - BOX[0], BOX[3] - BOX[1]
    s = min(bw / im.width, bh / im.height)
    size = (round(im.width * s), round(im.height * s))
    im = im.resize(size, Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h))
    canvas.paste(im, (BOX[0] + (bw - size[0]) // 2, BOX[1] + (bh - size[1]) // 2))
    alpha = canvas.getchannel("A")
    # 5-bit colour first, so the reduction works on what the GPU can show
    rgb = canvas.convert("RGB").point(lambda v: v & 0xF8)
    pal_im = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = pal_im.getpalette()[:255 * 3]
    clut = [0] + [_rgb15(*pal[3 * i:3 * i + 3]) for i in range(len(pal) // 3)]
    clut += [0x8000] * (256 - len(clut))
    idx = bytes(0 if a < ALPHA_CUT else p + 1 for p, a in zip(pal_im.getdata(), alpha.getdata()))
    return clut, idx


def apply(title, png):
    """TITLE.BIN with entry 0 redrawn from `png`, same size and tiling."""
    at, end = _entry(title)
    _, w, h = struct.unpack_from("<IHH", title, at)
    clut, idx = picture(png, w, h)
    d = bytearray(title)
    struct.pack_into("<256H", d, at + 8, *clut)
    p = at + 8 + 512
    while p < end:
        x, y, tw, th = struct.unpack_from("<4H", d, p)
        p += 8
        for r in range(th):
            d[p + r * tw:p + (r + 1) * tw] = idx[(y + r) * w + x:(y + r) * w + x + tw]
        p += tw * th
    if p != end:
        raise ValueError(f"logo tiles end at 0x{p:x}, entry ends at 0x{end:x}")
    return bytes(d)
