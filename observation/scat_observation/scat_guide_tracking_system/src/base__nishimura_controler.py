"""西村MoT (Master2018) の読み出し・命令送信をまとめる薄い制御層。

位置はTCP statusではなく、調査済みMaster2018の読み取り専用メモリから取得する。
制御命令はTCPまたは既存GUIボタン経由で、一度だけ送信する。
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2] / 'scat_auto_observation' / 'test_20260917'


def _load(name):
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    return importlib.import_module(name)


# User-confirmed tab/caption pairs. No guessed object offsets are used.
TAB_ACTIONS = {
    'power:on': ('制御', 'ON'), 'power:off': ('制御', 'OFF'),
    'slit:open': ('ドーム', '開'), 'slit:close': ('ドーム', '閉'),
    'slit:stop': ('ドーム', '停止'),
    'sidereal:on': ('望遠鏡', '恒星'), 'sidereal:off': ('望遠鏡', '停止'),
}
ACTION_TABS = {
    'power:on': '制御', 'power:off': '制御',
    'slit:open': 'ドーム', 'slit:close': 'ドーム', 'slit:stop': 'ドーム',
    'sidereal:on': '望遠鏡', 'sidereal:off': '望遠鏡',
}


def select_rotation_button(windows, pid, action, parent_of, rect_of, require_enabled=True):
    captions = {'dome:right': '右回転', 'dome:left': '左回転', 'dome:stop': '停止'}
    if action not in captions:
        raise ValueError(action)
    forms = [w for w in windows if w.pid == pid and w.class_name == 'TFormMenu'
             and w.visible and w.enabled]
    if len(forms) != 1:
        raise RuntimeError('MoTメインフォームを特定できません')
    buttons = [w for w in windows if w.pid == pid and w.class_name == 'TButton'
               and w.visible and parent_of(w.hwnd) == forms[0].hwnd]
    sides = []
    for caption in ('左回転', '右回転'):
        matches = [w for w in buttons if w.caption.strip() == caption]
        if len(matches) != 1:
            raise RuntimeError('回転ボタンが一意ではありません')
        sides.append(matches[0])
    left, right = [rect_of(w.hwnd) for w in sides]
    stops = [w for w in buttons if w.caption.strip() == '停止'
             and left[2] <= rect_of(w.hwnd)[0] < rect_of(w.hwnd)[2] <= right[0]
             and abs(rect_of(w.hwnd)[1] - left[1]) <= 3
             and abs(rect_of(w.hwnd)[1] - right[1]) <= 3]
    if len(stops) != 1:
        raise RuntimeError('左右回転の間にある停止ボタンを特定できません')
    chosen = {'dome:left': sides[0], 'dome:right': sides[1], 'dome:stop': stops[0]}[action]
    if require_enabled and not chosen.enabled:
        raise RuntimeError('対象回転ボタンは無効です')
    return chosen


def select_tab_button(windows, pid, action, parent_of, rect_of=None):
    """Require the button to belong to the named, visible tab and Master form."""
    if action not in TAB_ACTIONS:
        raise ValueError(f'未対応操作: {action}')
    tab_name, caption = TAB_ACTIONS[action]
    indexed = {w.hwnd: w for w in windows if w.pid == pid}
    matches = []
    for button in indexed.values():
        if button.class_name not in ('TButton', 'Button') or button.caption.strip() != caption:
            continue
        if not button.visible or (not button.enabled and action != 'sidereal:off'):
            continue
        current = button.hwnd
        seen = set()
        tab_found = form_found = False
        while current in indexed and current not in seen:
            seen.add(current)
            item = indexed[current]
            if not item.visible or (not item.enabled and current != button.hwnd):
                break
            if item.class_name == 'TTabSheet':
                if item.caption.strip() != tab_name:
                    break
                tab_found = True
            if item.class_name == 'TFormMenu':
                form_found = True
                break
            current = parent_of(current)
        if tab_found and form_found:
            matches.append(button)
    if action == 'sidereal:off' and matches and rect_of is not None:
        anchors = [w for w in indexed.values() if w.caption.strip() == '恒星'
                   and w.class_name == 'TButton' and w.visible
                   and parent_of(w.hwnd) == parent_of(matches[0].hwnd)]
        if len(anchors) != 1:
            raise RuntimeError('恒星ボタンを一意に照合できません')
        anchor = rect_of(anchors[0].hwnd)
        def distance(button):
            rect = rect_of(button.hwnd)
            return ((rect[0]+rect[2]-anchor[0]-anchor[2]) ** 2
                    + (rect[1]+rect[3]-anchor[1]-anchor[3]) ** 2)
        matches.sort(key=distance)
        if len(matches) > 1 and distance(matches[0]) == distance(matches[1]):
            raise RuntimeError('最も近い停止ボタンが同距離で複数あります')
        matches = matches[:1]
    if len(matches) != 1 or not matches[0].enabled:
        raise RuntimeError(f'{tab_name}タブの有効な「{caption}」を一意に特定できません ({len(matches)}件)。対象タブを表示してください')
    return matches[0]


class NishimuraController:
    """Master2018への操作と現在位置取得を提供する。"""
    def __init__(self, pid: int | None = None):
        self.pid = pid
        self.reader = None
        self.bridge = None

    @staticmethod
    def master_pids() -> list[int]:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
             '@(Get-Process -Name Master2018 -ErrorAction SilentlyContinue).Id'],
            capture_output=True, text=True, check=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return [int(line) for line in result.stdout.split() if line.strip().isdigit()]

    def _ensure_pid(self):
        if self.pid is None:
            pids = self.master_pids()
            if len(pids) != 1:
                raise RuntimeError(f'Master2018のPIDを一意に特定できません: {pids}')
            self.pid = pids[0]
        return self.pid

    def start_master(self):
        cli = _load('nishimura_cli')
        exe = cli.verify_executable(cli.DEFAULT_EXE)
        cli.ensure_not_running()
        process = subprocess.Popen([str(exe)], cwd=str(exe.parent))
        self.pid = process.pid
        return {'launched_pid': process.pid, 'controller_ready': 'unconfirmed'}

    def send(self, command: str, ra_hours=None, dec_deg=None):
        cli = _load('nishimura_cli')
        payload = cli.build_payload(command, ra_hours, dec_deg)
        return cli.send_payload(payload)

    def send_correction(self, ra_arcsec: float, dec_arcsec: float):
        """client_senderと同じTCP経路で相対RA/Dec補正を1回送信する。

        引数の単位は秒角。絶対RA/Decを送る ``send('track', ...)`` とは
        経路・命令形式が異なるため、追尾補正と実機試験ではこちらを使う。
        """
        sender = _load('base__client_sender')
        return sender.MoTSender().send_correction(ra_arcsec, dec_arcsec)

    def click(self, action: str):
        gui = _load('master_gui')
        pid = self._ensure_pid()
        # Reader verifies the running executable hash with read-only access.
        with _load('master_position').Reader(pid):
            from ctypes import wintypes
            native = gui.Win32()
            native.u.GetParent.argtypes = [wintypes.HWND]
            native.u.GetParent.restype = wintypes.HWND
            import ctypes
            native.u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            def rect_of(hwnd):
                rect = wintypes.RECT()
                if not native.u.GetWindowRect(hwnd, ctypes.byref(rect)):
                    raise ctypes.WinError()
                return rect.left, rect.top, rect.right, rect.bottom
            parent_of = lambda hwnd: native.u.GetParent(hwnd)
            # 対象ボタンが属するタブを先に選択する。旧実装は現在表示中の
            # タブだけを走査していたため、別タブの操作が失敗していた。
            if action in ACTION_TABS:
                self._select_tab_with_native(native, pid, ACTION_TABS[action])
            selector = select_rotation_button if action.startswith('dome:') else select_tab_button
            button = selector(native.windows(pid), pid, action, parent_of, rect_of)
            again = selector(native.windows(pid), pid, action, parent_of, rect_of)
            if button != again:
                raise RuntimeError('照合中にGUIが変化しました。操作を中止しました')
            native.click(button.hwnd, 2000)
            return {'action': action, 'clicked': True, 'hwnd': button.hwnd,
                    'mechanical_completion': 'unconfirmed', 'automatic_retry': False}

    def _select_tab_with_native(self, native, pid, name):
        """Select and verify one visible Master2018 operation tab."""
        from ctypes import wintypes
        import ctypes
        native.u.GetParent.argtypes = [wintypes.HWND]
        native.u.GetParent.restype = wintypes.HWND
        forms = [w for w in native.windows(pid) if w.class_name == 'TFormMenu'
                 and w.visible and w.enabled]
        pages = [w for w in native.windows(pid) if w.class_name == 'TPageControl'
                 and w.visible and w.enabled and len(forms) == 1
                 and native.u.GetParent(w.hwnd) == forms[0].hwnd]
        if len(pages) != 1:
            raise RuntimeError('操作タブを一意に特定できません')
        tabs = [w for w in native.windows(pid) if w.class_name == 'TTabSheet'
                and native.u.GetParent(w.hwnd) == pages[0].hwnd]
        target = [w for w in tabs if w.caption.strip() == name]
        if len(target) != 1:
            raise RuntimeError(f'{name}タブを一意に特定できません')
        # TCM_SETCURSEL: TPageControlの選択タブ変更。メモリは変更しない。
        index = tabs.index(target[0])
        result = ctypes.c_size_t()
        if not native.u.SendMessageTimeoutW(pages[0].hwnd, 0x130C, index, 0,
                                            0x22, 2000, ctypes.byref(result)):
            raise RuntimeError(f'{name}タブの選択に失敗しました')

    def select_tab(self, name):
        """Select a tab through its standard control; verify the resulting caption."""
        import ctypes
        from ctypes import wintypes
        index = {'望遠鏡': 0, 'ドーム': 1, '制御': 2}[name]
        pid = self._ensure_pid()
        with _load('master_position').Reader(pid):
            native = _load('master_gui').Win32()
            native.u.GetParent.argtypes = [wintypes.HWND]
            native.u.GetParent.restype = wintypes.HWND
            windows = native.windows(pid)
            forms = [w for w in windows if w.class_name == 'TFormMenu' and w.visible and w.enabled]
            pages = [w for w in windows if w.class_name == 'TPageControl' and w.visible
                     and w.enabled and len(forms) == 1 and native.u.GetParent(w.hwnd) == forms[0].hwnd]
            if len(pages) != 1:
                raise RuntimeError('操作タブを一意に特定できません')
            result = ctypes.c_size_t()
            # TCM_SETCURFOCUS uses an integer index, no remote-memory writes.
            if not native.u.SendMessageTimeoutW(pages[0].hwnd, 0x1330, index, 0,
                                               0x22, 2000, ctypes.byref(result)):
                raise RuntimeError('タブ選択に失敗しました')
            tabs = [w for w in native.windows(pid) if w.class_name == 'TTabSheet'
                    and w.visible and native.u.GetParent(w.hwnd) == pages[0].hwnd]
            if len(tabs) != 1 or tabs[0].caption.strip() != name:
                raise RuntimeError('タブ切替後の表示名が一致しません。機器操作は中止します')
            return name

    def read_position(self):
        position = _load('master_position')
        pid = self._ensure_pid()
        if self.reader is None:
            self.reader = position.Reader(pid)
        return self.reader.read_once()

    def close(self):
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        self.pid = None

    @staticmethod
    def unsupported(action):
        raise NotImplementedError(
            f'{action} は既存Master2018の確認済みAPI／GUIボタンが未特定のため、安全のため実行しません')
