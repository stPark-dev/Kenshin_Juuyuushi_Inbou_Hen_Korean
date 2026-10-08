import glob
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import setup_work  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)


@pytest.mark.skipif(not BIN, reason="disc image not available")
def test_setup_work_regenerates_iso_and_grp(tmp_path):
    setup_work.setup(Path(BIN), tmp_path)
    assert len(list((tmp_path / "iso").iterdir())) == 66  # data files; MOV/XAD (Form 2) are skipped
    grps = sorted(p.name for p in (tmp_path / "grp").iterdir())
    assert len(grps) == 59 and "SYSTEM" in grps
    assert (tmp_path / "grp" / "ZROUP40" / "GROUP40.BIN").stat().st_size == 69536
    assert (tmp_path / "grp" / "SYSTEM" / "NAMEFONT.BIN").stat().st_size == 220128
