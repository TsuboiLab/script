"""Single worker owns the ASCOM apartment; UI reads immutable snapshots."""
import queue
import threading
import time
import tomllib
from datetime import datetime
from pathlib import Path

import numpy as np
from .base__fits_utils import read_image, save_image
from .base__point_detector import slit_center, point_sources, pixel_offset, detect_frame, calibrate_slit
from .base__client_sender import MoTSender
from .base__point_detector import detect_illuminated_slit
from .base__slit_settings import save_slit, validate_slit


def load_config(path):
    path = Path(path).resolve()
    with path.open('rb') as f:
        c = tomllib.load(f)
    c['_config_path'] = str(path)
    for key in ('flat_path', 'output_path'):
        c[key] = str(path.parent / c[key])
    if c['guide_slit_mode'] not in ('science', 'reference'):
        raise ValueError('guide_slit_mode は science または reference')
    roi = c['guide_slit_roi']
    if len(roi) != 4 or any(type(v) is not int for v in roi) or not (0 <= roi[0] < roi[2] and 0 <= roi[1] < roi[3]):
        raise ValueError('guide_slit_roi は [x0,y0,x1,y1] を指定してください')
    for key in ('exposure_sec', 'exposure_timeout_sec', 'cooling_timeout_sec',
                'temperature_tolerance_c', 'threshold_sigma', 'max_target_jump_px'):
        if not np.isfinite(c[key]) or c[key] <= 0:
            raise ValueError(f'{key} は正の有限値を指定してください')
    if not np.isfinite(c['max_correction']) or c['max_correction'] < 0:
        raise ValueError('max_correction は0以上の有限値を指定してください')
    for key in ('settle_sec', 'deadband_px'):
        if not np.isfinite(c[key]) or c[key] < 0:
            raise ValueError(f'{key} は0以上を指定してください')
    if type(c.get('matrix_min_samples', 5)) is not int or not 3 <= c.get('matrix_min_samples', 5) <= 5:
        raise ValueError('matrix_min_samples は3〜5の整数を指定してください')
    if not np.isfinite(c.get('matrix_step_scale', .35)) or not 0 < c.get('matrix_step_scale', .35) <= 1:
        raise ValueError('matrix_step_scale は0より大きく1以下を指定してください')
    if not np.isfinite(c.get('pixel_scale_arcsec', 0.4)) or c['pixel_scale_arcsec'] <= 0:
        raise ValueError('pixel_scale_arcsec は正の有限値を指定してください')
    if not np.isfinite(c.get('max_gain_abs', 10.0)) or c.get('max_gain_abs', 10.0) <= 0:
        raise ValueError('max_gain_abs は正の有限値を指定してください')
    if not np.isfinite(c.get('declination_deg', 0.0)) or not -90 <= c.get('declination_deg', 0.0) <= 90:
        raise ValueError('declination_deg は-90〜90度を指定してください')
    if not np.isfinite(c.get('azimuth_deg', 0.0)) or not 0 <= c.get('azimuth_deg', 0.0) < 360:
        raise ValueError('azimuth_deg は0〜360度未満を指定してください')
    if not np.isfinite(c['temperature_c']):
        raise ValueError('temperature_c が不正です')
    c.setdefault('gain_ra', c['gain'])
    c.setdefault('gain_dec', c['gain'])
    # gain は補正量の倍率なので、正負を含む任意の有限値を受け付ける。
    # 符号反転は自動改善OFF時もユーザーが直接指定できるようにする。
    if not np.isfinite(c['gain_ra']) or not np.isfinite(c['gain_dec']) or not 0 <= c['adaptive_rate'] <= .2:
        raise ValueError('gain_ra/gain_dec は任意の有限値、adaptive_rate は [0,0.2]')
    if type(c['target_brightness_rank']) is not int or not 1 <= c['target_brightness_rank'] <= 5:
        raise ValueError('target_brightness_rank は1～5')
    m = np.asarray(c['matrix'], dtype=float)
    if m.shape != (2, 2) or not np.isfinite(m).all() or abs(np.linalg.det(m)) < 1e-9:
        raise ValueError('matrix は可逆な有限値の2×2行列を指定してください')
    MoTSender(c['mot_host'], c['mot_port'], c['mot_timeout_sec'], c['mot_expected_response'])
    c.setdefault('mot_enabled', True)  # Preserve existing configurations.
    for key in ('simulation', 'mot_enabled', 'calibration_confirmed'):
        if type(c[key]) is not bool:
            raise ValueError(f'{key} は true または false を指定してください')
    if type(c.get('auto_gain_enabled', True)) is not bool:
        raise ValueError('auto_gain_enabled は true または false を指定してください')
    if not c['simulation'] and c['mot_enabled'] and not c['calibration_confirmed']:
        raise ValueError('実機には calibration_confirmed の設定が必要です')
    return c


