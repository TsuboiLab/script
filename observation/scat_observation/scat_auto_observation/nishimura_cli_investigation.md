# 西村望遠鏡 Master2018：CLI化調査と実施手順

調査日：2026-09-17。指定フォルダ内のEXE・INI・操作ログ・SocketDebuggerのサンプルを静的解析した結果。実機へのコマンド送信、アプリ起動、鏡筒・ドームの操作は実施していない。

## 結論

| 要求 | このバージョンで確認できた方法 | 実機検証 |
|---|---|---|
| Ra/Dec指定 | TCP 8744へJSONのtrack命令 | 未実施 |
| 鏡筒とドームの連動 | GUIのドーム連動ON。専用JSON命令は存在しない | 未実施 |
| スリット開 | GUIのスリット開。制御装置への送信ログにDSO# | 未実施 |
| 現在位置取得 | 添付の読み取り専用プロセスメモリ取得CLI。既存JSONのstatusは座標を含まない | デコーダと誤EXE拒否を検証。実機値照合は未実施 |
| ソフト起動 | PowerShellのStart-Process。作業ディレクトリをMasterに指定 | 調査では起動していない |

既存ソフトにはTCPの外部操作口があるが、5項目すべてをカバーする正式CLIは確認できない。短期的には「Masterを唯一の制御装置接続元とする」「trackをTCPで送る」「ドーム操作はGUI操作ブリッジ」「位置は読み取り専用取得」の構成。無人運転の常用には、メーカー提供APIまたはソース改修でドーム操作と時刻付き位置取得を追加するのが適切。

## 1. 対象

- 本体：C:\Users\domepc6-tsuboi\Documents\nishimura\Master\Master2018.exe
- タイトル設定：Master of Telescope 2018.01EQ
- 同じフォルダにMaster2018_0207.exeも存在するが、本書の解析対象ではない。
- 本体SHA256：7A4D5966D313D615DFCA9980A9FDECE18928E92A1CDF683E904F5C8F0E5CC003
- AtikCamerasSDKはカメラ用。鏡筒・ドームの制御仕様とは分けて扱う。
- 起動中のMasterプロセスは調査時に見つからなかった。

設定にComPort = 3 8がある。2値の意味と通信速度・パリティ等を確定せず、COM3と決めつけて開かない。DomCont=2、SltCont=1、DomRadius=1.25、DecLength=0.46、SltLimTime=95という値もあるが、特に95を「開完了まで必ず95秒」と解釈しない。

## 2. ソフトをCLIから起動

PowerShell：

```powershell
$masterDir = 'C:\Users\domepc6-tsuboi\Documents\nishimura\Master'
if (-not (Get-Process -Name Master2018 -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath "$masterDir\Master2018.exe" -WorkingDirectory $masterDir
}
```

GUIアプリの起動であり、ヘッドレス化ではない。INIとdata配下に相対パスがあるためWorkingDirectoryを指定する。通常の観測用Windowsログオンセッションで実行する。起動直後の初期化は実機に影響し得る。既存ログにもPROGRAM START後のCOMオープンと送信がある。

起動後、待受の確認だけを行う例：

```powershell
$masterProcess = Get-Process -Name Master2018 -ErrorAction Stop
Get-NetTCPConnection -State Listen -LocalPort 8744 |
    Select-Object LocalAddress,LocalPort,OwningProcess
$masterProcess | Select-Object Id,ProcessName
```

OwningProcessが本体と一致することを確認する。解析したserverInitはINADDR_ANY:8744で待受する。HTTPサーバーではないためcurlのHTTPリクエストは使わない。観測制御用ネットワーク内にアクセスを限定する設計が必要。

注意：JSONのstartupは「このEXEを起動する命令」ではない。既に起動しているMasterの起動処理を呼ぶ。endingも観測終了処理を呼ぶため、単なる接続終了として送らない。

## 3. Ra/Dec指定で鏡筒を制御

受信側の命令表はtrack / guide / stop / startup / endingの5種類。trackはRa/Decを目標座標へ設定し、J2000→装置座標→水平座標の変換へ渡す。

送信例（任意の例示座標であり、今観測すべき天体の提案ではない）：

```json
{"command":"track","ra":12.5,"dec":30.0,"pmra":0.0,"pmdec":0.0}
```

