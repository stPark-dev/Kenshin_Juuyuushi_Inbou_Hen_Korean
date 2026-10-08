"""Reinterpret a DuckStation vram-write dump (16bpp) as 4bpp indices -> grayscale PNG."""
import sys
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGBA")
w, h = im.size
px = im.load()
out = Image.new("L", (w * 4, h))
o = out.load()
for y in range(h):
    for x in range(w):
        r, g, b, a = px[x, y]
        v = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10) | ((1 if a >= 128 else 0) << 15)
        for k in range(4):
            o[x * 4 + k, y] = ((v >> (4 * k)) & 15) * 17
out.save(dst)
