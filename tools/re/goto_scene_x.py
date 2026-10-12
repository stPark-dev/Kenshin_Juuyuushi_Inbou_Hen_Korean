"""Linux/Xephyr counterpart of goto_scene.py: boot on display :5, redirect the first
scene load (40) to SCENE, and run that scene's script at OFFSET on the next frame
yield (VM op 0x30), then capture a frame a second.

usage (run with the Python that has python-xlib, e.g. ../venv/bin/python):
  goto_scene_x.py image.cue SCENE OFFSET_HEX OUTDIR [SECONDS]
e.g. goto_scene_x.py build/kenshin_ko.cue 1 2658 work/z01   # ZROUP01 team battle lineup (総当たり戦)

Needs Xephyr :5 running (docs/HANDOFF.md §8) and the GDB server enabled. DUCKSTATION
overrides the emulator path. The default name is not entered on this route, so the
lineup shows the source name 聖.
"""
import os
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rsp import RSP  # noqa: E402

DISPLAY = ":5"
DS = os.environ.get("DUCKSTATION", os.path.expanduser("~/.local/opt/duckstation/v0.1-11894/DuckStation-x64.AppImage"))
XKEY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xkey.py")
SET_SCENE, OP30, DISPATCH, BASE_PTR = 0x801DFE64, 0x801D84FC, 0x801D7CD8, 0x801DC388

CUE, SCENE, TEXT, OUT = sys.argv[1], int(sys.argv[2]), int(sys.argv[3], 16), sys.argv[4]
SECS = int(sys.argv[5]) if len(sys.argv) > 5 else 20
os.makedirs(OUT, exist_ok=True)


def key(*k):
    subprocess.run([sys.executable, XKEY, DISPLAY, *k], check=True)


def grab(path):
    subprocess.run(["import", "-display", DISPLAY, "-window", "root", "-crop", "800x605+0+23", path], check=True)


env = dict(os.environ, DISPLAY=DISPLAY)
subprocess.Popen([DS, "-batch", "-fastboot", CUE], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(30)
key("Escape", "2", "Return", "3", "Return", "3")  # an update notice, the title, the title menu
r = RSP(timeout=30)
r.send("?")
r.send(f"Z0,{SET_SCENE:x},4")
r.send(f"Z0,{OP30:x},4")
r.send("c", wait=False)
hit = []


def reg(n):
    v = r.send(f"p{n:x}")
    while not re.fullmatch(r"[0-9a-f]{8}", v):  # stray packets after the stop reply
        v = r._packet()
    return int.from_bytes(bytes.fromhex(v), "little")


def watch():
    while True:
        r.wait_stop()
        pc = reg(0x25)
        if pc == SET_SCENE:
            a0 = reg(4)
            print(f"set_scene({a0})", flush=True)
            if a0 == 40 and not hit:
                r.send(f"P4={SCENE.to_bytes(4, 'little').hex()}")
                r.send(f"z0,{SET_SCENE:x},4")
                hit.append(a0)
                print(f"  -> {SCENE}", flush=True)
        elif pc == OP30 and hit:
            base = int.from_bytes(r.read_mem(BASE_PTR, 4), "little")
            r.send(f"z0,{OP30:x},4")
            r.send(f"P12={(base + TEXT).to_bytes(4, 'little').hex()}")  # s2: bytecode pointer
            r.send(f"P25={DISPATCH.to_bytes(4, 'little').hex()}")
            print(f"  -> script 0x{TEXT:x}", flush=True)
            r.send("c", wait=False)
            hit.append("run")
            return
        r.send("c", wait=False)


threading.Thread(target=watch, daemon=True).start()
time.sleep(1)
key("z", "4", "z", "3")  # new game, hero
for _ in range(30):
    if "run" in hit:
        break
    key("z", "2")
for i in range(SECS):
    time.sleep(1)
    grab(f"{OUT}/f{i:02d}.png")
print("done" if "run" in hit else "script never ran", flush=True)