- ra：J2000赤経、十進時間。12h30m = 12.5。角度187.5度をそのまま入れない。
- dec：J2000赤緯、十進度。南天は負数。
- pmra / pmdec：固有運動用。単位・規約は今回確定していないため、まず0.0として固有運動補正を使わない。
- 数値は12や30ではなく12.0、30.0のように小数点を含める。受信実装はjson_real_valueを使い、JSON整数を一般の数値として取り出す実装ではない。
- ra / dec / pmra / pmdecは毎回すべて指定する。省略値が過去の要求から残る可能性がある。
- nameは任意項目だが、今回の最小例には含めない。

送信用の最小PowerShell例。これは実行すると鏡筒の動作要求を送る。現地で座標と運転状態を確認したうえで使用する。

```powershell
$payload = '{"command":"track","ra":12.5,"dec":30.0,"pmra":0.0,"pmdec":0.0}'
$bytes = [Text.Encoding]::UTF8.GetBytes($payload)
$client = [Net.Sockets.TcpClient]::new()
try {
    $client.Connect('127.0.0.1', 8744)
    $stream = $client.GetStream()
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush()
    # ここでは送信しただけ。導入完了の意味ではない。
} finally {
    $client.Dispose()
}
```

要求側は生のJSON文字列を受ける。#、HTTPヘッダー、独自8バイトヘッダーを足さない。送信例は実機未検証。受信処理は1回のrecv（最大1024バイト）をそのままJSON解析へ渡しており、TCP分割への堅牢な組み立ては確認できない。短い要求を1接続1要求として送り、タイムアウトを理由に無条件再送しない。常用の自動観測では受信処理の改修が望ましい。

停止命令の形式は{"command":"stop"}。ただし追尾停止と物理的な緊急停止を同一視しない。

## 4. 鏡筒とドームをリンク

専用のJSON命令dome-link等は見つからない。GUIのドーム連動ONのハンドラーButtonDomRotAutoOnClickがDomRotAutoFlagを1に設定する。OFFはButtonDomRotAutoOffClick。CalDomAutoDirがあり、ドーム半径・鏡筒側の幾何を使う処理もあるため、単純に「鏡筒の方位角をドームへコピー」で代用しない。

現状でCLIから実現する場合の手順：

1. Masterのドーム連動ONボタンを対象にするWindows UI Automationブリッジを作る。
2. そのブリッジをCLIコマンドとして呼ぶ。ボタンのAutomationId/ハンドル/親ウィンドウは起動後の実画面から特定し、同名ボタンの誤選択を避ける。
3. 添付の位置CLIでraw.DomRotAutoFlagが1になったことを確認する。
4. raw.DomRotDirやドームの状態値を併せて監視する。連動フラグ1だけではドームの追従完了を保証しない。

今回は本体を起動していないため、UI Automation対応の有無と実際のボタン識別子は未検証。したがって、このブリッジを「動作確認済みのCLI」としては提供していない。内部変数を外部から書き換えて連動ONにする方式は採用しない。

## 5. ドームのスリットを開く

GUIのButtonDomSltOpenClickは内部コマンド17をキューへ設定する。Closeは16、Stopは18。

2026-09-14の実ログ：

```text
12:21:02 - Send DSO#
12:21:02 - Read OK 17
...
12:48:24 - Send DSC#
12:48:24 - Read OK 16
```

DSO#が開、DSC#が閉に対応することはGUIハンドラーとログから確認できる。しかしこれはMaster→制御装置の通信であり、TCP 8744へDSO#を投げるものではない。

既存Masterを動かしたまま別プログラムからシリアルポートを開かず、CLI→UI Automationブリッジ→Masterのスリット開ボタン、という経路にする。正式APIを追加できる場合はそちらを優先する。要求後はraw.DomSlStを監視するが、値と「開中／全開／閉中／全閉」の完全な対応は今回未確定。OK 17は受理応答であり全開の証明ではない。

## 6. 現在の鏡筒位置をリアルタイム取得

既存のMakeStatusが作るJSONはcommand=statusとstatus=stop/move/track/error/none。Ra/Dec/Az/Altを追加する処理はない。また同梱status.binは{"command":"status","status":"stop"}だが、statusは受信命令表に登録されていない。これを位置照会として扱わない。

