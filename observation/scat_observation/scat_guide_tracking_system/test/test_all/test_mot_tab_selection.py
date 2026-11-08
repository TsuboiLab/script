"""Offline checks: these tests never connect to hardware."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import json
import tomllib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.base__nishimura_controler import select_tab_button, TAB_ACTIONS
from src.base__client_sender import MoTSender


def window(hwnd, cls, text, enabled=True):
    return SimpleNamespace(hwnd=hwnd, class_name=cls, caption=text,
                           pid=42, visible=True, enabled=enabled)


class MoTTests(unittest.TestCase):
    def test_sidereal_stop_uses_nearest_even_when_disabled(self):
        windows = [window(1, 'TFormMenu', 'Master'), window(2, 'TTabSheet', '望遠鏡'),
                   window(3, 'TButton', '恒星'), window(4, 'TButton', '停止'),
                   window(5, 'TButton', '停止')]
        parents = {2: 1, 3: 2, 4: 2, 5: 2}
        rects = {3: (100, 100, 160, 125), 4: (50, 125, 160, 150), 5: (100, 300, 160, 325)}
        self.assertEqual(select_tab_button(windows, 42, 'sidereal:off', parents.get, rects.get).hwnd, 4)
        windows[3].enabled = False
        with self.assertRaises(RuntimeError):
            select_tab_button(windows, 42, 'sidereal:off', parents.get, rects.get)

    def test_each_action_is_scoped_to_its_tab(self):
        for action, (tab, caption) in TAB_ACTIONS.items():
            with self.subTest(action=action):
                windows = [window(1, 'TFormMenu', 'Master'),
                           window(2, 'TTabSheet', tab),
                           window(3, 'TButton', caption),
                           window(4, 'TTabSheet', '別タブ'),
                           window(5, 'TButton', caption)]
                parents = {2: 1, 3: 2, 4: 1, 5: 4}
                self.assertEqual(select_tab_button(windows, 42, action, parents.get).hwnd, 3)
                windows[2].enabled = False
                with self.assertRaises(RuntimeError):
                    select_tab_button(windows, 42, action, parents.get)

    def test_duplicate_buttons_are_rejected(self):
        windows = [window(1, 'TFormMenu', 'Master'), window(2, 'TTabSheet', '制御'),
                   window(3, 'TButton', 'ON'), window(4, 'TButton', 'ON')]
        with self.assertRaises(RuntimeError):
            select_tab_button(windows, 42, 'power:on', {2: 1, 3: 2, 4: 2}.get)

    def test_arcsecond_configuration_and_wire_values(self):
        with (ROOT / '.config').open('rb') as source:
            config = tomllib.load(source)
        self.assertEqual(config['matrix'], [[1., 0.], [0., 1.]])
        self.assertEqual(config['max_correction'], 0)
        with patch('src.base__client_sender.socket.create_connection') as connect:
            connection = connect.return_value.__enter__.return_value
            connection.recv.return_value = b'ok'
            MoTSender().send_correction(1., -2.)
            payload = json.loads(connection.sendall.call_args.args[0])
            self.assertEqual(payload['ra offset'], 1.)
            self.assertEqual(payload['dec offset'], -2.)


if __name__ == '__main__':
    unittest.main()
