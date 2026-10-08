import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import cdsector  # noqa: E402

RAW = 2352


def test_lba_to_header_bcd_msf():
    # LBA 0 is 00:02:00, mode 2
    assert cdsector.header(0) == bytes([0x00, 0x02, 0x00, 0x02])
    assert cdsector.header(227405) == bytes([0x50, 0x34, 0x05, 0x02])


def test_zero_payload_has_zero_edc_ecc():
    sec = cdsector.build_form1(16, bytes(8), bytes(2048))
    assert len(sec) == RAW
    assert sec[:12] == cdsector.SYNC
    assert sec[0x818:] == bytes(RAW - 0x818)


def test_form1_requires_2048_bytes():
    with pytest.raises(ValueError):
        cdsector.build_form1(16, bytes(8), bytes(2047))
    with pytest.raises(ValueError):
        cdsector.build_form1(16, bytes(7), bytes(2048))


def test_is_form1_rejects_form2_subheader():
    sub_form2 = bytes([0, 0, 0x20, 0, 0, 0, 0x20, 0])
    assert not cdsector.is_form1(cdsector.SYNC + cdsector.header(0) + sub_form2 + bytes(RAW - 24))


BIN = os.environ.get("KENSHIN_BIN")
if not BIN:
    found = sorted((Path(__file__).resolve().parent.parent / "original").glob("*.bin"))
    BIN = str(found[0]) if found else None


@pytest.mark.skipif(not BIN, reason="original disc image not available")
def test_corpus_every_form1_sector_regenerates_identically():
    import numpy as np

    checked = 0
    chunk = 8192
    with open(BIN, "rb") as f:
        lba0 = 0
        while True:
            buf = f.read(RAW * chunk)
            if not buf:
                break
            arr = np.frombuffer(buf, dtype=np.uint8).reshape(-1, RAW)
            sel = np.array([cdsector.is_form1(bytes(r[:24])) for r in arr])
            orig = arr[sel]
            rebuilt = orig.copy()
            rebuilt[:, 0x818:] = 0
            rebuilt = cdsector.complete_form1(rebuilt)
            bad = np.nonzero((rebuilt != orig).any(axis=1))[0]
            assert bad.size == 0, f"LBA {lba0 + np.nonzero(sel)[0][bad[0]]}"
            checked += int(sel.sum())
            lba0 += arr.shape[0]
    assert checked > 80000


def test_complete_form1_does_not_mutate_input():
    import numpy as np

    arr = np.frombuffer(cdsector.build_form1(16, bytes(8), bytes(range(256)) * 8), dtype=np.uint8)
    arr = arr.reshape(1, RAW).copy()
    arr[0, 0x818:] = 0
    before = arr.copy()
    cdsector.complete_form1(arr)
    assert (arr == before).all()
