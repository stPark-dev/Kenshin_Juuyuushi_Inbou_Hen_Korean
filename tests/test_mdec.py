import glob
import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import iso  # noqa: E402
import mdec  # noqa: E402
import movie  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)


def _picture():
    y, x = np.mgrid[0:48, 0:64]
    rgb = np.stack([x * 4, y * 5, (x + y) * 2], -1)
    rgb[10:30, 20:40] = (250, 250, 250)
    return rgb.astype(np.uint8)


def test_encode_decode_round_trip():
    rgb = _picture()
    data = mdec.encode(rgb, 1)
    assert data[2:4] == b"\x00\x38" and data[6:8] == b"\x03\x00"
    back = mdec.decode(64, 48, data)
    assert np.abs(back.astype(int) - rgb).mean() < 3


def test_code_count_and_end_code():
    data = mdec.encode(_picture(), 2)
    blocks, bits = mdec.decode_blocks(64, 48, data)
    assert len(blocks) == 12 * 6
    stream = mdec.Bits(data[8:]).s
    assert stream[bits:bits + 10] == mdec.END
    assert int.from_bytes(data[:2], "little") % 32 == 0


def test_fit_raises_qscale():
    rgb = (np.random.default_rng(1).random((48, 64, 3)) * 255).astype(np.uint8)
    big = len(mdec.encode(rgb, 1))
    data, q = mdec.fit(rgb, big // 2)
    assert q > 1 and len(data) <= big // 2


def test_dialogue_rows_scroll_the_speaker_out():
    assert movie._rows("켄신", ["가나", "다라", "마"], 2) == [(17, 172, "켄신"), (33, 188, "가나")]
    assert movie._rows("켄신", ["가나", "다라", "마"], 5) == [(33, 172, "가나"), (33, 188, "다라"), (33, 203, "마")]


@pytest.mark.skipif(not BIN, reason="disc image not available")
def test_source_frames_round_trip():
    raw = Path(BIN).read_bytes()
    rec = iso.load(raw).files["RU12.MOV"]
    w, h, data = mdec.frames(raw, rec)[30]
    rgb = mdec.decode(w, h, data)
    q = int.from_bytes(data[4:6], "little")
    again = mdec.decode(w, h, mdec.encode(rgb, q))
    assert np.abs(again.astype(int) - rgb).mean() < 2
    users = mdec.chunk_sectors(raw, rec, 30, mdec.encode(rgb, q))
    assert all(len(u) == 2048 and u[:4] == mdec.MAGIC for u in users.values())


def test_speakerless_rows_scroll():
    layout = movie.RU13_LAYOUT
    rows = movie._rows("", ["가", "나", "다", "라"], 4, layout)
    assert [t for _, _, t in rows] == ["나", "다", "라"] and rows[0][:2] == (24, 171)
