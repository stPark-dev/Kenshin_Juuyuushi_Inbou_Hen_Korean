"""Fast per-scene translation check (no image is written).

Usage: python3 tools/check_ko.py --src original/<image>.bin --galmuri ../galmuri/Galmuri14.bdf \
           [--ko-dir text/ko] ZROUP40 [ZROUP41 ...]

Runs the same encoding and scene build as tools/build.py and reports problems
per string id, plus translation coverage. Exit status 1 if any problem.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import build
import grparc
import iso
import koenc
import script
import textio


@dataclass
class Context:
    raw: bytes
    disc: object
    assets: object

    @classmethod
    def load(cls, src, galmuri):
        raw = Path(src).read_bytes()
        build.check_source(raw)
        disc = iso.load(raw)
        return cls(raw, disc, build.load_assets(raw, disc, galmuri))

    def group(self, scene):
        grp = grparc.parse(iso.read_file(self.raw, self.disc, scene + ".GRP"))
        return script.parse_group(grp.get(scene.replace("ZROUP", "GROUP") + ".BIN"))


def check_scene(ctx, scene, ko_path):
    g = ctx.group(scene)
    rows = textio.extract(scene, g)
    ko = json.loads(Path(ko_path).read_text(encoding="utf-8")) if Path(ko_path).is_file() else {}
    usable, problems = textio.usable_translations(rows, ko, textio.STATUSES)
    by_off = {r["offset"]: r for r in rows}
    hangul = {c for t in usable.values() for c in t if koenc.is_hangul(c)}
    code_of = koenc.assign_codes(hangul, set())
    entry_errors = []
    for off, text in sorted(usable.items()):
        try:
            koenc.encode(text, by_off[off]["src"].encode("cp932"), code_of)
        except (ValueError, KeyError) as e:
            entry_errors.append(f"{by_off[off]['id']}: {e}")
    problems += entry_errors
    report = {}
    if usable and not entry_errors:
        try:
            _, report = build.scene_build(g, usable, ctx.assets)
        except ValueError as e:
            problems.append(f"{scene}: {e}")
        else:
            if report["size"] > build.ORIGINAL_MAX_GROUP:
                problems.append(f"{scene}: size {report['size']} above verified maximum {build.ORIGINAL_MAX_GROUP}")
    return {"scene": scene, "total": len(rows), "translated": len(usable), "problems": problems, "build": report}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--galmuri", required=True)
    ap.add_argument("--ko-dir", default="text/ko")
    ap.add_argument("scenes", nargs="+")
    a = ap.parse_args(argv)
    ctx = Context.load(a.src, a.galmuri)
    bad = 0
    for scene in a.scenes:
        r = check_scene(ctx, scene, Path(a.ko_dir) / f"{scene}.json")
        print(f"{scene}: {r['translated']}/{r['total']} translated, {len(r['problems'])} problems {r['build']}")
        for p in r["problems"]:
            print("  PROBLEM", p)
        bad += bool(r["problems"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
