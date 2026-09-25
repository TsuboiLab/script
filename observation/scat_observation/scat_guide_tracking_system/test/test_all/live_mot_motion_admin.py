"""Explicit live test: one short movement, followed by a stop. Never auto-retry."""
import argparse
import ctypes
from ctypes import wintypes
import datetime
import json
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.base__nishimura_controler import NishimuraController, _load, select_rotation_button


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['dome:right', 'dome:left', 'slit:open', 'slit:close'])
    parser.add_argument('--execute', action='store_true', required=True)
    args = parser.parse_args()
    controller = NishimuraController()
    output = Path(__file__).with_name('mot_motion_' + args.action.replace(':', '_') + '.json')
    report = {'action': args.action, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    def save():
        output.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding='utf-8')
    stop = 'dome:stop' if args.action.startswith('dome:') else 'slit:stop'
    try:
        report['before'] = controller.read_position()
        native = _load('master_gui').Win32()
        native.u.GetParent.argtypes = [wintypes.HWND]
        native.u.GetParent.restype = wintypes.HWND
        native.u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        def rect_of(hwnd):
            rect = wintypes.RECT()
            if not native.u.GetWindowRect(hwnd, ctypes.byref(rect)):
                raise ctypes.WinError()
            return rect.left, rect.top, rect.right, rect.bottom
        if args.action.startswith('dome:'):
            candidate = select_rotation_button(native.windows(controller.pid), controller.pid,
                stop, native.u.GetParent, rect_of, require_enabled=False)
        else:
            report['tab'] = controller.select_tab('ドーム')
            windows = native.windows(controller.pid)
            tabs = [w for w in windows if w.class_name == 'TTabSheet' and w.visible and w.caption == 'ドーム']
            candidates = [w for w in windows if w.class_name == 'TButton' and w.visible
                and w.caption == '停止' and len(tabs) == 1 and native.u.GetParent(w.hwnd) == tabs[0].hwnd]
            if len(candidates) != 1:
                raise RuntimeError('スリット停止の対応を特定できません')
            candidate = candidates[0]
        report['stop_hwnd_before'] = candidate.hwnd
        report['phase'] = 'ready'
        save()
        try:
            report['start'] = controller.click(args.action)
            report['phase'] = 'started'
            save()
            time.sleep(1)
            report['during'] = controller.read_position()
        finally:
            # Even a start timeout may have started motion. Stop once, never resend start.
            report['stop'] = controller.click(stop)
            report['phase'] = 'stop_returned'
            save()
        time.sleep(3)
        report['after'] = controller.read_position()
        time.sleep(2)
        report['after_settle'] = controller.read_position()
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        controller.close()
        save()


if __name__ == '__main__':
    main()
