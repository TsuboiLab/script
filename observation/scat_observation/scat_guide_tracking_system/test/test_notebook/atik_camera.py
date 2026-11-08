# -*- coding: utf-8 -*-
"""
Atik 314L+ カメラ制御モジュール
ASCOM 経由で冷却・露光・FITS保存を提供する AtikCamera クラス。
"""

import os
import time
from datetime import datetime
from typing import Optional

import numpy as np
import win32com.client
from astropy.io import fits


# ProgID
ASCOM_PROG_ID = "ASCOM.AtikCameras.Camera"

# 冷却安定判定: 目標温度 ± この値(℃) 以内
TEMPERATURE_TOLERANCE_C = 1.0
# 冷却監視のポーリング間隔（秒）
COOLING_POLL_INTERVAL = 30


class AtikCamera:
    """Atik 314L+ を ASCOM 経由で制御するクラス。"""

    def __init__(self, prog_id: str = ASCOM_PROG_ID):
        self._prog_id = prog_id
        self._cam = None
        self._connected = False

    def connect(self) -> None:
        """ASCOM カメラに接続する"""
        if self._connected:
            return
        self._cam = win32com.client.Dispatch(self._prog_id)
        self._cam.Connected = True
        if not self._cam.Connected:
            raise RuntimeError(f"接続に失敗しました: {self._prog_id}")
        self._connected = True

    def disconnect(self) -> None:
        """接続を安全に切断する"""
        if not self._connected or self._cam is None:
            return
        try:
            self._cam.Connected = False
        except Exception:
            pass
        self._cam = None
        self._connected = False

    def __enter__(self) -> "AtikCamera":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
        return None

    @property
    def camera(self):
        """内部の ASCOM カメラオブジェクト（必要時のみ使用）。"""
        if not self._connected or self._cam is None:
            raise RuntimeError("カメラが接続されていません。")
        return self._cam

    # --- 冷却制御 ---

    def set_ccd_temperature(self, target_celsius: float) -> None:
        """目標CCD温度を設定し、冷却を開始する。"""
        self.camera.SetCCDTemperature = target_celsius
        self.camera.CoolerOn = True

    def wait_for_temperature(self, target_celsius: float) -> None:
        """
        目標温度 ±0.5℃ になるまでブロッキングで待機する。
        5秒ごとに現在温度と冷却パワーをコンソールに出力する。
        """
        cam = self.camera
        low = target_celsius - TEMPERATURE_TOLERANCE_C
        high = target_celsius + TEMPERATURE_TOLERANCE_C
        while True:
            t = float(cam.CCDTemperature)
            p = float(cam.CoolerPower)
            print(f"  CCD温度: {t:.2f} ℃, 冷却パワー: {p:.1f} %")
            if low <= t <= high:
                print(f"  目標温度 {target_celsius} ℃ 付近に到達しました。")
                return
            time.sleep(COOLING_POLL_INTERVAL)

    def cool_to(self, target_celsius: float) -> None:
        """目標温度を設定し、到達するまで待機する（冷却の一連処理）。"""
        self.set_ccd_temperature(target_celsius)
        self.wait_for_temperature(target_celsius)

    # --- 露光・データ取得 ---

    def start_exposure(self, duration_sec: float, is_light: bool = True) -> None:
        """
        露光を開始する。
        is_light: True でライトフレーム、False でダークフレーム
            カバーがないので現状ライトフレーム撮像のみ対応
        """
        self.camera.StartExposure(duration_sec, is_light)

    def wait_exposure_ready(self) -> None:
        """ImageReady が True になるまでポーリングで待機し、露光/読み出し状態を表示する。"""
        cam = self.camera
        while True:
            if cam.ImageReady:
                return
            # ASCOM では CameraState で状態を取得できる場合がある
            try:
                state = getattr(cam, "CameraState", None)
                if state is not None:
                    states = {0: "Idle", 1: "Waiting", 2: "Exposing", 3: "Reading"}
                    msg = states.get(int(state), str(state))
                else:
                    msg = "露光中/読み出し中"
            except Exception:
                msg = "露光中/読み出し中"
            print(f"  ステータス: {msg}")
            time.sleep(0.5)

    def get_image_array(self) -> np.ndarray:
        """
        露光完了後の ImageArray を取得し、NumPy配列で返す。
        縦横が反転している場合は転置 (.T) して返す。
        """
        cam = self.camera
        arr = np.array(cam.ImageArray)
        # 仕様: 配列の次元が反転している場合は .T で転置
        if arr.ndim == 2 and cam.CameraXSize == arr.shape[1] and cam.CameraYSize == arr.shape[0]:
            pass  # そのまま (X=列, Y=行 なら XSize, YSize と一致)
        elif arr.ndim == 2 and cam.CameraXSize == arr.shape[0] and cam.CameraYSize == arr.shape[1]:
            arr = arr.T
        return arr

    def capture(
        self,
        duration_sec: float,
    ) -> np.ndarray:
        """
        指定秒数の露光を行い、完了まで待機して画像配列を返す。
        """
        self.start_exposure(duration_sec)
        self.wait_exposure_ready()
        return self.get_image_array()

    # --- FITS 保存 ---

    def save_fits(
        self,
        image: np.ndarray,
        exptime_sec: float,
        output_dir: str = "pictures/02_slit_guide_camera",
        filename_base: Optional[str] = None,
        enabled: bool = True,
        overwrite: bool = True,
    ) -> Optional[str]:
        """
        FITS の保存可否を選択できる保存関数。

        - enabled=False の場合: 保存せず None を返す
        - enabled=True の場合: FITS 保存してパスを返す

        保存先: output_dir/<filename_base or Atik314L_YYYYMMDD_HHMMSS>.fits
        ヘッダー: EXPTIME, CCD-TEMP, DATE-OBS, INSTRUME を記録
        """
        if not enabled:
            return None

        os.makedirs(output_dir, exist_ok=True)
        if filename_base is None or str(filename_base).strip() == "":
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename_base = f"Atik314L_{timestamp}"
        filename = f"{filename_base}.fits"
        filepath = os.path.join(output_dir, filename)

        ccd_temp = float(self.camera.CCDTemperature)
        date_obs = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        instrume = str(getattr(self.camera, "Name", "Atik 314L+"))

        hdu = fits.PrimaryHDU(image)
        hdu.header["EXPTIME"] = (exptime_sec, "Exposure time (sec)")
        hdu.header["CCD-TEMP"] = (ccd_temp, "CCD temperature (C)")
        hdu.header["DATE-OBS"] = (date_obs, "Observation start (UTC)")
        hdu.header["INSTRUME"] = (instrume, "Instrument name")
        hdu.writeto(filepath, overwrite=overwrite)
        return filepath