class Correction:
    """固定した度/pixel行列と、4連続の応答で調整するgain。"""
    def __init__(self, config):
        self.c = config
        self.previous = None
        self.gains = np.ones(2)
        self.crossings = np.zeros(2, dtype=int)
        self.retreats = np.zeros(2, dtype=int)
        self.last_needs_correction = False
        self.last_distance_px = 0.0

    def calculate(self, position, slit):
        matrix = np.asarray(self.c['tracking_matrix_deg_per_pix'], dtype=float)
        error = pixel_offset(position, slit)
        residual = matrix @ error
        if not self.c.get('auto_gain_enabled', True):
            self.gains = np.array([self.c['gain_ra'], self.c['gain_dec']], dtype=float)
            self.crossings[:] = self.retreats[:] = 0
        elif self.previous is not None:
            previous_position, sent = self.previous
            before = matrix @ pixel_offset(previous_position, slit)
            # 混合行列でRA/Dec残差へ変換してから、各軸の通過と遠ざかりを判定。
            active = np.abs(sent) > 1e-9
            crossed = active & (before * residual < 0)
            away = active & ~crossed & (np.abs(residual) > np.abs(before) + 1e-9)
            self.crossings = np.where(crossed, self.crossings + 1, 0)
            self.retreats = np.where(away, self.retreats + 1, 0)
            self.gains[self.crossings >= 4] *= 0.8
            self.gains[self.retreats >= 4] *= 1.05
            self.crossings[self.crossings >= 4] = 0
            self.retreats[self.retreats >= 4] = 0
            self.gains = np.clip(self.gains, -self.c.get('max_gain_abs', 10.), self.c.get('max_gain_abs', 10.))
        self.previous = None
        self.last_distance_px = float(np.linalg.norm(error))
        self.last_needs_correction = bool(np.any(np.abs(error) > 10.))
        if not self.last_needs_correction:
            return error, np.zeros(2)
        # 行列は度/pixel、client_senderのguideは秒角。変換はここで一度だけ。
        command = residual * 3600. * self.gains
        if self.c['max_correction'] > 0:
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
    """UIは要求と状態参照のみ行い、専用workerが撮像・校正・送信を直列実行する。"""
    def __init__(self, config, camera_factory=None, sender=None):
        self.c = config
        self.camera_factory = camera_factory
        self.sender = sender
        self.commands = queue.Queue()
        self.stop_event = threading.Event()
        self.tracking_event = threading.Event()
        self.cooling_off_event = threading.Event()
        self.slit_request = threading.Event()
        self.source_request = threading.Event()
        self.calibration_request = threading.Event()
        self.lock = threading.Lock()
        self.data = dict(state='未接続', error='', frame=0, image=None,
                         connected=False, cooling=False, temperature=None,
                         imaging_state='待機中')
        self.pending_exposure_sec = None
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def snapshot(self):
        with self.lock:
            return self.data.copy()

    def detect_slit_position(self):
        self.slit_request.set()

    def calibrate_tracking(self):
        with self.lock:
            if self.data['state'] != '連続撮像中':
                return
            self.data.update(state='校正中', error='', calibration_ready=False)
            self.c.pop('tracking_matrix_deg_per_pix', None)
            self.calibration_request.set()

    def _calibrate_tracking(self, camera, send):
        """ループを中断し、基準snapとRA +60,-120、Dec +60,-120秒角後のsnapを取得。"""
        self.publish(calibration_points=[], calibration_point_frames=0)
        if not (self.c['simulation'] or self.c.get('mot_enabled', True)):
            raise ValueError('MoT送信が無効です')
        def capture(previous=None):
            if self.stop_event.is_set():
                raise RuntimeError('校正を中止しました')
            self._apply_pending_settings()
            image = camera.capture()
            self._save_image_safe(image)
            self.publish(image=image, frame=self.snapshot()['frame'] + 1)
            self.c['tracking_calibration_shape'] = image.shape
            sources = point_sources(image, self.c['threshold_sigma'], max_sources=5)
            if previous is None:
                rank = self.c['target_brightness_rank']
                if len(sources) < rank:
                    raise ValueError('校正用天体が見つかりません')
                chosen = sources[rank-1]
            else:
                candidates = [p for p in sources if np.linalg.norm(np.array([p['x'], p['y']])-previous) < self.c.get('calibration_max_jump_px', 120.)]
                if len(candidates) != 1:
                    raise ValueError('校正用天体を一意に対応付けできません。校正中止')
                chosen = candidates[0]
            target = np.array([chosen['x'], chosen['y']])
            self.publish(target=target.tolist(), sources=sources)
            return target
        before = capture()
        # 基準snapとの差ではなく、直前snapとの差を各相対命令に対応付ける。
        # 最終位置は基準からRA/Decとも-60秒角。復帰命令は送らない。
        moves = []
        points = []
        commands = np.array([[60., 0.], [-120., 0.], [0., 60.], [0., -120.]])
        for i, command in enumerate(commands):
            if self.stop_event.is_set():
                raise RuntimeError('校正を中止しました')
            self.publish(calibration_progress=f'{i+1}/4', imaging_state='校正移動中')
            response = send(*command)
            self.publish(sent_correction=command.tolist(), mot_response=response)
            if self.stop_event.wait(self.c.get('calibration_settle_sec', 3.)):
                raise RuntimeError('校正を中止しました（自動復帰送信なし）')
            after = capture(before)
            points.append(after.tolist())
            self.publish(calibration_points=list(points), calibration_point_frames=10)
            moves.append(after-before)
            before = after
        # commands: 秒角→度。moves = commands @ response.T を最小二乗で解く。
        # responseの行はX/Y、列はRA/Decで単位はpixel/度。
        response = np.linalg.lstsq(commands / 3600., np.asarray(moves), rcond=None)[0].T
        if not np.isfinite(response).all() or np.linalg.cond(response) > 100:
            raise ValueError('校正応答が不安定です。行列を採用しません')
        for axis in range(2):
            forward, backward = moves[axis*2:axis*2+2]
            # 負方向は移動角が2倍。単位角あたりの応答で往復を比較する。
            backward = backward / 2.
            if min(np.linalg.norm(forward), np.linalg.norm(backward)) < 1. or np.linalg.norm(forward+backward) > .5*max(np.linalg.norm(forward), np.linalg.norm(backward)):
                raise ValueError('往復移動量が不整合です。行列を採用しません')
        matrix = np.linalg.inv(response)
        # 逆行列の行はRA/Dec、列はX/Y、単位は度/pixel。
        # 実測した向き・混合を含むので、cos(Dec)や東西符号を追加で掛けない。
        self.c['tracking_matrix_deg_per_pix'] = matrix.tolist()
        self.c['gain_ra'] = self.c['gain_dec'] = 1.
        self.publish(calibration_ready=True, calibration_time=datetime.now().astimezone().isoformat(timespec='seconds'),
                     calibration_matrix=matrix.tolist(), calibration_progress='完了', gain_ra=1., gain_dec=1.)

    def detect_target_position(self):
        self.source_request.set()

    def _advance_calibration_points(self):
        """校正snapを含めず、再開したループの10枚目で点を消す。"""
        with self.lock:
            remaining = self.data.get('calibration_point_frames', 0)
            if remaining > 0:
                self.data['calibration_point_frames'] = remaining - 1
                if remaining == 1:
                    self.data['calibration_points'] = []

    def use_initial_slit(self):
        """保存値は明示的なボタン操作で適用。画像サイズが違えば拒否する。"""
        try:
            with self.lock:
                if self.tracking_event.is_set():
                    raise ValueError('自動追尾を停止してから初期値を使用してください')
                center, shape = validate_slit(self.c.get('slit_initial_center_px', []),
                                              self.c.get('slit_initial_image_shape', []))
                image = self.data.get('image')
                if image is not None and list(image.shape) != shape:
                    raise ValueError('初期値の画像サイズが現在画像と異なります。再検知してください')
                self.data.pop('slit_endpoints', None)
                self.data.update(slit=center, slit_shape=shape, slit_origin='保存済み初期値', error='')
        except Exception as exc:
            self.publish(error=str(exc))

    def _detect_requested(self):
        """スリット校正と単発天体検知は、撮像・送信とは独立した要求。"""
        if not (self.slit_request.is_set() or self.source_request.is_set()):
            return
        try:
            image = self.snapshot().get('image')
            if image is None:
                image = read_image(self.c['output_path'])
                self.publish(image=image)
            if self.slit_request.is_set():
                self.slit_request.clear()
                found = detect_illuminated_slit(image, self.c.get('slit_calibration_roi'))
                center, shape = validate_slit(found['center'], list(image.shape))
                save_slit(self.c['_config_path'], center, shape)
                self.c.update(slit_initial_center_px=center, slit_initial_image_shape=shape)
                self.publish(slit=found['center'].tolist(), slit_shape=list(image.shape),
                             slit_endpoints=found['endpoints'].tolist(), slit_origin='照明ON画像（初期値保存済み）', error='')
            if self.source_request.is_set():
                self.source_request.clear()
                self._detect_target(image)
        except Exception as exc:
            self.slit_request.clear()
            self.source_request.clear()
            self.publish(error=str(exc))

    def _detect_target(self, image):
        sources = point_sources(image, self.c['threshold_sigma'], max_sources=5)
        rank = self.c['target_brightness_rank']
        self.publish(sources=sources)
        if len(sources) < rank:
            with self.lock:
                self.data.pop('target', None)
            raise ValueError('指定順位の天体を検出できません。補正を保留します')
        chosen = sources[rank-1]
        target = np.array([chosen['x'], chosen['y']])
        self.publish(target=target.tolist(), error='')
        return target, sources

    def set_exposure(self, exposure_sec):
        """露光時間を次の撮像フレームから適用する。

        露光中のカメラ設定は変更せず、フレーム境界でworkerが反映する。
        """
        exposure_sec = float(exposure_sec)
        if not np.isfinite(exposure_sec) or exposure_sec <= 0:
            raise ValueError('露光時間は正の有限値を指定してください')
        with self.lock:
            limits = self.data.get('exposure_limits')
            if limits and not limits[0] <= exposure_sec <= limits[1]:
                self.data['exposure_error'] = f'露光時間は {limits[0]}〜{limits[1]} 秒で指定してください。適用値を維持します。'
                return
            self.data['exposure_error'] = ''
            self.pending_exposure_sec = exposure_sec

    def _apply_pending_settings(self):
        with self.lock:
            if self.pending_exposure_sec is not None:
                self.c['exposure_sec'] = self.pending_exposure_sec
                self.pending_exposure_sec = None

    def _publish_camera_status(self, camera):
        """接続中カメラの冷却スイッチと温度をUIへ反映する。"""
        try:
            cam = getattr(camera, 'camera', None)
            cooling = bool(getattr(cam, 'CoolerOn', False)) if cam is not None else False
            temperature = getattr(cam, 'CCDTemperature', None) if cam is not None else None
            self.publish(cooling=cooling, temperature=temperature)
        except Exception:
            # シミュレーションカメラや一部ASCOM実装では属性がないため、
            # 撮像処理自体を止めずに既存状態を維持する。
            return

    def _save_image_safe(self, image):
        try:
            save_image(self.c['output_path'], image, self.c['exposure_sec'])
            self.publish(save_error='')
        except (PermissionError, RuntimeError) as exc:
            # FITSビューア等が保存先を開いていても、撮像と補正は継続する。
            self.publish(save_error=str(exc))

    def cool_off(self):
        """UIでは要求のみ発行し、カメラ所有workerで実際にOFFにする。"""
        self.cooling_off_event.set()

    def _apply_cooling_off(self, camera):
        if camera is not None and self.cooling_off_event.is_set():
            if not self.c['simulation']:
                camera.camera.CoolerOn = False
            self.cooling_off_event.clear()
            self.publish(cooling=False)

    def publish(self, **values):
        with self.lock:
            self.data.update(values)

    def prepare(self):
        with self.lock:
            if self.data['state'] not in ('未接続', 'エラー'):
                return
            self.stop_event.clear()
            for key in ('target', 'sources', 'offset', 'correction', 'matrix'):
                self.data.pop(key, None)
            self.data['image'] = None
            self.data.update(state='冷却中', error='')
            self.commands.put('prepare')

    def connect(self):
        with self.lock:
            if self.data['state'] not in ('未接続', 'エラー'):
                return
            self.stop_event.clear()
            self.data['state'] = '接続中'
            self.commands.put('connect')

    def cool(self):
        with self.lock:
            if self.data['state'] not in ('準備完了', '追尾終了'):
                return
            self.stop_event.clear()
            self.data['state'] = '冷却中'
            self.commands.put('cool')

    def stop_tracking(self):
        # 撮像ループは継続し、次の送信直前にもこのフラグを確認する。
        self.tracking_event.clear()
        if self.snapshot()['state'] == '追尾中':
            self.publish(state='連続撮像中')

    def start(self):
        with self.lock:
            if 'tracking_matrix_deg_per_pix' not in self.c:
                self.data['error'] = '先に追尾用calibrationを実行してください'
                return
            if 'slit' not in self.data:
                self.data['error'] = '先にスリット位置検知を実行してください'
                return
            if self.data['state'] not in ('準備完了', '追尾終了', '連続撮像中'):
                return
            self.tracking_event.set()
            if self.data['state'] == '連続撮像中':
                self.data['state'] = '追尾中'
                return
            self.stop_event.clear()
            self.data['state'] = '追尾開始中'
            self.commands.put('start')

    def start_capture(self):
        with self.lock:
            if self.data['state'] not in ('準備完了', '追尾終了'):
                return
            self.stop_event.clear()
            self.tracking_event.clear()
            self.data['state'] = '連続撮像中'
            self.commands.put('start')

    def stop(self):
        self.calibration_request.clear()
        self.tracking_event.clear()
        with self.lock:
            self.stop_event.set()
            if self.data['state'] in ('追尾中', '追尾開始中'):
                self.data['state'] = '停止中'
    def disconnect(self):
        self.calibration_request.clear()
        self.tracking_event.clear()
        self.stop_event.set()
        self.commands.put('disconnect')

    def update_matrix(self, matrix):
        """Update the user-editable pixel-to-RA/Dec correction matrix."""
        matrix = np.asarray(matrix, dtype=float)
        if matrix.shape != (2, 2) or not np.isfinite(matrix).all():
            raise ValueError('補正係数は有限値の2×2行列で指定してください')
        if abs(np.linalg.det(matrix)) < 1e-9:
            raise ValueError('補正係数の行列は可逆である必要があります')
        with self.lock:
            self.c['matrix'] = matrix.tolist()
            self.data['matrix'] = matrix.tolist()

    def close(self):
        self.stop_event.set()
        self.commands.put('close')

    def _worker(self):
        camera = None
        ready = False
        pythoncom = None
        position_reader = None
        try:
            if not self.c['simulation'] and self.camera_factory is None:
                import pythoncom
                pythoncom.CoInitialize()
            while True:
                try:
                    action = self.commands.get(timeout=.5)
                except queue.Empty:
                    self._apply_cooling_off(camera)
                    self._detect_requested()
                    continue
                try:
                    if action in ('close', 'disconnect'):
                        if camera is not None:
                            camera.disconnect()
                        camera, ready = None, False
                        self.publish(state='未接続', connected=False, cooling=False,
                                     temperature=None, imaging_state='待機中')
                        if action == 'close':
                            return
                    elif action == 'cool' and camera is not None:
                        camera.prepare(self.stop_event)
                        self._publish_camera_status(camera)
                        self.publish(state='準備完了')
                    elif action in ('prepare', 'connect') and camera is None:
                        self.publish(state='接続中', error='')
                        if self.camera_factory:
                            camera = self.camera_factory(self.c)
                        elif self.c['simulation']:
                            camera = SimulationCamera(self.c)
                        else:
                            from .base__atik_camera_contloer import GuideCamera
                            camera = GuideCamera(self.c)
                            camera.cooling_off_event = self.cooling_off_event
                        camera.connect()
                        # ASCOMプロパティはカメラ所有workerだけで読む。
                        if not self.c['simulation'] and self.camera_factory is None:
                            try:
                                self.publish(exposure_limits=(float(camera.camera.ExposureMin), float(camera.camera.ExposureMax)))
                            except Exception:
                                pass  # 未対応ドライバでは正の有限値の検証を使用する。
                        self.publish(connected=True)
                        if action == 'prepare':
                            self.publish(state='冷却中')
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
                        self._publish_camera_status(camera)
                        self.publish(state='準備完了')
                    elif action == 'capture' and ready:
                        self.publish(state='連続撮像中', error='')
                        while not self.stop_event.is_set():
                            self._apply_pending_settings()
                            self._apply_cooling_off(camera)
                            self._publish_camera_status(camera)
                            self.publish(imaging_state='撮像中')
                            exposure_started = time.monotonic()
                            image = camera.capture()
                            self.publish(imaging_state='DL中')
                            self._save_image_safe(image)
                            self.publish(image=image, frame=self.snapshot()['frame'] + 1,
                                         imaging_state='待機中')
                            self.stop_event.wait(self.c['settle_sec'])
                        self.publish(state='追尾終了', imaging_state='待機中')
                    elif action == 'start' and ready:
                        self.publish(state='追尾中' if self.tracking_event.is_set() else '連続撮像中', error='')
                        correction = Correction(self.c)
                        target = None
                        move_until = 0.0
                        while not self.stop_event.is_set():
                            self._apply_pending_settings()
                            self._apply_cooling_off(camera)
                            self._publish_camera_status(camera)
                            self.publish(imaging_state='撮像中')
                            exposure_started = time.monotonic()
                            image = camera.capture()
                            self.publish(imaging_state='DL中')
                            self._save_image_safe(image)
                            self.publish(image=image, frame=self.snapshot()['frame'] + 1)
                            self._advance_calibration_points()
                            # An exposure already underway is saved; no new correction starts after stop.
                            if self.stop_event.is_set():
                                break
                            self._detect_requested()
                            if self.calibration_request.is_set():
                                # 同じworker内で校正を完了させるため、ループ撮像との重複はない。
                                self.calibration_request.clear()
                                try:
                                    self._calibrate_tracking(camera, send)
                                except Exception as exc:
                                    self.publish(error=f'校正失敗: {exc}', calibration_ready=False)
                                correction = Correction(self.c)
                                self.publish(state='連続撮像中', imaging_state='待機中')
                                continue
                            if not self.tracking_event.is_set():
                                correction.previous = None
                                target = None
                                self.publish(state='連続撮像中', imaging_state='待機中')
                                self.stop_event.wait(self.c['settle_sec'])
                                continue
                            # 移動待ち中に露光したフレームは補正計算に使わない。
                            if exposure_started < move_until:
                                self.publish(imaging_state='待機中')
                                self.stop_event.wait(self.c['settle_sec'])
                                continue
                            fixed = self.snapshot()
                            if tuple(fixed.get('slit_shape', ())) != image.shape:
                                self.tracking_event.clear()
                                self.publish(error='画像サイズが変わりました。スリット位置を再検知してください')
                                continue
                            if tuple(self.c.get('tracking_calibration_shape', ())) != image.shape:
                                self.tracking_event.clear()
                                self.publish(error='画像サイズが変わりました。追尾用calibrationを再実行してください')
                                continue
                            slit = np.asarray(fixed['slit'])
                            try:
                                target, sources = self._detect_target(image)
                            except ValueError as exc:
                                correction.previous = None
                                self.publish(error=str(exc), correction=[0., 0.], correction_needed=False)
                                self.stop_event.wait(self.c['settle_sec'])
                                continue
                            position = None
                            if not self.c['simulation'] and self.c.get('mot_enabled', True) and self.sender is None:
                                try:
                                    if position_reader is None:
                                        from .base__nishimura_controler import NishimuraController
                                        position_reader = NishimuraController()
                                    position = position_reader.read_position()
                                    self.c['declination_deg'] = position['dec_j2000_deg']
                                    for key in ('azimuth_deg', 'az_deg', 'azimuth_j2000_deg'):
                                        if key in position and position[key] is not None:
                                            self.c['azimuth_deg'] = float(position[key]) % 360.0
                                            break
                                except Exception as exc:
                                    self.tracking_event.clear()
                                    self.publish(error=f'MoT座標取得失敗・追尾停止: {exc}')
                                    continue
                            error, command = correction.calculate(target, slit)
                            if (self.tracking_event.is_set() and not self.stop_event.is_set()
                                    and np.any(command) and (self.c['simulation'] or self.c.get('mot_enabled', True))):
                                try:
                                    # 自動追尾は現在座標への絶対trackではなく、
                                    # client_senderの相対guideを使用する。
                                    response = send(float(command[0]), float(command[1]))
                                    self.publish(sent_correction=command.tolist(), mot_response=response,
                                                 sent_correction_unit='arcsec', sent_command='guide')
                                    move_until = time.monotonic() + 3.0
                                except Exception as exc:
                                    self.tracking_event.clear()
                                    self.publish(error=f'送信結果不明・追尾停止（再送なし）: {exc}')
                                    continue
                                # 次回は各軸の残差を比較してgainを更新する。
                                correction.previous = (target.copy(), command.copy())
                            self.publish(target=target.tolist(), sources=sources, offset=error.tolist(),
                                         correction=command.tolist(), correction_needed=correction.last_needs_correction,
                                         correction_distance_px=correction.last_distance_px,
                                         gain=correction.gains.tolist(),
                                         gain_ra=float(correction.gains[0]),
                                         gain_dec=float(correction.gains[1]),
                                         calibration_matrix=self.c['tracking_matrix_deg_per_pix'])
                            self.publish(imaging_state='待機中')
                            self.stop_event.wait(self.c['settle_sec'])
                        self.publish(state='追尾終了', imaging_state='待機中')
                except Exception as exc:
                    ready = False
                    if camera is not None:
                        try:
                            camera.disconnect()
                        except Exception as cleanup:
                            self.publish(error=f'{exc}; 切断失敗: {cleanup}', state='エラー')
                            continue
                    camera = None
                    self.publish(state='エラー', error=str(exc), imaging_state='待機中', cooling=False)
        except Exception as exc:
            self.publish(state='エラー', error=str(exc), imaging_state='待機中', cooling=False)
        finally:
            if position_reader is not None:
                position_reader.close()
            if pythoncom is not None:
                pythoncom.CoUninitialize()
