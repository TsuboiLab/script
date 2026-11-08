"""Read-only GUI identity check. Never clicks or sends device commands."""
import json
from pathlib import Path
import sys
import traceback

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root.parent / 'scat_auto_observation' / 'test_20260917'))
from src.base__nishimura_controler import NishimuraController
from master_gui import GuiBridge

try:
    pids = NishimuraController.master_pids()
    if len(pids) != 1:
        raise RuntimeError(f'Expected one Master2018 process: {pids}')
    with GuiBridge(pids[0]) as bridge:
        result = {'inspection': bridge.inspect(), 'position': bridge.reader.read_once()}
        result['resolution'] = {}
        for action in ('slit:open', 'slit:close', 'slit:stop'):
            try:
                parent, button = bridge.resolve(action)
                result['resolution'][action] = {'ok': True, 'hwnd': button.hwnd}
            except Exception as exc:
                result['resolution'][action] = {'ok': False, 'error': str(exc)}
except Exception:
    result = {'error': traceback.format_exc()}
Path(__file__).with_name('mot_gui_inspection_result.json').write_text(
    json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
