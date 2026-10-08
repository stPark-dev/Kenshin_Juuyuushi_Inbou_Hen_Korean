import glob
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)


@pytest.mark.skipif(not BIN, reason="disc image not available")
def test_extract_writes_all_scenes(tmp_path):
    n = extract.extract_all(Path(BIN), tmp_path)
    files = sorted(tmp_path.glob("ZROUP*.json"))
    assert len(files) == 58
    rows = [r for f in files for r in json.loads(f.read_text(encoding="utf-8"))]
    assert n == len(rows) == 10401
    assert all({"id", "src", "hash", "slot", "ref", "speaker"} <= set(r) for r in rows)
