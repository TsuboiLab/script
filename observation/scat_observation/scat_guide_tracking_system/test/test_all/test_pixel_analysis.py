"""Hardware-free image regression tests, including a known synthetic slit."""
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.base__fits_utils import read_image
from src.base__point_detector import detect_science_slit, slit_center, point_sources, pixel_offset, detect_frame


class PixelAnalysisTests(unittest.TestCase):
    def test_multiple_sources_with_banded_background(self):
        yy, xx = np.indices((240, 320))
        a = 6000. + np.random.default_rng(9).normal(0, 10, xx.shape)
        a += 200 * (yy > 130)
        for x, y in ((70, 60), (230, 180)):
            a += 1500 * np.exp(-((xx-x)**2+(yy-y)**2)/8)
        sources = point_sources(a)
        self.assertEqual(len(sources), 2)
        for x, y in ((70, 60), (230, 180)):
            self.assertLess(min(np.hypot(s['x']-x, s['y']-y) for s in sources), .5)

    def test_missing_slit_keeps_sources_without_inventing_center(self):
        yy, xx = np.indices((240, 320))
        a = 6000. + np.random.default_rng(2).normal(0, 10, xx.shape)
        a += 1500 * np.exp(-((xx-70)**2+(yy-60)**2)/8)
        result = detect_frame(a, [120, 10, 200, 230])
        self.assertIsNone(result['slit'])
        self.assertTrue(result['warning'])
        self.assertEqual(len(result['sources']), 1)

    def test_known_slit_with_obscuring_star(self):
        rng = np.random.default_rng(22)
        yy, xx = np.indices((240, 320))
        flat = 1000. + rng.normal(0, 2, (240, 320))
        flat[35:205, 158:163] -= 600
        image = np.minimum(flat + 100000*np.exp(-((xx-153)**2+(yy-120)**2)/32), 65535)
        found = detect_science_slit(image, [120, 10, 200, 230])
        np.testing.assert_allclose(found['center'], [160, 119.5], atol=2)
        self.assertEqual(found['component_count'], 2)
        source = point_sources(image)[0]
        offset = pixel_offset([source['x'], source['y']], found['center'])
        self.assertGreater(offset[0], 0)

    def test_real_science_image_without_flat(self):
        image = read_image(ROOT / 'pictures/02_slit_guide_images/test_sigmagem_nearby_slit.fit')
        roi = [880, 250, 1130, 850]
        found = detect_science_slit(image, roi)
        np.testing.assert_allclose(slit_center(image, roi, science_image=True), found['center'])
        self.assertGreaterEqual(found['component_count'], 2)
        # Broad image-inspection bounds, not a claim of subpixel accuracy.
        self.assertTrue(990 < found['center'][0] < 1025)
        self.assertTrue(540 < found['center'][1] < 590)
        estimates = [detect_science_slit(image, roi, threshold_sigma=t)['center'] for t in (2, 2.5, 3)]
        self.assertLess(np.max(np.ptp(estimates, axis=0)), 5)

    def test_flat_gradient_and_pixel_sign(self):
        image = read_image(ROOT / 'pictures/02_slit_guide_images/test_00.fits')
        center = slit_center(image, [450, 250, 660, 760])
        self.assertTrue(540 < center[0] < 580)
        self.assertTrue(500 < center[1] < 560)
        np.testing.assert_array_equal(pixel_offset([8, 3], [2, 5]), [-6, 2])

    def test_no_slit_rejected(self):
        with self.assertRaises(ValueError):
            detect_science_slit(np.ones((200, 200)), [10, 10, 190, 190])
