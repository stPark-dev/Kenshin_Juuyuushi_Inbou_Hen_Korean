"""Dump STR movie frames as PNG for surveying (tools/mdec.py does the decoding).

usage: strdec.py IMAGE.bin RU12.MOV OUT_DIR [--every N] [--first F] [--last L]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import iso  # noqa: E402
import mdec  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("image")
ap.add_argument("movie")
ap.add_argument("out")
ap.add_argument("--every", type=int, default=15)
ap.add_argument("--first", type=int, default=1)
ap.add_argument("--last", type=int, default=1 << 30)
a = ap.parse_args()
raw = Path(a.image).read_bytes()
fr = mdec.frames(raw, iso.load(raw).files[a.movie])
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
print(a.movie, "frames", len(fr), flush=True)
for f in sorted(fr):
    if a.first <= f <= a.last and (f - a.first) % a.every == 0:
        w, h, data = fr[f]
        Image.fromarray(mdec.decode(w, h, data)).save(out / f"{f:05d}.png")
