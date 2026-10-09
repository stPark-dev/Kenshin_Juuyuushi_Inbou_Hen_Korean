import glob
import json
import os
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import bootlz  # noqa: E402
import grparc  # noqa: E402
import iso  # noqa: E402
import ovltext  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)
pytestmark = pytest.mark.skipif(not BIN, reason="disc image not available")


@pytest.fixture(scope="module")
def overlays():
    raw = Path(BIN).read_bytes()
    grp = grparc.parse(iso.read_file(raw, iso.load(raw), "SYSTEM.GRP"))
    return {n: bootlz.decode(grp.get(f"{n}.Z32"), 0)[0] for n in ("MAPCODE", "BTLCODE")}


def _deref(data, site):
    p = struct.unpack_from("<I", data, site - ovltext.BASE)[0] - ovltext.BASE
    return data[p:data.index(b"\0", p)]


@pytest.mark.parametrize("name", ["MAPCODE", "BTLCODE"])
def test_repack_keeps_every_reference(overlays, name):
    data = overlays[name]
    mov = ovltext.movable(name, data)
    a0 = mov[0][0]
    new = b"\x88\x9f"  # changed and shorter: BTLCODE has no spare bytes
    out = ovltext.apply(name, data, {f"{name}:{a0:x}": new})
    for a, raw, sites in mov:
        for s in sites:
            assert _deref(out, s) == (new if a == a0 else raw)


def test_fixed_slots(overlays):
    data = overlays["BTLCODE"]
    a, raw, slot = ovltext.fixed("BTLCODE", data)[2]
    out = ovltext.apply("BTLCODE", data, {f"BTLCODE:{a:x}": b"\x88\x9f\x88\xa0"})
    assert out[a - ovltext.BASE:a - ovltext.BASE + slot] == b"\x88\x9f\x88\xa0" + b"\x81\x40" * 4
    with pytest.raises(ValueError):
        ovltext.apply("BTLCODE", data, {f"BTLCODE:{a:x}": b"\x88\x9f" * 7})


def test_mapcode_font_roundtrip(overlays):
    data = overlays["MAPCODE"]
    font = ovltext.mapcode_font(data)
    assert len(font) == 400
    small = dict(list(font.items())[:10])
    assert ovltext.mapcode_font(ovltext.set_mapcode_font(data, font)) == font
    out = ovltext.set_mapcode_font(data, small)
    lst = out[ovltext.MAPCODE_FONT_LIST - ovltext.BASE:]
    assert lst[:20] == b"".join(small) and lst[20:22] == b"\0\0"


@pytest.mark.parametrize("name", ["MAPCODE", "BTLCODE"])
def test_translation_files_are_current(overlays, name):
    rows = {r["id"]: r for r in ovltext.extract(name, overlays[name])}
    ko = json.loads((ROOT / "text" / "ko" / f"{name}.json").read_text(encoding="utf-8"))
    for sid, e in ko.items():
        assert e["src_hash"] == rows[sid]["hash"], sid
        assert len(e["ko"]) <= rows[sid]["limit"], sid
