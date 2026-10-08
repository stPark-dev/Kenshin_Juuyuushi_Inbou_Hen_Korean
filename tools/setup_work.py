"""Regenerate the untracked analysis folder from the original disc.

Usage: python3 tools/setup_work.py --src original/<image>.bin [--out work]

Writes work/iso/<FILE> for every Form 1 data file (MOV/XAD are Form 2 and
skipped) and work/grp/<GRP name>/<member> for every GRP archive. The corpus
tests and the reverse-engineering scripts in tools/re read these.
"""

import argparse
from pathlib import Path

import build
import grparc
import iso


def setup(src, out):
    raw = Path(src).read_bytes()
    build.check_source(raw)
    disc = iso.load(raw)
    out = Path(out)
    (out / "iso").mkdir(parents=True, exist_ok=True)
    for name in sorted(disc.files):
        if name.endswith((".MOV", ".XAD")):
            continue
        data = iso.read_file(raw, disc, name)
        (out / "iso" / name).write_bytes(data)
        if name.endswith(".GRP"):
            gdir = out / "grp" / name[:-4]
            gdir.mkdir(parents=True, exist_ok=True)
            for e in grparc.parse(data).entries:  # duplicate names hold identical bytes
                (gdir / e.name).write_bytes(e.data)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default="work")
    a = ap.parse_args()
    setup(a.src, a.out)
    print("done")
