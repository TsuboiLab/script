# SCAT ガイド追尾システム

自動追尾アプリの現行実装・uvでの起動方法は [README_auto_guide.md](README_auto_guide.md) を参照してください。以下は従来の試作コード・ノートブックの説明です。

Atik 314L+ をスリットガイドカメラとして用い、撮像した FITS 画像からスリット位置を推定し、赤道儀による追尾補助につなげるための試作プロジェクトです。

現時点では、カメラ制御は `src/atik_camera.py`、画像解析の試作は `auto_guide.ipynb` に分かれています。ノートブック内の「光源検出」「赤経・赤緯への変換」「追尾情報の送信」は未実装のため、運用前に実機での検証と実装の補完が必要です。

## 構成

```text
scat_guide_tracking_system/
├─ auto_guide.ipynb          # FITS画像を用いたスリット位置検出の試作
├─ src/
│  ├─ atik_camera.py         # Atik 314L+ の ASCOM 制御と FITS 保存
│  └─ fits_utils.py          # FITS ユーティリティ用の予約ファイル（現在は空）
├─ pictures/                 # 画像・FITS の保存場所
│  ├─ 01_spectroscopic_images/
│  ├─ 02_slit_guide_camera/
│  ├─ 02_slit_guide_images/
│  ├─ 03_wide_range_images/
│  └─ 99_temporal_images/
├─ test_notebook/            # Atik カメラ撮像の検証用ノートブック・依存関係
└─ test_all/                 # 追尾処理の初期検証ノートブック
```

## 必要環境

- Windows 10 / 11
- Python 3.11 系（`test_notebook/requirements_atik314.txt` では 3.11.9 を推奨）
- Atik 314L+ のドライバおよび ASCOM Platform
- ASCOM の ProgID `ASCOM.AtikCameras.Camera` が利用可能であること

カメラ制御に必要な最小限のパッケージは次で導入できます。

```powershell
python -m pip install -r test_notebook/requirements_atik314.txt
```

`auto_guide.ipynb` の実行には、上記に加えて `jupyter`、`pandas`、`polars`、`matplotlib`、`plotly`、`scipy`、`scikit-image`、`scikit-learn` が必要です。

```powershell
python -m pip install jupyter pandas polars matplotlib plotly scipy scikit-image scikit-learn
```

## `src/atik_camera.py` の利用方法

`AtikCamera` は ASCOM 経由での接続、冷却、露光、画像取得、FITS 保存をまとめたクラスです。`with` 構文を使うと、例外が起きても接続を切断できます。

プロジェクトのルートディレクトリで、次のように実行します。

```python
from src.atik_camera import AtikCamera

exposure_sec = 1.0

with AtikCamera() as camera:
    # 必要な場合だけ実行: 目標温度の ±1 ℃ に到達するまで待機する
    camera.cool_to(-5.0)

    # ライトフレームを露光し、NumPy の2次元配列として取得する
    image = camera.capture(exposure_sec)

    # FITS として保存する。保存しない場合は enabled=False を指定する
    saved_path = camera.save_fits(
        image,
        exptime_sec=exposure_sec,
        output_dir="pictures/02_slit_guide_camera",
        filename_base="guide_001",
    )
    print(saved_path)
```

主なメソッドは以下です。

| メソッド | 用途 |
| --- | --- |
| `connect()` / `disconnect()` | カメラへの接続・切断 |
| `set_ccd_temperature(℃)` | 冷却を開始して目標 CCD 温度を設定 |
| `wait_for_temperature(℃)` | 目標温度の ±1 ℃ に入るまで待機（30 秒間隔で状態表示） |
| `cool_to(℃)` | 温度設定と到達待機を連続実行 |
| `capture(秒)` | ライトフレームを露光し、画像配列を返す |
| `save_fits(...)` | FITS を保存。`EXPTIME`、`CCD-TEMP`、`DATE-OBS`、`INSTRUME` をヘッダーに記録 |

`save_fits()` のデフォルトの保存先は `pictures/02_slit_guide_camera` です。既存ファイルを上書きしたくない場合は、ユニークな `filename_base` を指定するか、`overwrite=False` を指定してください。

> 実機を接続して露光・冷却を行うコードです。望遠鏡・カメラの状態、安全な温度設定、保存先の空き容量を確認してから実行してください。

## `pictures` フォルダ

観測画像と検証データを用途別に置くフォルダです。

| フォルダ | 用途 |
| --- | --- |
| `01_spectroscopic_images/` | 分光観測画像 |
| `02_slit_guide_camera/` | `AtikCamera.save_fits()` の標準保存先。ガイドカメラの撮像結果 |
| `02_slit_guide_images/` | スリット位置検出に使うガイド画像。`auto_guide.ipynb` はここを参照 |
| `03_wide_range_images/` | 広視野画像 |
| `99_temporal_images/` | 一時データ |

解析用の FITS を追加する場合は、ノートブックで指定するファイル名と保存先を一致させてください。観測データは容量が大きくなりやすいため、長期保管・共有の方針も別途決めることを推奨します。

## `auto_guide.ipynb` の解説

このノートブックは、スリットガイド画像からスリットの中心位置を求める処理を検証するためのものです。カメラを直接操作せず、FITS ファイルを読み込んで解析します。

実行はプロジェクトのルートをカレントディレクトリにしてから行います。

```powershell
jupyter notebook auto_guide.ipynb
```

主な処理の流れは次のとおりです。

1. `pictures/02_slit_guide_images/test_01.fits` を対象画像として指定する。
2. FITS の主 HDU から画像データを 2 次元配列として読み込む。
3. カラーマップを表示して画像を確認する。
4. ガウシアン平滑化画像との差分から暗い構造を抽出する。
5. 連結成分のうち長軸長が 2 番目に大きい領域をスリットとみなし、その重心をスリット中心として可視化する。

別の画像を解析する場合は、最初に以下のセルを編集します。

```python
latest_image_path = slit_guide_images_path / "test_01.fits"
```

この検出ロジックは「スリットが画像内で 2 番目に長い暗領域である」という仮定に基づきます。視野内の暗い構造、飽和、ノイズの状態によっては誤検出するため、必ず表示結果を確認してください。

ノートブック後半の以下の章は見出しのみで、処理はまだ実装されていません。

- 光源位置の特定
- 光源とスリット中心との距離計算
- ピクセル距離から赤経・赤緯への変換
- 固定した赤経・赤緯情報の JSON 送信

## 関連する検証用ファイル

- `test_notebook/test_capture_atik314.ipynb`: Atik 314L+ の撮像を確認するためのノートブック
- `test_notebook/readme_test_capture_atik314.md`: カメラ制御の仕様メモ
- `test_all/test_tracking.ipynb`: 追尾処理を試行した初期ノートブック
