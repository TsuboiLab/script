"""Explicitly authorized live test: one controller power-ON click, no retries."""
import datetime
import json
from pathlib import Path
import sys
import time
import traceback
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.base__nishimura_controler import NishimuraController, _load

result = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'action': 'power:on'}
output = Path(__file__).with_name('mot_power_on_admin_result.json')
controller = NishimuraController()
try:
    result['before'] = controller.read_position()
    result['phase'] = 'before_single_click'
    output.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
    result['command'] = controller.click('power:on')
    result['phase'] = 'click_returned'
    output.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
    time.sleep(3)
    result['after'] = controller.read_position()
    result['windows'] = [asdict(w) for w in _load('master_gui').Win32().windows(controller.pid)]
except Exception:
    result['error'] = traceback.format_exc()
finally:
    controller.close()
    output.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
