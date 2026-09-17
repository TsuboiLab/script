"""ASCOM calls are made exclusively on the GuideService worker thread."""
import time
from .atik_camera import AtikCamera


class GuideCamera(AtikCamera):
    def __init__(self, config):
        super().__init__()
        self.c = config

    def prepare(self, cancel):
        self.set_ccd_temperature(self.c['temperature_c'])
        deadline = time.monotonic() + self.c['cooling_timeout_sec']
        while abs(float(self.camera.CCDTemperature) - self.c['temperature_c']) > self.c['temperature_tolerance_c']:
            if cancel.wait(.5):
                raise RuntimeError('冷却準備を中止しました')
            if time.monotonic() >= deadline:
                raise TimeoutError('カメラ冷却がタイムアウトしました')

    def capture(self):
        self.start_exposure(self.c['exposure_sec'])
        deadline = time.monotonic() + self.c['exposure_sec'] + self.c['exposure_timeout_sec']
        while not self.camera.ImageReady:
            if time.monotonic() >= deadline:
                if self.camera.CanAbortExposure:
                    self.camera.AbortExposure()
                raise TimeoutError('露光・読み出しがタイムアウトしました')
            time.sleep(.1)
        # ASCOM ImageArray indexes X first, including square detectors / ROI.
        import numpy as np
        return np.asarray(self.camera.ImageArray).T.copy()

    def disconnect(self):
        if self._cam is not None:
            self._cam.Connected = False
        self._cam = None
        self._connected = False
