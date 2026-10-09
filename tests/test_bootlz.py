import glob
import os
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import bootlz  # noqa: E402
import iso  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)


@pytest.mark.parametrize("data", [
    b"",
    b"A",
    bytes(5000),
    b"abcabcabcabcabcabcabcabc" * 40,
    bytes(random.Random(1).randrange(256) for _ in range(3000)),
    bytes(random.Random(2).choice(b"\x00\x01ab") for _ in range(20000)),
    b"xyz" + bytes(300) + b"xyz" * 3000 + bytes(range(256)) * 50,
], ids=["empty", "one", "zeros", "repeat", "random", "small-alphabet", "mixed"])
def test_roundtrip(data):
    packed = bootlz.encode(data)
    out, end = bootlz.decode(packed, 0)
    assert out == data and end == len(packed)


def test_far_and_short_matches_both_used():
    rng = random.Random(3)
    block = bytes(rng.randrange(256) for _ in range(600))
    data = block + bytes(rng.randrange(256) for _ in range(5000)) + block + block[:3] * 50
    packed = bootlz.encode(data)
    assert bootlz.decode(packed, 0)[0] == data
    assert len(packed) < len(data)


@pytest.mark.skipif(not BIN, reason="disc image not available")
def test_boot_executable_repacks_smaller():
    raw = Path(BIN).read_bytes()
    disc = iso.load(raw)
    exe = iso.read_file(raw, disc, next(n for n in disc.files if n.startswith("SCPS")))
    main, end = bootlz.decode(exe, 0xA48)
    assert len(main) == 1705992 and not any(exe[end:])
    packed = bootlz.encode(main)
    assert bootlz.decode(packed, 0)[0] == main
    assert len(packed) <= end - 0xA48