添付master_position.pyは標準ライブラリのみで動作する、読み取り専用の試作。対象本体のSHA256を照合し、ASLRを考慮してロードベース+RVAからReadProcessMemoryで取得する。WriteProcessMemory、制御装置への接続、起動処理は含まない。

このPCのバンドルPythonでの実行例：

```powershell
$pythonExe = 'C:\Users\domepc6-tsuboi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$readerFile = 'C:\Users\domepc6-tsuboi\work\observation\scat_observation\scat_auto_observation\test_20260917\master_position.py'
$masterProcess = @(Get-Process -Name Master2018 -ErrorAction Stop)
if ($masterProcess.Count -ne 1) { throw 'Master2018のPIDを一つに特定してください' }
& $pythonExe $readerFile --pid $masterProcess[0].Id --interval 0.5
```

--onceを付けると1回だけ取得。Ctrl+Cで終了。64ビットPythonが別にあればそれも使える。現在のPCではpyランチャーはあるが、登録済みPythonは見つからなかったため、上の実在するランタイムを指定した。

主な出力：

| JSONキー | ソフト内部の変数 | 意味 |
|---|---|---|
| ra_j2000_hours | TelPosJ2kRa | 鏡筒現在位置のJ2000赤経、時間 |
| dec_j2000_deg | TelPosJ2kDec | 鏡筒現在位置のJ2000赤緯、度 |
| azimuth_software_deg | TelPosLon | ソフトの水平座標変換が計算する方位角、度 |
| altitude_software_deg | TelPosLat | ソフトの高度、度。水平変換後に屈折処理を通る |
| raw.TelPosIntRa / TelPosIntDec | 同名 | 装置側座標。J2000と区別する |
| raw.DomRotAutoFlag | 同名 | 連動ONで1、OFFで0 |
| raw.DomRotDir / DomRtSt / DomSlSt | 同名 | ドーム方位／回転状態／スリット状態の内部値 |
| raw.ComStat / EmgStat / RainStat | 同名 | 通信／非常／雨の内部状態コード。コード意味は未確定 |

方位角は表示値との一致と北・東・南・西の対応を現地で照合するまでは、一般的な北0度・東90度と決めつけない。TelPos系を読むことが重要で、CurPos系は選択・目標座標側であり「現在の鏡筒位置」の代わりにしない。

新規Pythonプログラムへの組み込み：

```python
from master_position import Reader

with Reader(master_pid) as reader:
    sample = reader.read_once()
    ra = sample['ra_j2000_hours']
    dec = sample['dec_j2000_deg']
    az = sample['azimuth_software_deg']
    alt = sample['altitude_software_deg']
```

master_position.pyを新規プログラムと同じフォルダまたはPythonのモジュール検索パスに置く。異なる言語ならCLI標準出力のJSON Linesを読む。

制限：

- サンプリング間隔と装置側の更新周期は別。0.5秒読み取りは0.5秒ごとの新測定を保証しない。
- sampled_at_utcは読み取ったPC時刻。装置データの測定時刻ではない。controller_data_freshnessは意図的にunknown。
- 通信断・初期化中の古い値やゼロも読める。移動していないと座標が変わらない場合もあるため、「値が不変＝通信断」という判定もしない。
- 一括メモリ読み取りはアプリの更新処理と同期していない。境界では異なる更新の値が混ざる可能性があり、厳密な同時刻スナップショットではない。
- 元EXEの差し替え・更新ではハッシュ不一致として停止する。Master2018_0207.exeには使わない。
- この試作は監視・調査用。無人観測の安全判定をこの値だけに依存させない。

## 7. 自動観測の方針

準備→装置状態と観測条件の確認→スリット開要求→全開の確認→ドーム連動ON→連動フラグ確認→track要求→鏡筒導入とドーム追従完了の確認→露光、という順序を状態機械として管理する。

特に「要求の送信」「受理」「動作中」「完了」を別の状態にする。追尾状態trackだけで露光開始せず、現在座標と目標座標を同じ座標系で比較し、ドームの開口も確認する。エラー・通信断・雨・復電後の扱いは既存装置の仕様に合わせて決める。

メーカーへ追加を求めるAPIの最小セット：

- slew(ra_j2000_hours, dec_j2000_deg)、stop
- dome_link(enabled)、slit_open / slit_close / slit_stop
- get_position：Ra/Dec/Az/Alt、座標系、方位原点、取得時刻、装置更新時刻
- get_state：導入中、追尾、ドーム追従、全開・全閉、通信状態とエラー
- 各要求のIDと完了通知。要求の境界を確実に解釈できるTCPフレーミング

