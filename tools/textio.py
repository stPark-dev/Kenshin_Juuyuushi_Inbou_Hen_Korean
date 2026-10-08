"""Source extraction (text/src, untracked) and Korean translation files (text/ko).

Source rows are regenerated from the disc and never committed. A translation
entry is keyed by string id "ZROUPnn:<hex offset>" and records the hash of the
source bytes it was made from; a hash mismatch marks it stale so a corrected
source never silently keeps an old translation.

text/ko/ZROUPnn.json: {id: {"src_hash", "ko", "status": "draft"|"reviewed", "note"}}
"""

import hashlib

import refs

STATUSES = {"draft", "reviewed"}


def src_hash(raw):
    return hashlib.sha1(raw).hexdigest()[:12]


def extract(scene, g):
    cls = refs.classify(g)
    rows = []
    for s in g.strings:
        text = s.raw.decode("cp932")
        rows.append(
            {
                "id": f"{scene}:{s.offset:x}",
                "offset": s.offset,
                "src": text,
                "hash": src_hash(s.raw),
                "slot": s.slot - 1,  # usable bytes (terminator excluded)
                "ref": cls[s.offset].status,
                "speaker": text.split("^c", 1)[0] if "^c" in text else None,
            }
        )
    return rows


def usable_translations(rows, ko, statuses):
    """Return ({offset: ko_text} eligible for the build, [problems])."""
    by_id = {r["id"]: r for r in rows}
    got, problems = {}, []
    for sid, e in ko.items():
        r = by_id.get(sid)
        if r is None:
            problems.append(f"{sid}: unknown id")
            continue
        if e.get("status") not in STATUSES:
            problems.append(f"{sid}: bad status {e.get('status')!r}")
            continue
        if e.get("src_hash") != r["hash"]:
            problems.append(f"{sid}: stale (source changed)")
            continue
        if e["status"] in statuses and e.get("ko"):
            got[r["offset"]] = e["ko"]
    return got, problems
