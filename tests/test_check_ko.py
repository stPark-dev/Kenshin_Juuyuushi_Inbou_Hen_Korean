import glob
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import check_ko  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)
GALMURI = Path(os.environ.get("KENSHIN_GALMURI14", ROOT.parent / "galmuri" / "Galmuri14.bdf"))
ok = BIN and GALMURI.is_file() and (ROOT / "text" / "ko" / "ZROUP40.json").is_file()


@pytest.fixture(scope="module")
def ctx():
    return check_ko.Context.load(Path(BIN), GALMURI)


@pytest.mark.skipif(not ok, reason="disc, Galmuri14 or ZROUP40 translation not available")
def test_current_zroup40_translation_is_clean(ctx):
    res = check_ko.check_scene(ctx, "ZROUP40", ROOT / "text" / "ko" / "ZROUP40.json")
    assert res["problems"] == []
    assert res["translated"] == res["total"] == 44


@pytest.mark.skipif(not ok, reason="disc, Galmuri14 or ZROUP40 translation not available")
def test_broken_entry_is_reported(ctx, tmp_path):
    d = json.loads((ROOT / "text" / "ko" / "ZROUP40.json").read_text(encoding="utf-8"))
    d["ZROUP40:f1d0"]["ko"] = "예아니오"  # control codes dropped
    p = tmp_path / "ZROUP40.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    res = check_ko.check_scene(ctx, "ZROUP40", p)
    assert any("ZROUP40:f1d0" in x and "control" in x for x in res["problems"])


@pytest.mark.skipif(not ok, reason="disc, Galmuri14 or ZROUP40 translation not available")
def test_missing_file_reports_zero_coverage(ctx, tmp_path):
    res = check_ko.check_scene(ctx, "ZROUP40", tmp_path / "none.json")
    assert res["translated"] == 0 and res["problems"] == []
