# ハードを使わないpixelズレ検証

`pixel_offset_nearby_slit.ipynb` は全8コードセルを実行済みです。
`src.base__fits_utils`、`src.base__point_detector` を直接使用しています。
カメラの接続・露光・MoT送信は行いません。

## 設定

プロジェクトの `.config` を参照します。

```toml
pixel_test_image_path = 'pictures/02_slit_guide_images/test_sigmagem_nearby_slit.fit'
pixel_test_slit_mode = 'science'
pixel_test_slit_roi = [880, 250, 1130, 850]
```

`science` は星像画像1枚からスリットと星の両方を検出し、`test_00.fits` を読みません。
ROIはスリット全体を含み、他の暗い構造を除外する範囲です。
別画像を試す場合はファイル名とROIを設定してください。

`reference` に変更すると `flat_path`（現在 `test_00.fits`）と `slit_roi` を使う2画像方式です。
実ファイルの拡張子は `test_00.fit` ではなく `test_00.fits` です。
この設定切替はオフラインノートブック用です。追尾アプリも `guide_slit_mode = 'science'`、
`guide_slit_roi` によって同じ検出処理を毎フレーム実行します。

## uvで再実行

`observation` フォルダで実行します。

```powershell
uv sync --group notebook
uv run --group notebook python scat_observation/scat_guide_tracking_system/test_all/run_pixel_notebook.py
uv run python -m unittest discover -s scat_observation/scat_guide_tracking_system/test_all -p test_pixel_analysis.py -v
```

エディタで開く場合は `observation/.venv/Scripts/python.exe` をカーネルとして選択します。

## 今回の結果（scienceモード）

座標は0始まりの(x,y)。ズレはスリット中心−星中心です。

| 項目 | x [pixel] | y [pixel] |
|---|---:|---:|
| 推定スリット中心 | 1007.114 | 564.276 |
| 点源重心 | 994.712 | 538.253 |
| pixelズレ | +12.401 | +26.023 |

中心間距離は28.827 pixel、スリット軸までの垂直距離は18.390 pixelです。

星によって途切れた暗いスリットを直線で結び、検出端点の中点を中心としています。
参照画像方式の二値マスク重心とは中心の定義が異なります。
今回の画像には65535 ADU以上の画素が31個あり、星は飽和しています。
閾値を2.0/2.5/3.0に変えたときの中心位置の変動幅はx=1.377、y=1.721 pixelでした。
これはパラメーター感度であり、真の位置に対する誤差範囲ではありません。

結果画像とJSONは `pixel_offset_results/` に保存します。元のFITSは変更しません。
スリットの大部分が星で隠れる画像や、端点がROIの外に出る画像では正確に推定できません。

## 検証範囲

画像テスト4件が成功：既知の位置に置いたスリットと重なる模擬星像、実際の星像画像、
照明勾配を含む参照画像、スリットがない画像でのエラーを確認しています。
実機の動作・校正は検証していません。
