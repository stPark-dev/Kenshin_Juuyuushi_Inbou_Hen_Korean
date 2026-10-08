"""Drive DuckStation on an isolated X display to the ZROUP40 town dialogue.

Waits without input until the title menu (reference crop) is on screen, then
selects New Game and advances. Captures the dialogue window after each press.
usage: route_town.py :5 ref.png outdir presses
"""
import os
import subprocess
import sys
import time

from PIL import Image, ImageChops, ImageStat
from Xlib import X, XK, display
from Xlib.ext import xtest

DISP, REF, OUT, PRESSES = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
assert DISP not in (":0", ":1"), "refusing to touch the user desktop"
d = display.Display(DISP)
os.makedirs(OUT, exist_ok=True)
ref = Image.open(REF).convert("RGB")


def key(name):
    d.screen().root.warp_pointer(400, 300)  # no WM on the nested display: focus follows the pointer
    d.sync()
    kc = d.keysym_to_keycode(XK.string_to_keysym(name))
    xtest.fake_input(d, X.KeyPress, kc)
    d.sync()
    time.sleep(0.08)
    xtest.fake_input(d, X.KeyRelease, kc)
    d.sync()


def grab(path, geom="800x610+0+23"):
    subprocess.run(["import", "-display", DISP, "-window", "root", "-crop", geom, path], check=True)
    return Image.open(path).convert("RGB")


def menu_diff():
    im = grab(f"{OUT}/_probe.png")
    crop = im.crop((250, 330, 550, 450))
    return sum(ImageStat.Stat(ImageChops.difference(crop, ref)).mean) / 3


for attempt in range(150):
    diff = menu_diff()
    if diff < 15:
        print(f"title menu after {attempt} polls (diff={diff:.1f})", flush=True)
        break
    time.sleep(2)
else:
    raise SystemExit("title menu never appeared")
time.sleep(1)
key("Return")  # Start on the title menu opens protagonist select
time.sleep(4)
key("z")  # confirm the protagonist
time.sleep(8)
for i in range(PRESSES):
    key("z")
    time.sleep(5)
    grab(f"{OUT}/d{i:02d}.png", "800x170+0+440")
print("done")