以上が整うまでは「導入はCLI、ドームは現地監督下、位置CLIで照合」という段階運用が妥当。

## 8. 静的解析の根拠と検証

EXEに残るDWARFデバッグ情報と逆アセンブルを照合した。以下は解析時の優先ロードアドレス（実行時ASLRで変わる）。

| 処理 | アドレス | 確認内容 |
|---|---|---|
| serverInit | 0x4c01d0 | AF_INET/SOCK_STREAM、8744番、全インターフェースbind |
| ソケット受信 | 0x4c00b0 | 最大1024バイトのrecvからJSON処理 |
| RecvCmdAns | 0x45e730 | 5種類の命令表による分岐 |
| tracking | 0x45d960 | ra / dec / pmra / pmdec、J2000変換呼び出し |
| MakeStatus | 0x45e3e0 | commandと状態文字列のみ |
| ButtonDomRotAutoOnClick | 0x48b900 | DomRotAutoFlag=1 |
| ButtonDomSltOpenClick | 0x48c060 | 内部要求17 |
| TelPosLon等 | 0x16cb320以降 | DWARF変数名、受信値変換、表示参照を照合 |

位置CLIのフィールド復号、短い読み取りとNaNの拒否、Windowsプロセス照会と別EXEのハッシュ拒否を検証済み。Masterへの接続・位置値の画面照合・実機動作・スリット状態コードの完全同定は未実施。元フォルダのファイルは変更していない。


## 9. 今回配置したPythonソース

`test_20260917/nishimura_cli.py` に起動・track・stop・startup・endingのCLIを実装した。
既定は送信内容の表示だけで、`--execute` を付けると実行する。
`position` は `master_position.py` を呼び出す読み取り専用機能。
`dome-link` / `slit` は未対応であることを表示して終了コード2で停止し、命令を送らない。
具体例は `test_20260917/README.md` を参照。
試験はモックと合成データで実施し、ソフト起動・実機コマンド送信は行っていない。

## GUI操作のCLI化（追補）

ドーム連動とスリット操作は、8744番のJSON APIに命令名がないため、MasterのGUIボタンが呼ぶOnClickをWindowsメッセージで実行する方式を追加した。
EXE内のDFM/シンボルから、対象コンポーネント名を確認した。

| CLI操作 | Masterコンポーネント | GUI処理 |
|---|---|---|
| `dome-link on` | `ButtonDomRotAutoOn` | ドーム自動連動フラグをONにするOnClick |
| `dome-link off` | `ButtonDomRotAutoOff` | ドーム自動連動フラグをOFFにするOnClick |
| `slit open` | `ButtonDomSltOpen` | 内部要求17（ログ上の `DSO#`）を設定するOnClick |
| `slit close` | `ButtonDomSltClose` | 内部要求16（ログ上の `DSC#`）を設定するOnClick |
| `slit stop` | `ButtonDomSltStop` | 内部要求18を設定するOnClick |

実装は `test_20260917/gui_bridge.py`。PIDの全トップレベル／子ウィンドウを列挙し、`TButton`または`Button`クラスと表示文字列を一意照合した後、Windows標準の`BM_CLICK`を`SendMessageTimeoutW`で一度だけ送る。対象が0件、複数件、非表示、無効の場合はクリックしない。

実行例：

```powershell
& $pythonExe .\nishimura_cli.py dome-link on --pid $masterPid --execute
& $pythonExe .\nishimura_cli.py slit open --pid $masterPid --execute
```

これはGUIのOnClickを呼ぶため、Masterが起動し、対象画面が表示されている必要がある。クリック処理の完了はドーム／スリットの機械動作完了を保証しない。クリック後は位置CLIの`raw.DomRotAutoFlag`と`raw.DomSlSt`、GUI表示、装置状態を別々に確認する。`DomSlSt`の数値と「全開」等の意味は未確定なので、自動観測の完了判定へ直接使わない。

この方式は実機GUIでのクリック検証をまだ行っていない。初回は`--execute`を付けずに計画表示を確認し、対象ウィンドウとPIDが正しいことを確認してから、監督下で1回だけ実行する。
