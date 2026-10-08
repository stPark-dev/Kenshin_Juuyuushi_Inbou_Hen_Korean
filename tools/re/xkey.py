"""Send key taps to an isolated X display only. usage: xkey.py :5 Return 0.1 z ..."""
import sys,time
from Xlib import display, X, XK
from Xlib.ext import xtest
disp=sys.argv[1]
assert disp not in (':0',':1'), 'refusing to touch the user desktop'
d=display.Display(disp)
d.screen().root.warp_pointer(400,300); d.sync()  # no WM on the nested display: focus follows the pointer
for tok in sys.argv[2:]:
    try:
        time.sleep(float(tok)); continue
    except ValueError: pass
    kc=d.keysym_to_keycode(XK.string_to_keysym(tok))
    xtest.fake_input(d,X.KeyPress,kc); d.sync(); time.sleep(0.08)
    xtest.fake_input(d,X.KeyRelease,kc); d.sync(); time.sleep(0.05)
