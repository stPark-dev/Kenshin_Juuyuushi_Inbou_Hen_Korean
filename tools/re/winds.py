"""Drive a DuckStation window on Windows without touching the user's focus.

Keys go to the emulator window with PostMessage (Qt reads WM_KEYDOWN from its
queue), frames come from PrintWindow, so the user can keep working elsewhere.
"""
import ctypes
import os
import subprocess
import time
from ctypes import wintypes

import win32con
import win32gui
import win32process
import win32ui
from PIL import Image

DS = r"C:\Users\S.T.Park\tools\duckstation\duckstation-qt-x64-ReleaseLTCG.exe"
VK = {"Return": win32con.VK_RETURN, "Up": win32con.VK_UP, "Down": win32con.VK_DOWN,
      "Left": win32con.VK_LEFT, "Right": win32con.VK_RIGHT, "BackSpace": win32con.VK_BACK,
      **{f"F{i}": win32con.VK_F1 + i - 1 for i in range(1, 13)}}
user32 = ctypes.windll.user32


def launch(cue, state=None):
    """Start DuckStation on `cue`; `state` boots straight into that save-state slot.
    The SaveGameStateN hotkeys write savestates/savestate_N.sav (not the per-game
    slot `-state N` reads), so the file is passed with -statefile."""
    extra = ["-statefile", os.path.join(os.path.dirname(DS), "savestates", f"savestate_{state}.sav")] if state is not None else []
    p = subprocess.Popen([DS, "-batch", "-fastboot", "-nofullscreen", *extra, cue])
    return p


def windows(pid):
    out = []

    def cb(h, _):
        if win32process.GetWindowThreadProcessId(h)[1] == pid and win32gui.IsWindowVisible(h):
            out.append(h)
        return True

    win32gui.EnumWindows(cb, None)
    return out


def game_window(pid, timeout=60):
    """The top-level window showing the game (largest visible one)."""
    end = time.time() + timeout
    while time.time() < end:
        hs = windows(pid)
        if hs:
            def area(h):
                l, t, r, b = win32gui.GetClientRect(h)
                return (r - l) * (b - t)
            return max(hs, key=area)
        time.sleep(0.5)
    raise TimeoutError("no DuckStation window")


def _targets(hwnd):
    kids = []
    win32gui.EnumChildWindows(hwnd, lambda h, _: kids.append(h) or True, None)
    return [hwnd] + kids


def key(hwnd, name, hold=0.08):
    vk = VK.get(name) or ord(name.upper())
    scan = user32.MapVirtualKeyW(vk, 0)
    ext = 1 << 24 if vk in (win32con.VK_UP, win32con.VK_DOWN, win32con.VK_LEFT, win32con.VK_RIGHT) else 0
    down = 1 | (scan << 16) | ext
    up = down | (1 << 30) | (1 << 31)
    for h in _targets(hwnd):
        win32gui.PostMessage(h, win32con.WM_KEYDOWN, vk, down)
    time.sleep(hold)
    for h in _targets(hwnd):
        win32gui.PostMessage(h, win32con.WM_KEYUP, vk, up)


def grab(hwnd):
    """Client area of the window as an RGB image (PrintWindow, full content)."""
    l, t, r, b = win32gui.GetClientRect(hwnd)
    w, h = r - l, b - t
    hdc = win32gui.GetWindowDC(hwnd)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src, w, h)
    mem.SelectObject(bmp)
    user32.PrintWindow(hwnd, mem.GetSafeHdc(), 3)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
    info = bmp.GetInfo()
    im = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    win32gui.DeleteObject(bmp.GetHandle())
    mem.DeleteDC()
    src.DeleteDC()
    win32gui.ReleaseDC(hwnd, hdc)
    return im
