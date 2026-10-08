"""Product build: original disc image + text/ko translations -> patched image.

Usage:
  python3 tools/build.py --src original/<image>.bin --out build/kenshin_ko.bin \
      --galmuri ../galmuri/Galmuri14.bdf [--ko-dir text/ko] [--policy dev|release]

dev uses draft and reviewed translations and reports problems; release uses
only reviewed translations and fails on any problem. Every disc change goes
through iso.plan/iso.apply (expected-source checks and final diff audit).
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import grparc
import iso
import kfont
import koenc
import refs
import scenefont
import script
import textio

SOURCE_SHA256 = "738f320c105dc7ab63515553112bd78a62041305ee4f3ebfeaf5b7df8bb2abd8"
ORIGINAL_MAX_GROUP = 382396  # largest original GROUP (ZROUP24); larger sizes are not runtime-verified
POLICIES = {"dev": {"draft", "reviewed"}, "release": {"reviewed"}}


@dataclass(frozen=True)
class Assets:
    font: dict
    box: tuple
    namefont: dict


def check_source(raw):
    got = hashlib.sha256(raw).hexdigest()
    if got != SOURCE_SHA256:
        raise ValueError(f"source SHA-256 {got} does not match the supported image {SOURCE_SHA256}")


def load_assets(raw, disc, galmuri_path):
    sysgrp = grparc.parse(iso.read_file(raw, disc, "SYSTEM.GRP"))
    nf = scenefont.load_namefont(sysgrp.get("NAMEFONT.TXT"), sysgrp.get("NAMEFONT.BIN"))
    font = kfont.load_bdf(galmuri_path)
    return Assets(font=font, box=kfont.hangul_box(font), namefont=nf)


def scene_build(g, ko_map, assets):
    """Apply {offset: korean text} to a parsed GROUP; return (bytes, report)."""
    originals = {s.offset: s.raw for s in g.strings}
    slots = {s.offset: s.slot for s in g.strings}
    hangul = {c for t in ko_map.values() for c in t if koenc.is_hangul(c)}
    reserved = set()
    for s in g.strings:
        if s.offset not in ko_map:
            reserved |= {t.raw for t in script.tokenize(s.raw) if t.kind == "char"}
    for t in ko_map.values():
        reserved |= {c.encode("cp932") for c in t if ord(c) >= 0x80 and not koenc.is_hangul(c) and _sjis(c)}
    code_of = koenc.assign_codes(hangul, reserved)
    raws = {off: koenc.encode(text, originals[off], code_of) for off, text in ko_map.items()}
    missing = sorted(c for c in hangul if c not in assets.font)
    if missing:
        raise ValueError(f"Hangul font has no glyph for {''.join(missing)}")
    hglyphs = {code_of[c]: kfont.render(assets.font[c], assets.box) for c in hangul}
    # font covers the whole final pool: in-place text, old slots of moved strings
    # (left unchanged by refs.rebuild), then appended text
    moved = [o for o, r in sorted(raws.items()) if len(r) >= slots[o]]
    final = [raws[s.offset] if s.offset in raws and s.offset not in moved else s.raw for s in g.strings]
    final += [raws[o] for o in moved]
    codes, glyphs = scenefont.build(final, hglyphs, dict(zip(g.font_codes, g.font_glyphs)), assets.namefont)
    out = refs.rebuild(g, raws, codes, glyphs)
    report = {
        "translated": len(raws),
        "in_place": sum(1 for o, r in raws.items() if len(r) < slots[o]),
        "appended": sum(1 for o, r in raws.items() if len(r) >= slots[o]),
        "glyphs": len(codes),
        "size": len(out),
    }
    return out, report


def _sjis(c):
    try:
        return len(c.encode("cp932")) == 2
    except UnicodeEncodeError:
        return False


def build(src, ko_dir, out, statuses, assets=None, galmuri=None):
    raw = Path(src).read_bytes()
    check_source(raw)
    disc = iso.load(raw)
    if assets is None:
        assets = load_assets(raw, disc, galmuri)
    changes, problems, warnings, scenes = {}, [], [], {}
    for name in sorted(n for n in disc.files if n.startswith("ZROUP") and n.endswith(".GRP")):
        scene = name[:-4]
        grp = grparc.parse(iso.read_file(raw, disc, name))
        member = scene.replace("ZROUP", "GROUP") + ".BIN"
        g = script.parse_group(grp.get(member))
        rows = textio.extract(scene, g)
        kof = Path(ko_dir) / f"{scene}.json"
        ko = json.loads(kof.read_text(encoding="utf-8")) if kof.is_file() else {}
        ko_map, probs = textio.usable_translations(rows, ko, statuses)
        problems += probs
        if not ko_map:
            continue
        try:
            new, rep = scene_build(g, ko_map, assets)
        except ValueError as e:
            problems.append(f"{scene}: {e}")
            continue
        scenes[scene] = rep
        if rep["size"] > ORIGINAL_MAX_GROUP:
            warnings.append(f"{scene}: {member} is {rep['size']} bytes, above the verified maximum {ORIGINAL_MAX_GROUP}")
        changes[name] = grparc.build(grp.replace(member, new))
    image = iso.apply(raw, iso.plan(raw, disc, changes) if changes else [])
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image)
    out.with_suffix(".cue").write_text(f'FILE "{out.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    return {"problems": problems, "warnings": warnings, "scenes": scenes, "sha256": hashlib.sha256(image).hexdigest()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--galmuri", required=True)
    ap.add_argument("--ko-dir", default="text/ko")
    ap.add_argument("--policy", choices=sorted(POLICIES), default="dev")
    a = ap.parse_args(argv)
    rep = build(a.src, a.ko_dir, a.out, POLICIES[a.policy], galmuri=a.galmuri)
    for p in rep["problems"]:
        print("PROBLEM", p)
    for w in rep["warnings"]:
        print("WARNING", w)
    for s, r in rep["scenes"].items():
        print(s, r)
    print("output sha256", rep["sha256"])
    if a.policy == "release" and rep["problems"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
