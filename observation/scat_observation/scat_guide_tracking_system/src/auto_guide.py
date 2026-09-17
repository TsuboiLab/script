"""Single worker owns the ASCOM apartment; UI reads immutable snapshots."""
import queue
import threading
import time
import tomllib
from pathlib import Path

import numpy as np
from .base__fits_utils import read_image, save_image
from .base__point_detector import slit_center, point_sources, pixel_offset
from .base__client_sender import MoTSender


def load_config(path):
    path = Path(path).resolve()
    with path.open('rb') as f:
        c = tomllib.load(f)
    for key in ('flat_path', 'output_path'):
        c[key] = str(path.parent / c[key])
    if c['guide_slit_mode'] not in ('science', 'reference'):
        raise ValueError('guide_slit_mode は science または reference')
    roi = c['guide_slit_roi']
    if len(roi) != 4 or any(type(v) is not int for v in roi) or not (0 <= roi[0] < roi[2] and 0 <= roi[1] < roi[3]):
        raise ValueError('guide_slit_roi は [x0,y0,x1,y1] を指定してください')
    for key in ('exposure_sec', 'exposure_timeout_sec', 'cooling_timeout_sec',
                'temperature_tolerance_c', 'threshold_sigma', 'max_target_jump_px', 'max_correction'):
        if not np.isfinite(c[key]) or c[key] <= 0:
            raise ValueError(f'{key} は正の有限値を指定してください')
    for key in ('settle_sec', 'deadband_px'):
        if not np.isfinite(c[key]) or c[key] < 0:
            raise ValueError(f'{key} は0以上を指定してください')
    if not np.isfinite(c['temperature_c']):
        raise ValueError('temperature_c が不正です')
    if not 0 < c['gain'] <= 1 or not 0 <= c['adaptive_rate'] <= .2:
        raise ValueError('gain は (0,1]、adaptive_rate は [0,0.2]')
    if type(c['target_brightness_rank']) is not int or not 1 <= c['target_brightness_rank'] <= 5:
        raise ValueError('target_brightness_rank は1～5')
    m = np.asarray(c['matrix'], dtype=float)
    if m.shape != (2, 2) or not np.isfinite(m).all() or abs(np.linalg.det(m)) < 1e-9:
        raise ValueError('matrix は可逆な有限値の2×2行列を指定してください')
    MoTSender(c['mot_host'], c['mot_port'], c['mot_timeout_sec'], c['mot_expected_response'])
    if not c['simulation'] and not c['calibration_confirmed']:
        raise ValueError('実機には calibration_confirmed の設定が必要です')
    return c


class Correction:
    def __init__(self, config):
        self.c = config
        self.matrix = np.array(config['matrix'], dtype=float)
        self.initial = self.matrix.copy()
        self.previous = None

    def calculate(self, position, slit):
        if self.previous is not None:
            previous_position, command = self.previous
            motion = position - previous_position
            predicted = self.matrix @ motion
            # Only learn from plausible responses of the same locked source.
            if .2 < np.linalg.norm(motion) < self.c['max_target_jump_px'] and np.dot(predicted, command) > 0:
                candidate = self.matrix + self.c['adaptive_rate'] * np.outer(command - predicted, motion) / np.dot(motion, motion)
                relative = candidate @ np.linalg.inv(self.initial)
                singular = np.linalg.svd(relative, compute_uv=False)
                if singular.min() >= .5 and singular.max() <= 2 and np.linalg.det(relative) > 0:
                    self.matrix = candidate
        self.previous = None
        error = pixel_offset(position, slit)
        if np.linalg.norm(error) <= self.c['deadband_px']:
            return error, np.zeros(2)
        command = self.c['gain'] * (self.matrix @ error)
        command *= min(1., self.c['max_correction'] / max(np.max(np.abs(command)), 1e-12))
        return error, command


class SimulationCamera:
    def __init__(self, config):
        self.c = config
        self.position = np.array([142., 102.])
        self.rng = np.random.default_rng(42)

    def connect(self): pass
    def prepare(self, cancel): pass
    def disconnect(self): pass

    def flat(self):
        image = np.full((240, 320), 1000.)
        image[30:210, 158:163] = 100
        return image

    def capture(self):
        time.sleep(self.c['exposure_sec'])
        yy, xx = np.indices((240, 320))
        image = 100 + self.rng.normal(0, 2, (240, 320)) + 3000 * np.exp(-((xx-self.position[0])**2+(yy-self.position[1])**2)/8)
        image[30:210, 158:163] -= 60
        return image

    def send(self, ra, dec):
        self.position += np.linalg.solve(np.array(self.c['matrix']), [ra, dec])


