"""Read-only inspection of actual tab ancestry; no input messages."""
import ctypes
from ctypes import wintypes
from dataclasses import asdict
import datetime
import json
from pathlib import Path
import sys
import traceback

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from src.base__nishimura_controler import NishimuraController, _load, select_tab_button, TAB_ACTIONS

result = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
try:
    controller = NishimuraController()
    pid = controller._ensure_pid()
    with _load('master_position').Reader(pid) as reader:
        api = _load('master_gui').Win32()
        api.u.GetParent.argtypes = [wintypes.HWND]
        api.u.GetParent.restype = wintypes.HWND
        windows = api.windows(pid)
        api.u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        def rect_of(hwnd):
            rect = wintypes.RECT()
            if not api.u.GetWindowRect(hwnd, ctypes.byref(rect)):
                raise ctypes.WinError()
            return [rect.left, rect.top, rect.right, rect.bottom]
        result['pid'] = pid
        result['windows'] = [dict(asdict(w), parent=api.u.GetParent(w.hwnd), rect=rect_of(w.hwnd)) for w in windows]
        result['position'] = reader.read_once()
        result['resolved'] = {}
        for action in TAB_ACTIONS:
            try:
                result['resolved'][action] = asdict(select_tab_button(windows, pid, action, api.u.GetParent, rect_of))
            except Exception as exc:
                result['resolved'][action] = {'error': str(exc)}
except Exception:
    result['error'] = traceback.format_exc()
Path(__file__).with_name('mot_tabs_admin_result.json').write_text(
    json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
