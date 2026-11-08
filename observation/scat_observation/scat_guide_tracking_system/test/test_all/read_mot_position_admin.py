"""Read-only elevated position check; no device commands."""
import json
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.base__nishimura_controler import NishimuraController

output = Path(__file__).with_name('mot_position_admin_result.json')
controller = NishimuraController()
try:
    result = {'ok': True, 'position': controller.read_position()}
except Exception:
    result = {'ok': False, 'error': traceback.format_exc()}
finally:
    controller.close()
output.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
