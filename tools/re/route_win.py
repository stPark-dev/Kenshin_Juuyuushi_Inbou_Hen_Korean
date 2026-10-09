"""Boot an image in DuckStation on Windows, start a new game, then press ○ and capture.

usage: route_win.py image.cue outdir presses [interval]
Waits for the title menu (reference crops in winds.TITLE_REFS), skipping the
intro with Start, then Start → ○ (protagonist) and `presses` × (○, capture).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winds  # noqa: E402

CUE, OUT, PRESSES = sys.argv[1], sys.argv[2], int(sys.argv[3])
STEP = float(sys.argv[4]) if len(sys.argv) > 4 else 4
os.makedirs(OUT, exist_ok=True)
p = winds.launch(CUE)
h = winds.game_window(p.pid)
print("pid", p.pid, flush=True)


def at_title():
    return winds.at_title(winds.grab(h))


for i in range(120):
    if at_title():
        break
    if i > 8:
        winds.key(h, "Return")  # skip the intro movie
    time.sleep(2)
else:
    raise SystemExit("title menu never appeared")
time.sleep(1)
winds.key(h, "Return")
time.sleep(3)
winds.key(h, "z")
time.sleep(3)
winds.key(h, "z")
time.sleep(8)
winds.grab(h).save(f"{OUT}/s00.png")
for i in range(1, PRESSES + 1):
    winds.key(h, "z")
    time.sleep(STEP)
    winds.grab(h).save(f"{OUT}/s{i:02d}.png")
print("done", flush=True)
