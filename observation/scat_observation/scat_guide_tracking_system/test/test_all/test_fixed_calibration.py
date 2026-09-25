"""Hardware-free tests: load only the control classes, avoiding ASCOM/FITS imports."""
import ast
from pathlib import Path
import threading
from datetime import datetime
import unittest
import numpy as np

source = Path(__file__).resolve().parents[2] / 'src' / 'auto_guide.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
scope = dict(np=np, datetime=datetime, pixel_offset=lambda p, s: np.asarray(s)-p)
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ('Correction', 'GuideService')], type_ignores=[]), str(source), 'exec'), scope)
Correction, Service = scope['Correction'], scope['GuideService']

class CalibrationTests(unittest.TestCase):
    def test_calibration_mixed_axes_and_units(self):
        h = np.array([[.5, .15], [-.1, .4]])  # pixel/arcsec
        class Camera:
            position = np.array([200., 200.])
            def capture(self): return self.position.copy()
        camera = Camera()
        scope['point_sources'] = lambda image, *a, **k: [dict(x=image[0], y=image[1])]
        service = Service.__new__(Service)
        service.c = dict(simulation=True, threshold_sigma=3, target_brightness_rank=1, calibration_settle_sec=0)
        service.stop_event = threading.Event()
        data = dict(frame=0)
        service.publish = lambda **kw: data.update(kw)
        service.snapshot = lambda: data.copy()
        service._apply_pending_settings = lambda: None
        service._save_image_safe = lambda image: None
        sent = []
        def send(ra, dec):
            sent.append([ra, dec])
            camera.position += h @ [ra, dec]
        service._calibrate_tracking(camera, send)
        np.testing.assert_allclose(sent, [[60,0],[-120,0],[0,60],[0,-120]])
        np.testing.assert_allclose(service.c['tracking_matrix_deg_per_pix'], np.linalg.inv(h)/3600)
        np.testing.assert_allclose(camera.position, np.array([200,200]) + h @ [-60,-60])
        self.assertEqual(len(data['calibration_points']), 4)
        service.lock = threading.Lock()
        service.data = data
        for _ in range(9): service._advance_calibration_points()
        self.assertEqual(len(data['calibration_points']), 4)
        service._advance_calibration_points()
        self.assertEqual(data['calibration_points'], [])
        service.c.update(max_correction=0, auto_gain_enabled=True)
        correction = Correction(service.c)
        _, command = correction.calculate(np.array([180.,170.]), np.array([200.,200.]))
        np.testing.assert_allclose(h @ command, [20,30])
        self.assertTrue(data['calibration_ready'])

    def test_four_consecutive_crossings_and_retreats(self):
        c = dict(tracking_matrix_deg_per_pix=(np.eye(2)/3600).tolist(), max_correction=0)
        correction = Correction(c)
        for i in range(4):
            correction.previous = (np.array([-20.,0.]), np.array([20.,0.]))
            correction.calculate(np.array([20.,0.]), np.zeros(2))
            self.assertAlmostEqual(correction.gains[0], .8 if i == 3 else 1.)
        for i in range(4):
            correction.previous = (np.array([20.,0.]), np.array([-20.,0.]))
            correction.calculate(np.array([30.,0.]), np.zeros(2))
        self.assertAlmostEqual(correction.gains[0], .84)
        np.testing.assert_allclose(c['tracking_matrix_deg_per_pix'], np.eye(2)/3600)

if __name__ == '__main__': unittest.main()