class GuideService:
    def __init__(self, config, camera_factory=None, sender=None):
        self.c = config
        self.camera_factory = camera_factory
        self.sender = sender
        self.commands = queue.Queue()
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.data = dict(state='未接続', error='', frame=0, image=None)
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def snapshot(self):
        with self.lock:
            return self.data.copy()

    def publish(self, **values):
        with self.lock:
            self.data.update(values)

    def prepare(self):
        with self.lock:
            if self.data['state'] not in ('未接続', 'エラー'):
                return
            self.stop_event.clear()
            for key in ('slit', 'target', 'sources', 'offset', 'correction', 'matrix'):
                self.data.pop(key, None)
            self.data['image'] = None
            self.data.update(state='冷却中', error='')
            self.commands.put('prepare')

    def start(self):
        with self.lock:
            if self.data['state'] not in ('準備完了', '追尾終了'):
                return
            self.stop_event.clear()
            self.data['state'] = '追尾開始中'
            self.commands.put('start')

    def stop(self):
        with self.lock:
            self.stop_event.set()
            if self.data['state'] in ('追尾中', '追尾開始中'):
                self.data['state'] = '停止中'
    def disconnect(self):
        self.stop_event.set()
        self.commands.put('disconnect')

    def close(self):
        self.stop_event.set()
        self.commands.put('close')

    def _worker(self):
        camera = None
        ready = False
        pythoncom = None
        try:
            if not self.c['simulation'] and self.camera_factory is None:
                import pythoncom
                pythoncom.CoInitialize()
            while True:
                action = self.commands.get()
                try:
                    if action in ('close', 'disconnect'):
                        if camera is not None:
                            camera.disconnect()
                        camera, ready = None, False
                        self.publish(state='未接続')
                        if action == 'close':
                            return
                    elif action == 'prepare' and camera is None:
                        self.publish(state='冷却中', error='')
                        if self.camera_factory:
                            camera = self.camera_factory(self.c)
                        elif self.c['simulation']:
                            camera = SimulationCamera(self.c)
                        else:
                            from .base__atik_camera_contloer import GuideCamera
                            camera = GuideCamera(self.c)
                        camera.connect()
                        camera.prepare(self.stop_event)
                        if self.stop_event.is_set():
                            raise RuntimeError('準備を中止しました')
                        science_mode = self.c['guide_slit_mode'] == 'science'
                        guide_roi = [110, 10, 210, 230] if self.c['simulation'] else self.c['guide_slit_roi']
                        shape = None
                        if not science_mode:
                            flat = camera.flat() if self.c['simulation'] else read_image(self.c['flat_path'])
                            slit = slit_center(flat, None if self.c['simulation'] else self.c.get('slit_roi'))
                            shape = flat.shape
                            self.publish(slit=slit.tolist(), image=flat)
                        send = self.sender or (camera.send if self.c['simulation'] else
                            MoTSender(self.c['mot_host'], self.c['mot_port'],
                                      self.c['mot_timeout_sec'], self.c['mot_expected_response']).send_correction)
                        ready = True
                        self.publish(state='準備完了')
                    elif action == 'start' and ready:
                        self.publish(state='追尾中', error='')
                        correction = Correction(self.c)
                        target = None
                        while not self.stop_event.is_set():
                            image = camera.capture()
                            save_image(self.c['output_path'], image, self.c['exposure_sec'])
                            self.publish(image=image, frame=self.snapshot()['frame'] + 1)
                            # An exposure already underway is saved; no new correction starts after stop.
                            if self.stop_event.is_set():
                                break
                            if shape is not None and image.shape != shape:
                                raise ValueError('準備時または前回の画像と撮像画像のサイズが一致しません')
                            shape = image.shape
                            if science_mode:
                                slit = slit_center(image, guide_roi, science_image=True)
                                self.publish(slit=slit.tolist())
                            sources = point_sources(image, self.c['threshold_sigma'])
                            if target is None:
                                rank = self.c['target_brightness_rank']
                                if len(sources) < rank:
                                    raise ValueError('指定順位の点源を検出できません')
                                chosen = sources[rank-1]
                            else:
                                if not sources:
                                    raise ValueError('追尾対象を見失いました')
                                chosen = min(sources, key=lambda s: np.linalg.norm(np.array([s['x'], s['y']])-target))
                                if np.linalg.norm(np.array([chosen['x'], chosen['y']])-target) > self.c['max_target_jump_px']:
                                    raise ValueError('追尾対象の移動量が上限を超えました')
                            target = np.array([chosen['x'], chosen['y']])
                            error, command = correction.calculate(target, slit)
                            if np.any(command):
                                send(float(command[0]), float(command[1]))
                                correction.previous = (target.copy(), command.copy())
                            self.publish(target=target.tolist(), sources=sources, offset=error.tolist(),
                                         correction=command.tolist(), matrix=correction.matrix.tolist())
                            self.stop_event.wait(self.c['settle_sec'])
                        self.publish(state='追尾終了')
                except Exception as exc:
                    ready = False
                    if camera is not None:
                        try:
                            camera.disconnect()
                        except Exception as cleanup:
                            self.publish(error=f'{exc}; 切断失敗: {cleanup}', state='エラー')
                            continue
                    camera = None
                    self.publish(state='エラー', error=str(exc))
        except Exception as exc:
            self.publish(state='エラー', error=str(exc))
        finally:
            if pythoncom is not None:
                pythoncom.CoUninitialize()
