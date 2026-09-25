"""Master2018 のGUIボタンをCLIから安全にクリックする薄いWin32ブリッジ。

GUIのOnClickハンドラーを経由するため、スリット開閉・ドーム連動の処理は
Master自身が行います。シリアルポートを直接開いたり、プロセスメモリを
書き換えたりしません。

対象ウィンドウとボタンは、PID・ウィンドウクラス・表示文字列の組合せで
一意に照合します。一意に決まらない場合はクリックせずエラーにします。
実機のボタン表示文字列は日本語/英語設定で異なるため、候補を明示的に
登録しています。
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass


BM_CLICK = 0x00F5
SMTO_ABORTIFHUNG = 0x0002
SMTO_ERRORONEXIT = 0x0020


# EXEのDFM/シンボルから確認したコンポーネント名に対応する表示文字列。
# 日本語設定では「開」「閉」「停止」、英語設定では Open/Close/Stop を想定。
BUTTON_CAPTIONS = {
    "dome-link:on": ("ON", "連動ON", "自動ON"),
    "dome-link:off": ("OFF", "連動OFF", "自動OFF"),
    "slit:open": ("開", "Open"),
    "slit:close": ("閉", "Close"),
    "slit:stop": ("停止", "Stop"),
}


@dataclass(frozen=True)
class Control:
    hwnd: int
    pid: int
    class_name: str
    caption: str


class Win32Gui:
    def __init__(self):
        self.user32 = C.WinDLL("user32", use_last_error=True)
        self._enum_window_cb = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        self.user32.EnumWindows.argtypes = [self._enum_window_cb, W.LPARAM]
        self.user32.EnumChildWindows.argtypes = [W.HWND, self._enum_window_cb, W.LPARAM]
        self.user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        self.user32.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.user32.IsWindowVisible.argtypes = [W.HWND]
        self.user32.IsWindowEnabled.argtypes = [W.HWND]
        self.user32.IsIconic.argtypes = [W.HWND]
        self.user32.SendMessageTimeoutW.argtypes = [
            W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, C.POINTER(W.DWORD_PTR)
        ]
        self.user32.SendMessageTimeoutW.restype = W.LRESULT

    def _info(self, hwnd: int) -> Control | None:
        pid = W.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        cls = C.create_unicode_buffer(256)
        caption = C.create_unicode_buffer(512)
        self.user32.GetClassNameW(hwnd, cls, len(cls))
        self.user32.GetWindowTextW(hwnd, caption, len(caption))
        return Control(int(hwnd), pid.value, cls.value, caption.value)

    def controls(self, pid: int) -> list[Control]:
        found: list[Control] = []

        def add(hwnd: int):
            info = self._info(hwnd)
            if info and info.pid == pid and info.caption:
                found.append(info)

        @self._enum_window_cb
        def child(hwnd, _):
            add(hwnd)
            return True

        @self._enum_window_cb
        def top(hwnd, _):
            info = self._info(hwnd)
            if info and info.pid == pid:
                add(hwnd)
                self.user32.EnumChildWindows(hwnd, child, 0)
            return True

        self.user32.EnumWindows(top, 0)
        return found

    def click(self, control: Control, timeout_ms: int = 2000):
        if not self.user32.IsWindowVisible(control.hwnd):
            raise RuntimeError("対象ボタンが非表示です")
        if not self.user32.IsWindowEnabled(control.hwnd):
            raise RuntimeError("対象ボタンが無効です")
        result = W.DWORD_PTR()
        ok = self.user32.SendMessageTimeoutW(
            control.hwnd, BM_CLICK, 0, 0,
            SMTO_ABORTIFHUNG | SMTO_ERRORONEXIT, timeout_ms, C.byref(result)
        )
        if not ok:
            raise OSError(C.get_last_error(), "BM_CLICKがタイムアウトまたは失敗しました")


def resolve_button(pid: int, action: str, api: Win32Gui | None = None) -> tuple[Win32Gui, Control]:
    """PIDと期待する表示文字列から、唯一の対象ボタンを返す。"""
    if action not in BUTTON_CAPTIONS:
        raise ValueError(f"未対応のGUI操作: {action}")
    api = api or Win32Gui()
    captions = set(BUTTON_CAPTIONS[action])
    candidates = [
        c for c in api.controls(pid)
        if c.class_name in {"TButton", "Button"} and c.caption.strip() in captions
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"{action} のボタンを一意に特定できません（候補 {len(candidates)}件）。"
            "GUI設定と表示を確認して中止しました"
        )
    return api, candidates[0]


def click_action(pid: int, action: str, timeout_ms: int = 2000) -> dict:
    """一度だけGUI操作を実行する。クリック完了は機械動作完了を意味しない。"""
    api, button = resolve_button(pid, action)
    api.click(button, timeout_ms)
    return {
        "action": action,
        "clicked": True,
        "hwnd": button.hwnd,
        "caption": button.caption,
        "message": "BM_CLICK processed; mechanical completion is unconfirmed",
        "automatic_retry": False,
    }
