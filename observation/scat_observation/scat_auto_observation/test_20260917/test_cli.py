"""実機を使わない試験。ソケット・プロセス起動はモックへ置き換える。"""
import contextlib
import io
import json
import struct
import unittest
from unittest.mock import patch

import nishimura_cli as cli
import master_position as position


class CommandTests(unittest.TestCase):
    def run_cli(self, args):
        # 試験中に標準出力へ計画JSONが大量に出ないよう捕捉する。
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return cli.main(args)

    def test_coordinates_are_json_reals(self):
        data = json.loads(cli.build_payload('track', 12, -30))
        self.assertIsInstance(data['ra'], float)
        self.assertIsInstance(data['dec'], float)
        self.assertEqual(data['pmra'], 0.0)
        self.assertEqual(data['pmdec'], 0.0)
        self.assertEqual(data['ra'], 12.0)  # RAを勝手に度へ変換していない。

    def test_invalid_coordinates(self):
        for ra, dec in [(-1, 0), (24, 0), (12, 91), (12, -91), (float('nan'), 0), (0, float('inf'))]:
            with self.subTest(ra=ra, dec=dec), self.assertRaises(ValueError):
                cli.build_payload('track', ra, dec)

    def test_dry_run_never_opens_socket(self):
        with patch.object(cli.socket, 'create_connection') as connect:
            self.assertEqual(self.run_cli(['track', '--ra-hours', '12.5', '--dec-deg', '30']), 0)
            connect.assert_not_called()

    def test_dry_start_never_launches(self):
        with patch.object(cli.subprocess, 'Popen') as launch:
            self.assertEqual(self.run_cli(['start']), 0)
            launch.assert_not_called()

    def test_execute_sends_exact_payload_once(self):
        with patch.object(cli, 'verify_executable'), patch.object(cli.socket, 'create_connection') as connect:
            self.assertEqual(self.run_cli(['track', '--ra-hours', '12.5', '--dec-deg', '-30', '--execute']), 0)
            connect.assert_called_once_with(('127.0.0.1', 8744), timeout=3.0)
            connect.return_value.__enter__.return_value.sendall.assert_called_once_with(
                b'{"command":"track","ra":12.5,"dec":-30.0,"pmra":0.0,"pmdec":0.0}')

    def test_connection_failure_never_retries(self):
        with patch.object(cli, 'verify_executable'), patch.object(cli.socket, 'create_connection', side_effect=OSError('mock failure')) as connect:
            self.assertEqual(self.run_cli(['stop', '--execute']), 1)
            connect.assert_called_once()

    def test_unknown_version_never_connects(self):
        with patch.object(cli, 'verify_executable', side_effect=ValueError('hash mismatch')), patch.object(cli.socket, 'create_connection') as connect:
            self.assertEqual(self.run_cli(['stop', '--execute']), 1)
            connect.assert_not_called()

    def test_gui_actions_are_dry_run_by_default(self):
        with patch.object(cli, 'click_action') as click:
            self.assertEqual(self.run_cli(['dome-link', 'on', '--pid', '123']), 0)
            self.assertEqual(self.run_cli(['slit', 'open', '--pid', '123']), 0)
            click.assert_not_called()

    def test_gui_actions_click_master_handler_once(self):
        with patch.object(cli, 'verify_executable'), patch.object(cli, 'click_action', return_value={'clicked': True}) as click:
            self.assertEqual(self.run_cli(['dome-link', 'on', '--pid', '123', '--execute']), 0)
            self.assertEqual(self.run_cli(['slit', 'open', '--pid', '123', '--execute']), 0)
            self.assertEqual(click.call_count, 2)
            self.assertEqual(click.call_args_list[0].args, (123, 'dome-link:on'))
            self.assertEqual(click.call_args_list[1].args, (123, 'slit:open'))

    def test_invalid_timeout_never_connects(self):
        with patch.object(cli.socket, 'create_connection') as connect:
            self.assertEqual(self.run_cli(['stop', '--timeout', '0', '--execute']), 1)
            connect.assert_not_called()

    def test_stop_and_lifecycle_payloads(self):
        for command in ['stop', 'startup', 'ending']:
            self.assertEqual(json.loads(cli.build_payload(command)), {'command': command})

    def test_unrecognized_command_is_rejected(self):
        with self.assertRaises(ValueError):
            cli.build_payload('DSO#')

    def test_start_execute_is_mocked(self):
        with patch.object(cli, 'verify_executable', return_value=cli.DEFAULT_EXE), patch.object(cli, 'ensure_not_running'), patch.object(cli.subprocess, 'Popen') as launch:
            launch.return_value.pid = 1234
            self.assertEqual(self.run_cli(['start', '--execute']), 0)
            launch.assert_called_once_with([str(cli.DEFAULT_EXE)], cwd=str(cli.DEFAULT_EXE.parent))


class PositionTests(unittest.TestCase):
    def test_layout_and_freshness(self):
        data = bytearray(position.BLOCK_SIZE)
        # 変数表とは独立に、解析済みオフセットへ異なる値を詰めて取り違えを検出する。
        struct.pack_into('<6d', data, 0, 180.0, 45.0, 12.5, -20.0, 12.6, -19.9)
        struct.pack_into('<i', data, 72, 1)
        struct.pack_into('<i', data, 108, 3)
        struct.pack_into('<i', data, 160, 7)
        sample = position.decode(data)
        self.assertEqual(sample['ra_j2000_hours'], 12.5)
        self.assertEqual(sample['dec_j2000_deg'], -20.0)
        self.assertEqual(sample['azimuth_software_deg'], 180.0)
        self.assertEqual(sample['altitude_software_deg'], 45.0)
        self.assertEqual(sample['raw']['DomRotAutoFlag'], 1)
        self.assertEqual(sample['raw']['DomSlSt'], 3)
        self.assertEqual(sample['raw']['ComStat'], 7)
        self.assertEqual(sample['controller_data_freshness'], 'unknown')

    def test_bad_memory_samples(self):
        with self.assertRaises(ValueError):
            position.decode(b'')
        data = bytearray(position.BLOCK_SIZE)
        struct.pack_into('<d', data, 0, float('nan'))
        with self.assertRaises(ValueError):
            position.decode(data)


if __name__ == '__main__':
    unittest.main()
