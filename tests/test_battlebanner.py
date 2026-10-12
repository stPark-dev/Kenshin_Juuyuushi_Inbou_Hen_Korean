import glob
import os
import struct
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import battlebanner  # noqa: E402
import grparc  # noqa: E402
import iso  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)


@pytest.fixture(scope="module")
def group00():
    if not BIN:
        pytest.skip("disc image not available")
    raw = Path(BIN).read_bytes()
    return grparc.parse(iso.read_file(raw, iso.load(raw), "ZROUP00.GRP")).get("GROUP00.BIN")


def _up(rgba, k=8):
    return np.kron(rgba, np.ones((k, k, 1), np.uint8))


def test_banners_found_in_source(group00):
    pics = battlebanner.export(group00)
    assert set(pics) == {b.name for b in battlebanner.BANNERS}
    for p in pics.values():
        assert p.shape == (battlebanner.H, battlebanner.W, 4)
        alpha = p[..., 3]
        # a framed picture: mostly opaque, transparent corners
        assert 0.5 < (alpha == 255).mean() < 1 and set(np.unique(alpha)) == {0, 255}


def test_export_import_round_trip(group00):
    for b in battlebanner.BANNERS:
        pic = battlebanner.export(group00)[b.name]
        idx = battlebanner.indices(_up(pic), group00)
        back = battlebanner.rgba(idx, group00)
        assert (back == pic).all()


def test_import_without_alpha_uses_magenta_as_transparent(group00):
    pic = battlebanner.export(group00)["league"]
    rgb = pic[..., :3].copy()
    rgb[pic[..., 3] == 0] = battlebanner.KEY
    idx = battlebanner.indices(_up(rgb), group00)
    assert ((idx == 0) == (pic[..., 3] == 0)).all()


def test_import_snaps_to_banner_colours(group00):
    noise = np.random.default_rng(1).integers(0, 256, (64, 256, 3), np.uint8)
    idx = battlebanner.indices(noise, group00)
    assert idx.shape == (battlebanner.H, battlebanner.W)
    assert set(np.unique(idx)) <= set(battlebanner.palette_indices(group00)) | {0}


def test_apply_changes_only_the_picture(group00, tmp_path):
    pic = battlebanner.export(group00)["kachinuki"].copy()
    pic[4:8, 4:40, :3] = 0  # an opaque black bar
    pic[4:8, 4:40, 3] = 255
    cv2.imwrite(str(tmp_path / "kachinuki.png"), cv2.cvtColor(_up(pic), cv2.COLOR_RGBA2BGRA))
    new, done = battlebanner.apply(group00, tmp_path)
    assert done == ["kachinuki"] and len(new) == len(group00)
    b = next(b for b in battlebanner.BANNERS if b.name == "kachinuki")
    diff = [i for i in range(len(group00)) if new[i] != group00[i]]
    assert diff and all(b.offset + 8 <= i < b.offset + 8 + battlebanner.W * battlebanner.H for i in diff)
    assert (battlebanner.export(new)["kachinuki"] == pic).all()


def test_apply_without_pictures_is_identity(group00, tmp_path):
    assert battlebanner.apply(group00, tmp_path) == (group00, [])


def test_apply_refuses_unexpected_layout(group00, tmp_path):
    bad = bytearray(group00)
    struct.pack_into("<HH", bad, battlebanner.BANNERS[0].offset + 4, 64, 32)
    with pytest.raises(ValueError):
        battlebanner.export(bytes(bad))
    with pytest.raises(ValueError):
        battlebanner.apply(bytes(bad), tmp_path)


def test_16_bit_png_reads_like_8_bit(group00, tmp_path):
    pic = battlebanner.export(group00)["league"]
    big = cv2.cvtColor(_up(pic), cv2.COLOR_RGBA2BGRA).astype(np.uint16) * 257
    cv2.imwrite(str(tmp_path / "league.png"), big)
    new, _ = battlebanner.apply(group00, tmp_path)
    assert (battlebanner.export(new)["league"] == pic).all()


def test_wrong_shape_is_refused(group00, tmp_path):
    cv2.imwrite(str(tmp_path / "league.png"), np.zeros((1024, 1536, 3), np.uint8))  # a typical AI output
    with pytest.raises(ValueError, match="4:1"):
        battlebanner.apply(group00, tmp_path)


def test_unreadable_picture_is_a_value_error(group00, tmp_path):
    (tmp_path / "league.png").write_bytes(b"not a png")
    with pytest.raises(ValueError):
        battlebanner.apply(group00, tmp_path)
