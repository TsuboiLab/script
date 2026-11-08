"""Hardware-free checks for fixed slit, independent detection and TCP targets."""
import json
import sys
import time
import unittest
import tempfile
import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.auto_guide import GuideService, load_config
from src.base__client_sender import MoTSender
from src.base__point_detector import calibrate_slit
from src.base__slit_settings import save_slit


class SplitTrackingTests(unittest.TestCase):
    def test_persist_slit_preserves_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'.config'
            path.write_text('# keep comment\ngain_ra = -2.0\n', encoding='utf-8')
            save_slit(path, [544.8,479.1], [1039,1391])
            save_slit(path, [545.,480.], [1039,1391])
            text = path.read_text(encoding='utf-8')
            data = tomllib.loads(text)
            self.assertEqual(data['gain_ra'], -2.)
            self.assertEqual(data['slit_initial_center_px'], [545.,480.])
            self.assertIn('# keep comment', text)

    def test_tilted_slit_with_gradient(self):
        yy, xx = np.indices((300, 400))
        rng = np.random.default_rng(70)
        image = 6000.+yy*.3+rng.normal(0, 4, xx.shape)
        image[(np.abs(xx-(200+.06*(yy-150))) < 3) & (yy>50) & (yy<250)] -= 70
        found = calibrate_slit(image)
        np.testing.assert_allclose(found['center'], [200.,150.], atol=4)

    def test_zero_image_has_no_calibrated_slit(self):
        with self.assertRaises(ValueError):
            calibrate_slit(np.ones((180, 220)))

    def test_fractional_hint_is_not_used_as_measured_position(self):
        yy, xx = np.indices((300, 400))
        image = 6000.+np.random.default_rng(7).normal(0, 3, xx.shape)
        image[(np.abs(xx-(244+.05*(yy-135))) < 3) & (yy>60) & (yy<210)] -= 100
        found = calibrate_slit(image, center_hint=[.6, 3/7])
        np.testing.assert_allclose(found['center'], [244,135], atol=3)
        with self.assertRaises(ValueError):
            calibrate_slit(np.ones((150,200)), center_hint=[.6,3/7])

    def test_absolute_target_payload(self):
        connection = MagicMock()
        connection.recv.return_value = b'{"status":"move"}'
        with patch('src.base__client_sender.socket.create_connection') as connect:
            connect.return_value.__enter__.return_value = connection
            MoTSender().send_target(12.5, 30.25)
            payload = json.loads(connection.sendall.call_args.args[0])
        self.assertEqual(payload, dict(command='track', ra=12.5, dec=30.25, pmra=0., pmdec=0.))

    def test_fixed_slit_and_three_second_interval(self):
        config = load_config(ROOT / '.config')
        config.update(simulation=True, exposure_sec=.01, settle_sec=.01)
        calls = []
        service = GuideService(config, sender=lambda *args: calls.append(time.monotonic()))
        def wait_for(predicate, timeout=5):
            deadline = time.monotonic()+timeout
            while not predicate():
                if time.monotonic() > deadline:
                    self.fail(str(service.snapshot()))
                time.sleep(.01)
        try:
            with patch('src.auto_guide.save_image'), patch('src.auto_guide.save_slit'), patch('src.auto_guide.detect_illuminated_slit') as detect:
                detect.return_value = dict(center=np.array([160., 120.]), endpoints=np.array([[160, 35], [160,205]]))
                service.connect()
                wait_for(lambda: service.snapshot()['state'] == '準備完了')
                service.start_capture()
                wait_for(lambda: service.snapshot()['frame'] >= 1)
                service.detect_slit_position()
                wait_for(lambda: 'slit' in service.snapshot())
                service.detect_target_position()
                wait_for(lambda: 'target' in service.snapshot())
                self.assertEqual(calls, [])
                service.start()
                wait_for(lambda: len(calls) >= 2)
                self.assertGreaterEqual(calls[1]-calls[0], 3.)
                self.assertEqual(detect.call_count, 1)
                self.assertEqual(service.snapshot()['slit'], [160.,120.])
                service.stop_tracking()
                count = len(calls)
                frame = service.snapshot()['frame']
                wait_for(lambda: service.snapshot()['frame'] > frame+1)
                self.assertEqual(len(calls), count)
                service.stop()
                wait_for(lambda: service.snapshot()['state'] == '追尾終了')
        finally:
            service.close()
            service.thread.join(5)


if __name__ == '__main__':
    unittest.main()
