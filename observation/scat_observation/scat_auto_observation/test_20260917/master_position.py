"""Master2018の位置を読み取り専用で取得する実験用モジュール。

TCPのstatusは座標を返さないため、解析したEXEのデバッグ情報に基づいて
WindowsのReadProcessMemoryを使う。メモリへの書き込みや装置命令送信はしない。
ソフト更新時はアドレスが変わるため、SHA256が一致しない版には使用しない。
本体が保持する値は通信断でも古いまま残り得る。読み取り時刻と測定時刻は別。
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import datetime
import hashlib
import json
import math
from pathlib import Path
import struct
import time

# このハッシュは実際に調査したMaster2018.exe専用。別版に合わせて安易に変更しない。
EXPECTED_SHA256 = '7a4d5966d313d615dfca9980a9fdece18928e92a1cdf683e904f5c8f0e5cc003'
# 解析時のロードベース。実行時はASLRで変動するため、その差分を補正する。
IMAGE_BASE = 0x400000
BLOCK_VA = 0x16cb320
BLOCK_SIZE = 0xa4
# ブロック先頭からのバイト位置。8バイト浮動小数点数は座標などに使われる。
DOUBLE_FIELDS = {'TelPosLon':0, 'TelPosLat':8, 'TelPosJ2kRa':16,
                 'TelPosJ2kDec':24, 'TelPosIntRa':32, 'TelPosIntDec':40,
                 'DomRotDir':64}
# 状態コードは4バイト整数。意味未確定のコードを正常/異常へ独自変換しない。
INT_FIELDS = {'DomRotAutoFlag':72, 'TelStat':76, 'DomRtSt':104,
              'DomSlSt':108, 'ContModeSt':124, 'PwrStat':128,
              'EmgStat':132, 'CntStat':136, 'RainStat':140, 'ComStat':160}

def decode(data):
    """一括取得したバイト列を復号する。装置データの鮮度は判定しない。"""
    if len(data) != BLOCK_SIZE:
        raise ValueError('Incomplete telemetry block')
    raw = {key: struct.unpack_from('<d', data, off)[0] for key, off in DOUBLE_FIELDS.items()}
    if not all(math.isfinite(v) for v in raw.values()):
        raise ValueError('Non-finite telemetry; sample rejected')
    raw.update({key: struct.unpack_from('<i', data, off)[0] for key, off in INT_FIELDS.items()})
    return {'sampled_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source': 'Master2018 process memory; experimental',
            'controller_data_freshness': 'unknown',
            'ra_j2000_hours': raw['TelPosJ2kRa'], 'dec_j2000_deg': raw['TelPosJ2kDec'],
            'azimuth_software_deg': raw['TelPosLon'],
            'altitude_software_deg': raw['TelPosLat'], 'raw': raw}

class Reader:
    """with文で使う読み取り専用リーダー。終了時にプロセスハンドルを閉じる。"""
    def __init__(self, pid):
        if C.sizeof(C.c_void_p) != 8:
            raise RuntimeError('Use 64-bit Python')
        # ctypesでは64ビットポインタを切り詰めないよう、APIの引数型・戻り値型を指定。
        self.k = C.WinDLL('kernel32', use_last_error=True)
        self.ps = C.WinDLL('psapi', use_last_error=True)
        self.k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.k.OpenProcess.restype = W.HANDLE
        self.k.CloseHandle.argtypes = [W.HANDLE]
        self.k.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
        self.k.ReadProcessMemory.restype = W.BOOL
        self.k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
        self.ps.EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(W.HMODULE), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
        self.ps.EnumProcessModulesEx.restype = W.BOOL
        # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ のみ。書き込み権限は要求しない。
        self.handle = self.k.OpenProcess(0x0400 | 0x0010, False, pid)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        try:
            buf = C.create_unicode_buffer(32768)
            length = W.DWORD(len(buf))
            if not self.k.QueryFullProcessImageNameW(self.handle, 0, buf, C.byref(length)):
                raise C.WinError(C.get_last_error())
            exe = Path(buf.value)
            if hashlib.sha256(exe.read_bytes()).hexdigest() != EXPECTED_SHA256:
                raise RuntimeError('Executable SHA256 does not match inspected version; refusing offsets')
            modules = (W.HMODULE * 1024)()
            needed = W.DWORD()
            if not self.ps.EnumProcessModulesEx(self.handle, modules, C.sizeof(modules), C.byref(needed), 3):
                raise C.WinError(C.get_last_error())
            if not needed.value or not modules[0]:
                raise RuntimeError('Main module unavailable')
            # モジュール先頭 + RVA。固定の絶対アドレスをそのまま読まない。
            self.address = int(modules[0]) + BLOCK_VA - IMAGE_BASE
        except BaseException:
            self.close()
            raise
    def read_once(self):
        """座標と状態を一括で読む。ただしアプリ側更新との同期は保証されない。"""
        buf = C.create_string_buffer(BLOCK_SIZE)
        n = C.c_size_t()
        if not self.k.ReadProcessMemory(self.handle, self.address, buf, BLOCK_SIZE, C.byref(n)):
            raise C.WinError(C.get_last_error())
        if n.value != BLOCK_SIZE:
            raise RuntimeError('Short process-memory read')
        return decode(buf.raw)
    def close(self):
        """正常終了・例外の双方でハンドルを解放する。"""
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True, help='PID of the already running Master2018.exe')
    p.add_argument('--interval', type=float, default=1.0, help='Sampling interval in seconds (>=0.1)')
    p.add_argument('--once', action='store_true')
    a = p.parse_args()
    if not math.isfinite(a.interval) or a.interval < 0.1:
        p.error('--interval must be finite and >=0.1')
    try:
        with Reader(a.pid) as reader:
            while True:
                print(json.dumps(reader.read_once(), ensure_ascii=False, allow_nan=False), flush=True)
                if a.once: break
                time.sleep(a.interval)
    except KeyboardInterrupt:
        pass

if __name__ == '__main__': main()
