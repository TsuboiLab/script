import uuid
import time
import unittest
from pathlib import Path
import sys

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.auto_guide import load_config, GuideService, SimulationCamera, Correction
from src.base__point_detector import slit_center, point_sources
from src.base__fits_utils import read_image

ROOT = Path(__file__).resolve().parents[2]


def wait_for(service, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = service.snapshot()
        if predicate(s):
            return s
        time.sleep(.01)
    raise AssertionError(service.snapshot())


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.output = ROOT / 'test/test_all' / f'test-output-{uuid.uuid4().hex}.fit'
        self.c = load_config(ROOT / '.config')
        self.c.update(simulation=True, mot_enabled=True, exposure_sec=.01, settle_sec=.01,
                      output_path=str(self.output))
        self.services = []

    def tearDown(self):
        for s in self.services:
            s.close()
            s.thread.join(3)
            self.assertFalse(s.thread.is_alive())
        self.output.unlink(missing_ok=True)
        self.output.with_suffix('.tmp.fits').unlink(missing_ok=True)

    def service(self, **kwargs):
        s = GuideService(self.c, **kwargs)
        self.services.append(s)
        s.prepare()
        wait_for(s, lambda x: x['state'] == '準備完了')
        return s

    def test_real_camera_without_mount_send(self):
        self.c.update(simulation=False, mot_enabled=False,
                      guide_slit_roi=[110, 10, 210, 230])
        sent = []
        s = self.service(camera_factory=SimulationCamera,
                         sender=lambda *args: sent.append(args))
        s.start()
        wait_for(s, lambda x: x['frame'] >= 3 and 'correction' in x)
        s.stop()
        wait_for(s, lambda x: x['state'] == '追尾終了')
        self.assertEqual(sent, [])
        np.testing.assert_allclose(s.snapshot()['matrix'], self.c['matrix'])

    def test_mount_send_requires_calibration(self):
        import tempfile
        text = (ROOT / '.config').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / '.config'
            config.write_text(text, encoding='utf-8')
            self.assertFalse(load_config(config)['simulation'])
            config.write_text(text.replace('mot_enabled = false', 'mot_enabled = true'), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'calibration_confirmed'):
                load_config(config)

    def test_detection(self):
        cam = SimulationCamera(self.c)
        np.testing.assert_allclose(slit_center(cam.flat()), [160, 119.5], atol=.1)
        source = point_sources(cam.capture())[0]
        np.testing.assert_allclose([source['x'], source['y']], cam.position, atol=.05)
        self.assertEqual(point_sources(np.ones((80, 80))), [])
        with self.assertRaises(ValueError):
            slit_center(np.ones((80, 80)))

    def test_convergence_stop_restart_disconnect(self):
        s = self.service()
        s.start()
        result = wait_for(s, lambda x: 'offset' in x and np.linalg.norm(x['offset']) < .7)
        self.assertGreater(result['frame'], 2)
        s.stop()
        stopped = wait_for(s, lambda x: x['state'] == '追尾終了')
        time.sleep(.1)
        self.assertEqual(s.snapshot()['frame'], stopped['frame'])
        self.assertEqual(read_image(self.c['output_path']).shape, (240, 320))
        s.start()
        wait_for(s, lambda x: x['frame'] > stopped['frame'])
        s.disconnect()
        wait_for(s, lambda x: x['state'] == '未接続')

    def test_sender_failure(self):
        def fail(ra, dec):
            raise OSError('送信失敗')
        s = self.service(sender=fail)
        s.start()
        result = wait_for(s, lambda x: x['state'] == 'エラー')
        self.assertIn('送信失敗', result['error'])

    def test_stop_during_exposure_does_not_send(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        class SlowCamera(SimulationCamera):
            def capture(self):
                entered.set()
                release.wait(2)
                return super().capture()
        sent = []
        s = self.service(camera_factory=SlowCamera, sender=lambda *args: sent.append(args))
        s.start()
        self.assertTrue(entered.wait(2))
        s.stop()
        release.set()
        wait_for(s, lambda x: x['state'] == '追尾終了')
        self.assertEqual(sent, [])

    def test_missing_source_stops_without_send(self):
        class BlankCamera(SimulationCamera):
            def capture(self): return np.ones((240, 320))
        sent = []
        s = self.service(camera_factory=BlankCamera, sender=lambda *args: sent.append(args))
        s.start()
        wait_for(s, lambda x: x['state'] == 'エラー')
        self.assertEqual(sent, [])

    def test_correction_bounds_and_update(self):
        correction = Correction(self.c)
        _, command = correction.calculate(np.array([0., 0.]), np.array([100., -100.]))
        self.assertLessEqual(np.max(np.abs(command)), self.c['max_correction'])
        correction.previous = (np.array([0., 0.]), np.array([2., 0.]))
        correction.calculate(np.array([1., 0.]), np.array([100., 0.]))
        self.assertGreater(correction.matrix[0, 0], 1.)

    def test_science_loop_recomputes_slit_without_reference(self):
        from unittest.mock import patch
        image = read_image(ROOT / 'pictures/02_slit_guide_images/test_sigmagem_nearby_slit.fit')
        self.c['simulation'] = False
        class ReplayCamera:
            def __init__(self, config): self.frame = 0
            def connect(self): pass
            def prepare(self, cancel): pass
            def disconnect(self): pass
            def capture(self):
                result = np.roll(image, self.frame * 2, axis=1)
                self.frame += 1
                return result
        observed = []
        def send(ra, dec):
            observed.append(service.snapshot()['slit'])
            if len(observed) == 2:
                service.stop()
        with patch('src.auto_guide.read_image', side_effect=AssertionError('reference must not be read')):
            service = self.service(camera_factory=ReplayCamera, sender=send)
            self.assertNotIn('slit', service.snapshot())
            service.start()
            wait_for(service, lambda x: x['state'] == '追尾終了')
        self.assertEqual(len(observed), 2)
        np.testing.assert_allclose(np.array(observed[1])-observed[0], [2, 0], atol=.2)

    def test_adaptation_reduces_scale_mismatch(self):
        correction = Correction(self.c)
        position = np.array([0., 0.])
        slit = np.array([100., 0.])
        for _ in range(30):
            _, command = correction.calculate(position, slit)
            if not np.any(command):
                break
            correction.previous = (position.copy(), command.copy())
            # Plant needs 2 command units per pixel; configured matrix starts at 1.
            position = position + command/2
        self.assertLess(np.linalg.norm(slit-position), 1.)
        self.assertTrue(1 < correction.matrix[0, 0] <= 2)


if __name__ == '__main__':
    unittest.main()
