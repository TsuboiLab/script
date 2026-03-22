# Atik 314L+ カメラ制御システム 仕様書

## 1. プロジェクト概要
Windows環境において、Pythonから冷却CCDカメラ「Atik 314L+」を制御する。
ASCOMインターフェースを介し、冷却管理、露光制御、および撮像データのFITS形式保存を自動化する。

## 2. 実行環境
- **OS:** Windows 10 / 11
- **Python:** 3.11.9
- **接続方式:** ASCOM Platform 経由
- **確定済ProgID:** `ASCOM.AtikCameras.Camera`
- **主要ライブラリ:**
    - `win32com.client` (pywin32): ASCOM COMオブジェクト操作用
    - `astropy`: FITSファイル作成・ヘッダー編集用
    - `numpy`: 画像配列処理用
    - `time`: ポーリングおよび待機用

## 3. 技術的仕様・制約

### 3.1 デバイス特性 (Atik 314L+)
- **センサー:** Sony ICX285AL (モノクロ)
- **解像度:** 1391 x 1039
- **シャッター:** 電子シャッター（物理シャッターなし）
    - ※重要: ダークフレーム撮影時は、ユーザーにレンズキャップの装着を促すメッセージを表示すること。

### 3.2 冷却制御ロジック
- `SetCCDTemperature` プロパティで目標温度を設定。
- `CoolerOn = True` で冷却を開始。
- 冷却中は `CCDTemperature` を監視し、目標温度の ±0.5℃ 以内に収まるまで待機する。
- 待機中は5秒おきに現在の温度と冷却パワー（`CoolerPower`）をコンソールにログ出力する。

### 3.3 露光・データ取得ロジック
- `StartExposure(Duration, IsLight)` メソッドを使用する。
- 露光中は `ImageReady` プロパティをループで監視（ポーリング）し、`True` になるまで待機する。
- `ImageArray` を取得した後、`np.array()` でNumPy配列に変換する。
    - ※注意: 配列の次元（縦横）が反転している場合は、`.T` で転置処理を行う。

## 4. 機能要件 (Functional Requirements)

- **[接続]** `ASCOM.AtikCameras.Camera` への確実な接続と、終了時の安全な切断。
- **[冷却]** 目標温度への到達待ち機能（ブロッキング処理）。
- **[撮像]** 指定秒数の露光と、ステータス（露光中/読み出し中）の表示。
- **[保存]** `astropy.io.fits` を使用したFITS保存。
    - 保存先: `outputs/` フォルダ（自動生成すること）
    - ファイル名: `Atik314L_YYYYMMDD_HHMMSS.fits`
    - ヘッダー: `EXPTIME`, `CCD-TEMP`, `DATE-OBS`, `INSTRUME` を記録。

## 5. 推奨コード構造
- `AtikCamera` クラスとしてカプセル化する。
- メイン処理（`main.py`）では、コンストラクタでカメラを初期化し、`with` 構文や `try-finally` で確実に切断を保証する。