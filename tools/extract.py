"""Extract source text rows from the original disc into text/src (untracked).

Usage: python3 tools/extract.py --src original/<image>.bin [--out text/src]
"""

import argparse
import json
from pathlib import Path

import build
import grparc
import iso
import script
import textio


def extract_all(src, out_dir):
    raw = Path(src).read_bytes()
    build.check_source(raw)
    disc = iso.load(raw)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for name in sorted(n for n in disc.files if n.startswith("ZROUP") and n.endswith(".GRP")):
        scene = name[:-4]
        grp = grparc.parse(iso.read_file(raw, disc, name))
        g = script.parse_group(grp.get(scene.replace("ZROUP", "GROUP") + ".BIN"))
        rows = textio.extract(scene, g)
        (out_dir / f"{scene}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        total += len(rows)
    return total


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default="text/src")
    a = ap.parse_args()
    print("rows", extract_all(a.src, a.out))
