"""西村望遠鏡 Master2018 の実験用CLI（Python標準ライブラリのみ）。

例:
    python nishimura_cli.py start
    python nishimura_cli.py track --ra-hours 12.5 --dec-deg 30.0
    python nishimura_cli.py track --ra-hours 12.5 --dec-deg 30.0 --execute
    python nishimura_cli.py position --pid 1234 --once

重要:
    * 動作を伴う命令は、既定では計画の表示だけ。--executeで初めて実行する。
    * TCP書き込み成功は「導入完了」でも「装置の受理確認」でもない。
    * ドーム連動・スリット操作は既存JSONではなく、Master GUIのOnClickを呼ぶ。
    * 本ソースは静的解析からの試作。実機との接続試験は実施していない。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import socket
import subprocess
import sys

from master_position import EXPECTED_SHA256, Reader
from gui_bridge import click_action

DEFAULT_EXE = Path(r"C:\Users\domepc6-tsuboi\Documents\nishimura\Master\Master2018.exe")
# 調査したソフトが開くTCPサーバー。同一PC内での使用に限定する。
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8744


def finite_number(text: str) -> float:
    """NaNや無限大をCLI入力として受け付けない。"""
    value = float(text)
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError("有限の数値を指定してください")
    return value


def build_payload(command: str, ra_hours: float | None = None,
                  dec_deg: float | None = None) -> bytes:
    """送信するJSONを作る純粋関数。ここではソケットを開かない。

    RAはJ2000の十進時間、DecはJ2000の十進度。
    受信側がjson_real_valueを使うため、整数で与えられてもfloatへ変換する。
    固有運動の単位は未確定なので、pmra/pmdecは常に0.0とする。
    """
    if command == "track":
        if ra_hours is None or not math.isfinite(ra_hours) or not 0 <= ra_hours < 24:
            raise ValueError("RAは0以上24未満の十進時間で指定してください")
        if dec_deg is None or not math.isfinite(dec_deg) or not -90 <= dec_deg <= 90:
            raise ValueError("Decは-90以上90以下の度で指定してください")
        payload = {"command": "track", "ra": float(ra_hours), "dec": float(dec_deg),
                   "pmra": 0.0, "pmdec": 0.0}
    elif command in {"stop", "startup", "ending"}:
        payload = {"command": command}
    else:
        raise ValueError(f"未対応のTCP命令です: {command}")

    # HTTPや#終端、独自ヘッダーは付けない。UTF-8の短いJSONをそのまま送る。
    encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) >= 1024:
        raise ValueError("受信バッファ上限を超える要求です")
    return encoded


def verify_executable(exe: Path) -> Path:
    """解析対象と同じバイナリであることを照合。別版への流用を拒否する。"""
    exe = exe.resolve(strict=True)
    actual = hashlib.sha256(exe.read_bytes()).hexdigest()
    if actual != EXPECTED_SHA256:
        raise ValueError("Master2018.exeのSHA256が調査対象と異なります")
    return exe


def send_payload(payload: bytes, timeout: float = 3.0) -> dict:
    """一つの接続で一つの要求を送る。自動再送は絶対に行わない。

    相手側はTCPの分割受信を十分に扱っていない実装なので、sendallを使っても
    常に正しく処理される保証はない。失敗後は現場の状態を確認すること。
    応答プロトコルの受理・完了判定は未確定のため、成功判定は送信までに限定。
    """
    with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=timeout) as connection:
        connection.sendall(payload)
    return {"tcp_write_completed": True, "accepted_by_master": "unconfirmed",
            "motion_completed": "unconfirmed", "automatic_retry": False}


def ensure_not_running() -> None:
    """起動時だけ同名プロセスの存在を確認して二重起動を避ける。

    PowerShellへの入力は固定文字列だけであり、ユーザー入力をコードに埋め込まない。
    なお、照会と起動はアトミックではないため、複数CLIから同時起動しないこと。
    """
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "@(Get-Process -Name Master2018 -ErrorAction SilentlyContinue).Count"],
        capture_output=True, text=True, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if int(result.stdout.strip()) != 0:
        raise ValueError("Master2018は既に起動しています。二重起動を中止しました")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action", required=True)

    # --executeは動作を伴うサブコマンドごとに指定する。
    descriptions = {
        "start": "GUIソフトを起動（通常は計画表示のみ）",
        "track": "J2000のRa/Decへ導入・追尾要求",
        "stop": "鏡筒停止要求。物理非常停止の代替ではない",
        "startup": "起動済みMasterの観測起動処理。EXE起動とは別",
        "ending": "Masterの観測終了処理。設定次第でホーム移動等を伴う",
    }
    for action, description in descriptions.items():
        sub = commands.add_parser(action, help=description, description=description)
        sub.add_argument("--execute", action="store_true", help="実際に起動または送信する")
        sub.add_argument("--exe", type=Path, default=DEFAULT_EXE,
                         help="照合するMaster2018.exeのパス")
        if action == "track":
            sub.add_argument("--ra-hours", required=True, type=finite_number)
            sub.add_argument("--dec-deg", required=True, type=finite_number)
        if action != "start":
            sub.add_argument("--timeout", type=finite_number, default=3.0,
                             help="接続・書き込みタイムアウト秒。自動再送なし")

    position = commands.add_parser("position", help="起動済みMasterの位置を読み取り専用で取得")
    position.add_argument("--pid", required=True, type=int)
    position.add_argument("--once", action="store_true")
    position.add_argument("--interval", type=finite_number, default=1.0)

    link = commands.add_parser("dome-link", help="Master GUIのドーム連動ON/OFFボタンをクリック")
    link.add_argument("state", choices=["on", "off"])
    link.add_argument("--pid", required=True, type=int, help="起動中Master2018のPID")
    link.add_argument("--execute", action="store_true", help="実際にGUIボタンをクリックする")
    slit = commands.add_parser("slit", help="Master GUIのスリット操作ボタンをクリック")
    slit.add_argument("state", choices=["open", "close", "stop"])
    slit.add_argument("--pid", required=True, type=int, help="起動中Master2018のPID")
    slit.add_argument("--execute", action="store_true", help="実際にGUIボタンをクリックする")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        if args.action in {"dome-link", "slit"}:
            action = f"dome-link:{args.state}" if args.action == "dome-link" else f"slit:{args.state}"
            plan = {"action": action, "pid": args.pid, "execute": args.execute,
                    "transport": "Win32 BM_CLICK -> Master OnClick"}
            print(json.dumps(plan, ensure_ascii=False))
            if args.pid <= 0:
                raise ValueError("PIDは正数を指定してください")
            if args.execute:
                verify_executable(args.exe if hasattr(args, "exe") else DEFAULT_EXE)
                print(json.dumps(click_action(args.pid, action), ensure_ascii=False))
            return 0

        if args.action == "position":
            # 更新間隔は読み取り周期であり、制御装置側の測定周期ではない。
            import time
            if args.pid <= 0 or args.interval < 0.1:
                raise ValueError("PIDは正数、intervalは0.1秒以上を指定してください")
            with Reader(args.pid) as reader:
                while True:
                    print(json.dumps(reader.read_once(), ensure_ascii=False,
                                     allow_nan=False), flush=True)
                    if args.once:
                        break
                    time.sleep(args.interval)
            return 0

        plan = {"action": args.action, "execute": args.execute, "exe": str(args.exe)}
        if args.action == "start":
            plan["working_directory"] = str(args.exe.parent)
            print(json.dumps(plan, ensure_ascii=False))
            if args.execute:
                exe = verify_executable(args.exe)
                ensure_not_running()
                # shellを介さず、引数リストで起動。GUIは観測担当者が見える通常の表示。
                process = subprocess.Popen([str(exe)], cwd=str(exe.parent))
                print(json.dumps({"launched_pid": process.pid, "controller_ready": "unconfirmed"}))
            return 0

        if args.timeout <= 0:
            raise ValueError("timeoutは0より大きくしてください")
        payload = build_payload(args.action, getattr(args, "ra_hours", None),
                                getattr(args, "dec_deg", None))
        plan.update({"host": SERVER_HOST, "port": SERVER_PORT,
                     "payload": payload.decode("utf-8")})
        print(json.dumps(plan, ensure_ascii=False))
        if args.execute:
            # ファイルの照合であり、ポート所有者の認証ではない。READMEの待受確認も行う。
            verify_executable(args.exe)
            print(json.dumps(send_payload(payload, args.timeout), ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"エラー: {error}。自動再送は行っていません。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
