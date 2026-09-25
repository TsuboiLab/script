"""Streamlit AppTest exercises controls without a browser or real hardware."""
from pathlib import Path
import sys
import time
import unittest
import uuid
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.auto_guide import GuideService, load_config


class UITests(unittest.TestCase):
    def test_prepare_track_stop_disconnect(self):
        config = load_config(ROOT / '.config')
        output = ROOT / 'test/test_all' / f'test-ui-{uuid.uuid4().hex}.fit'
        config.update(simulation=True, exposure_sec=.01, settle_sec=.01, output_path=str(output))
        service = GuideService(config)
        st.cache_resource.clear()
        try:
            with patch('src.auto_guide.GuideService', return_value=service):
                app = AppTest.from_file(str(ROOT / 'app_auto_guide.py')).run(timeout=30)
                self.assertFalse(app.exception)
                self.assertTrue(app.button[1].disabled)
                app.button[0].click().run()
                self.wait(service, '準備完了')
                app.run()
                self.assertFalse(app.exception)
                self.assertFalse(app.button[1].disabled)
                app.button[1].click().run()
                deadline = time.monotonic() + 5
                while service.snapshot()['frame'] == 0 and time.monotonic() < deadline:
                    time.sleep(.02)
                app.run()
                self.assertFalse(app.exception)
                self.assertGreater(service.snapshot()['frame'], 0)
                app.button[2].click().run()
                self.wait(service, '追尾終了')
                app.run()
                app.button[3].click().run()
                self.wait(service, '未接続')
                self.assertFalse(app.exception)
        finally:
            service.close()
            service.thread.join(3)
            st.cache_resource.clear()
            output.unlink(missing_ok=True)
            output.with_suffix('.tmp.fits').unlink(missing_ok=True)

    def wait(self, service, state):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if service.snapshot()['state'] == state:
                return
            time.sleep(.02)
        self.fail(service.snapshot()['state'])
