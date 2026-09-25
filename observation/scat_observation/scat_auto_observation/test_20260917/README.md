# Master2018 制御CLI（試作・2026-09-17）

Python標準ライブラリのみで実装。位置取得は64ビットWindows＋64ビットPythonが必要。
実機との接続試験は未実施。調査根拠は一つ上の `nishimura_cli_investigation.md`。

## ファイル

- `nishimura_cli.py`：起動、TCP制御要求、位置取得のCLI。
- `gui_bridge.py`：MasterのGUIボタンを一意に照合し、Windows `BM_CLICK`でOnClickを呼ぶ。
- `master_position.py`：読み取り専用の位置取得。新規プログラムからもimport可能。
- `test_cli.py`：実機へ接続しないモック試験。

## 準備

PowerShellで次を設定する。このPCで確認済みのPythonを使う例。
別の64ビットPythonを利用する場合は `$pythonExe` を変更する。

```powershell
Set-Location 'C:\Users\domepc6-tsuboi\work\observation\scat_observation\scat_auto_observation\test_20260917'
$pythonExe = 'C:\Users\domepc6-tsuboi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $pythonExe .\nishimura_cli.py --help
```

## 起動

```powershell
# 計画表示だけ。ソフトは起動しない。
& $pythonExe .\nishimura_cli.py start

# 実際にGUIを起動する。EXEのハッシュを照合し、同名プロセスの二重起動を避ける。
& $pythonExe .\nishimura_cli.py start --execute
```

本体が別の場所にある場合は `--exe '絶対パス\Master2018.exe'` を指定できる。
解析対象と異なるハッシュのEXEは実行・送信を拒否する。
起動後にログイン操作や初期化画面が必要かは実機側で確認する。
CLIが起動できたことは制御装置が観測可能になったことを意味しない。

## Ra/Dec導入

```powershell
# 以下の座標は例。現在の観測対象としての推奨ではない。
# J2000、RA=12h30m、Dec=+30度。既定では送信内容を表示するだけ。
& $pythonExe .\nishimura_cli.py track --ra-hours 12.5 --dec-deg 30.0

# 現地で運転条件と目標座標を確認してから実行する。
& $pythonExe .\nishimura_cli.py track --ra-hours 12.5 --dec-deg 30.0 --execute

# 停止要求。物理非常停止の代替ではない。
& $pythonExe .\nishimura_cli.py stop --execute
```

RAは0以上24未満の十進時間、Decは-90以上90以下の十進度。
数値はJSONの浮動小数点数として送る。固有運動は単位未確定のため0.0に固定。
`guide` はオフセット規約の追加確認が必要なため、このCLIには公開していない。

接続先は同一PCの127.0.0.1:8744。送信前に待受の所有プロセスを確認する。
EXEハッシュ照合だけでは接続先プロセスの同一性までは証明しない。

```powershell
Get-Process -Name Master2018 | Select-Object Id,ProcessName
Get-NetTCPConnection -State Listen -LocalPort 8744 |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

`tcp_write_completed=true` は送信完了だけ。受理・導入完了は `unconfirmed` と出力する。
既存受信側のTCP分割処理は不十分なので、送信成功だけで動作成功と判定しない。
通信エラーやタイムアウトで自動再送せず、Masterの画面・装置状態を確認する。
`--timeout 3.0` は接続・送信待ち時間であり、鏡筒の移動待ち時間ではない。

## 観測開始・終了処理

```powershell
& $pythonExe .\nishimura_cli.py startup
& $pythonExe .\nishimura_cli.py ending
```

この例は計画表示のみ。`--execute` で既存Masterの処理を呼ぶ。
`startup` はEXEを起動する機能ではない。
`ending` は設定に応じてホーム移動やスリット閉等の終了処理を伴い得る。
単なるソケット切断やPythonの終了のためには送らない。

## ドーム連動・スリット（GUI OnClick経由）

```powershell
& $pythonExe .\nishimura_cli.py dome-link on --pid $masterPid
& $pythonExe .\nishimura_cli.py slit open --pid $masterPid
```

既定では対象ボタンの操作計画だけを表示します。実際にOnClickを呼ぶときは `--execute` を付けます。

```powershell
& $pythonExe .\nishimura_cli.py dome-link on --pid $masterPid --execute
& $pythonExe .\nishimura_cli.py slit open --pid $masterPid --execute
```

処理経路は `PID → 子ウィンドウ列挙 → class_name (TButton/Button) と表示文字列を一意照合 → BM_CLICK → MasterのOnClick` です。
EXE内で確認したコンポーネント名は `ButtonDomRotAutoOn/Off`、`ButtonDomSltOpen/Close/Stop` です。
候補が0件または複数件ならクリックせず停止します。

`BM_CLICK`の処理完了は、ドームやスリットの機械動作完了を意味しません。
クリック後は `position` の `raw.DomRotAutoFlag` / `raw.DomSlSt` とGUI表示・装置状態を確認してください。
スリット状態コードの意味は未確定です。`DSO#`を8744番へ送ったり、Masterと同時にCOMポートを開いたりしません。

## 現在位置

```powershell
$masterProcesses = @(Get-Process -Name Master2018 -ErrorAction Stop)
if ($masterProcesses.Count -ne 1) { throw '対象PIDを一つに特定してください' }
$masterPid = $masterProcesses[0].Id

# 1回だけ表示。
& $pythonExe .\nishimura_cli.py position --pid $masterPid --once

# 0.5秒おきにJSON Linesを出力。Ctrl+Cで終了。
& $pythonExe .\nishimura_cli.py position --pid $masterPid --interval 0.5
```

`ra_j2000_hours` / `dec_j2000_deg` / `azimuth_software_deg` / `altitude_software_deg` を使う。
`raw`には内部変数名のまま座標と状態コードを収める。
方位原点・状態コードの意味は実画面と照合するまで決めつけない。
`sampled_at_utc`はメモリを読んだ時刻。装置からの更新時刻ではない。
通信断でも古い値が読めるため、`controller_data_freshness`は常に`unknown`。
複数の値の厳密な同時刻性も保証しない。この試作だけで無人運転の安全判定をしない。

新規プログラムで使う場合：

```python
from master_position import Reader

# このファイルとmaster_position.pyを同じフォルダに置く例。
# master_pidには実際のMaster2018のプロセスIDを渡す。
with Reader(master_pid) as reader:
    sample = reader.read_once()
    print(sample['ra_j2000_hours'], sample['dec_j2000_deg'])
```

## 実機を使わない試験

```powershell
& $pythonExe -m unittest discover -s . -p 'test_cli.py' -v
```

通信・起動はモックに置換。座標範囲、JSON実数、既定で送信しないこと、
失敗時に再送しないこと、未対応操作の拒否、位置復号を検証する。
この試験の成功は、実機で導入・追尾・ドーム動作を検証したことを意味しない。

終了コード：0=計画表示／送信／読み取りの処理終了、1=実行エラー、2=引数エラーまたは未対応、130=Ctrl+C。
本体側のエラーや動作完了を0から推定しない。
