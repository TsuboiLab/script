"""Masterの既存TButtonをCLIからクリックする、版固定のGUIブリッジ。

経路: FormMenuのボタン参照 → HWNDのVCLプロパティ照合 → BM_CLICK → 既存OnClick。
メモリの書き換え、DLL注入、内部関数の直接呼び出し、シリアル送信は行わない。
画面の文字や座標でボタンを選ばない。同名の「開」ボタンとの混同を避ける。

注意: HWNDとVCLオブジェクトの対応は実機では未検証。対応が見つからなければ
推測クリックへフォールバックせず停止する。inspect-guiで最初に照合結果を確認する。
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass, asdict
import time

from master_position import Reader, BLOCK_VA, IMAGE_BASE

# 解析したEXEのDWARFから得たFormMenuグローバル変数の仮想アドレス。
# ReaderがEXEのSHA256を検証してから、実際のロードベースとの差分を加える。
FORM_MENU_VA = 0x16DF050

# EXEの公開フィールドRTTIから得たTFormMenuオブジェクト内のボタン参照位置。
# DFM内のTButton名とOnClickの結び付けも照合した。これはHWNDの固定値ではない。
BUTTONS = {
    'dome-link:on': ('ButtonDomRotAutoOn', 0xB80),
    'dome-link:off': ('ButtonDomRotAutoOff', 0xB78),
    'slit:open': ('ButtonDomSltOpen', 0xBA8),
    'slit:close': ('ButtonDomSltClose', 0xB98),
    'slit:stop': ('ButtonDomSltStop', 0xBA0),
}


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    class_name: str
    caption: str
    # VCLがウィンドウに付けたDelphi...プロパティの値を保持する。
    # 値がTFormMenu内の対象ボタン参照と一致して初めて候補として扱う。
    object_addresses: tuple[int, ...]
    visible: bool
    enabled: bool


def select_window(windows, pid, object_address, class_name):
    """完全一致する唯一のウィンドウを選ぶ。曖昧・未生成の場合は実行しない。"""
    if not object_address:
        raise RuntimeError('対象VCLオブジェクトが未生成です')
    matches = [w for w in windows if w.pid == pid and w.class_name == class_name
               and object_address in w.object_addresses]
    if len(matches) != 1:
        raise RuntimeError(f'{class_name}のVCL/ HWND照合が一意ではありません: {len(matches)}件。'
                           'GUIを表示し、inspect-guiで確認してください。推測クリックは行いません')
    return matches[0]


class Win32:
    """Windows APIのみを集めた薄い層。試験時はこの層をFakeへ差し替える。"""
    def __init__(self):
        self.u = C.WinDLL('user32', use_last_error=True)
        self.window_callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        self.property_callback = C.WINFUNCTYPE(W.BOOL, W.HWND, C.c_void_p, W.HANDLE, C.c_size_t)
        self.u.EnumWindows.argtypes = [self.window_callback, W.LPARAM]
        self.u.EnumChildWindows.argtypes = [W.HWND, self.window_callback, W.LPARAM]
        self.u.EnumPropsExW.argtypes = [W.HWND, self.property_callback, C.c_size_t]
        self.u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        self.u.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.u.IsWindowVisible.argtypes = [W.HWND]
        self.u.IsWindowEnabled.argtypes = [W.HWND]
        self.u.IsChild.argtypes = [W.HWND, W.HWND]
        self.u.IsIconic.argtypes = [W.HWND]
        self.u.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM,
                                               W.UINT, W.UINT, C.POINTER(C.c_size_t)]
        self.u.SendMessageTimeoutW.restype = C.c_ssize_t

    def describe(self, hwnd):
        pid = W.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, C.byref(pid))
        cls = C.create_unicode_buffer(256)
        text = C.create_unicode_buffer(512)
        self.u.GetClassNameW(hwnd, cls, len(cls))
        self.u.GetWindowTextW(hwnd, text, len(text))
        objects = []

        @self.property_callback
        def property_found(window, name, value, context):
            # 名前が整数ATOMとして渡される場合は文字列として参照しない。
            if name and name > 0xFFFF:
                key = C.wstring_at(name)
                if key.startswith('Delphi') and value:
                    objects.append(int(value))
            return True

        self.u.EnumPropsExW(hwnd, property_found, 0)
        return WindowInfo(int(hwnd), pid.value, cls.value, text.value, tuple(objects),
                          bool(self.u.IsWindowVisible(hwnd)), bool(self.u.IsWindowEnabled(hwnd)))

    def windows(self, pid):
        result = []
        seen = set()

        def add(hwnd):
            owner = W.DWORD()
            self.u.GetWindowThreadProcessId(hwnd, C.byref(owner))
            if owner.value == pid and int(hwnd) not in seen:
                seen.add(int(hwnd))
                result.append(self.describe(hwnd))

        @self.window_callback
        def child(hwnd, context):
            add(hwnd)
            return True

        @self.window_callback
        def top(hwnd, context):
            owner = W.DWORD()
            self.u.GetWindowThreadProcessId(hwnd, C.byref(owner))
            if owner.value == pid:
                add(hwnd)
                self.u.EnumChildWindows(hwnd, child, 0)
            return True

        self.u.EnumWindows(top, 0)
        return result

    def is_child(self, parent, child):
        return bool(self.u.IsChild(parent, child))

    def is_minimized(self, hwnd):
        return bool(self.u.IsIconic(hwnd))

    def click(self, hwnd, timeout_ms):
        # BM_CLICKはWindows標準のボタンクリックメッセージ。
        # 戻り値は動作完了ではなく、ウィンドウメッセージ処理の結果としてのみ扱う。
        result = C.c_size_t()
        C.set_last_error(0)
        ok = self.u.SendMessageTimeoutW(hwnd, 0x00F5, 0, 0, 0x0002 | 0x0020,
                                        timeout_ms, C.byref(result))
        if not ok:
            raise RuntimeError(f'クリックの結果が不明です (Win32={C.get_last_error()})。'
                               'タイムアウトでも処理済みの可能性があるため再送しません')


class GuiBridge:
    def __init__(self, pid, reader=None, windows=None):
        self.pid = pid
        self.reader = reader if reader is not None else Reader(pid)
        try:
            self.native = windows if windows is not None else Win32()
        except BaseException:
            self.reader.close()
            raise

    def close(self):
        self.reader.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def pointer(self, address):
        # Readerは読み取り専用権限で開いている。オブジェクトのポインタだけを取得する。
        value = C.c_uint64()
        size = C.c_size_t()
        if not self.reader.k.ReadProcessMemory(self.reader.handle, address,
                                               C.byref(value), 8, C.byref(size)) or size.value != 8:
            raise RuntimeError('VCLオブジェクト参照の読み取りに失敗しました')
        return value.value

    def form_and_buttons(self):
        # reader.addressはテレメトリブロックの実アドレス。そこからASLR差分を復元する。
        relocation = self.reader.address - BLOCK_VA
        form = self.pointer(FORM_MENU_VA + relocation)
        if not form:
            raise RuntimeError('FormMenuが未生成です。Masterの初期化完了を待ってください')
        return form, {key: self.pointer(form + offset) for key, (_, offset) in BUTTONS.items()}

    def inspect(self):
        """クリックせず、オブジェクトとHWNDの対応、表示・有効状態をJSON用に返す。"""
        form, buttons = self.form_and_buttons()
        windows = self.native.windows(self.pid)
        result = {'pid': self.pid, 'form_object': hex(form), 'buttons': {}}
        try:
            form_window = select_window(windows, self.pid, form, 'TFormMenu')
            result['form_window'] = asdict(form_window)
        except RuntimeError as error:
            result['form_error'] = str(error)
            form_window = None
        for action, address in buttons.items():
            entry = {'component': BUTTONS[action][0], 'object_address': hex(address)}
            try:
                target = select_window(windows, self.pid, address, 'TButton')
                entry.update(asdict(target))
                entry['under_form'] = bool(form_window and self.native.is_child(form_window.hwnd, target.hwnd))
            except RuntimeError as error:
                entry['error'] = str(error)
            result['buttons'][action] = entry
        return result

    def resolve(self, action):
        form, buttons = self.form_and_buttons()
        windows = self.native.windows(self.pid)
        parent = select_window(windows, self.pid, form, 'TFormMenu')
        target = select_window(windows, self.pid, buttons[action], 'TButton')
        if not self.native.is_child(parent.hwnd, target.hwnd):
            raise RuntimeError('対象ボタンがFormMenuの配下ではありません')
        if not parent.visible or not target.visible or self.native.is_minimized(parent.hwnd):
            raise RuntimeError('対象GUIを表示し、最小化を解除してください。自動で状態は変更しません')
        if not parent.enabled or not target.enabled:
            raise RuntimeError('GUI側で操作が無効です。無効化を迂回せず中止しました')
        return parent, target

    def execute(self, action, timeout=2.0):
        """対象を再照合して1回だけクリック。連動フラグのみ、要求状態到達を確認する。"""
        if action not in BUTTONS:
            raise ValueError('不明なGUI操作です')
        if not 0 < timeout <= 30:
            raise ValueError('GUI timeoutは0より大きく30秒以下にしてください')
        before = self.reader.read_once()
        # ON/OFFはトグルではなく目的状態。既に目的状態ならクリックしない。
        desired = 1 if action == 'dome-link:on' else 0
        if action.startswith('dome-link:') and before['raw']['DomRotAutoFlag'] == desired:
            return {'action': action, 'clicked': False, 'link_flag_confirmed': True,
                    'reason': 'already_requested_state', 'mechanical_completion': 'unconfirmed'}
        parent, target = self.resolve(action)
        # 照合中のGUI再生成などでHWNDが変わった場合は実行しない。
        if self.resolve(action) != (parent, target):
            raise RuntimeError('照合中にGUIが変化しました。クリックせず中止しました')
        self.native.click(target.hwnd, max(1, int(timeout * 1000)))
        after = self.reader.read_once()
        result = {'action': action, 'component': BUTTONS[action][0], 'hwnd': target.hwnd,
                  'clicked': True, 'message_processed': True,
                  'mechanical_completion': 'unconfirmed', 'automatic_retry': False,
                  'before': before['raw'], 'after': after['raw']}
        if action.startswith('dome-link:'):
            deadline = time.monotonic() + timeout
            while after['raw']['DomRotAutoFlag'] != desired and time.monotonic() < deadline:
                time.sleep(0.05)
                after = self.reader.read_once()
            result['after'] = after['raw']
            result['link_flag_confirmed'] = after['raw']['DomRotAutoFlag'] == desired
        # スリットのDomSlStコード意味は未確定。開要求と全開確認を混同しない。
        return result
