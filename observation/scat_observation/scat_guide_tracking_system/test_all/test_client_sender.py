import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.base__client_sender import MoTSender


class SenderTests(unittest.TestCase):
    def connection(self, response):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.recv.return_value = response
        return connection

    def test_exact_protocol(self):
        conn = self.connection(b'OK')
        with patch('src.base__client_sender.socket.create_connection', return_value=conn) as factory:
            self.assertEqual(MoTSender().send_correction(1.25, -2.5), 'OK')
        factory.assert_called_once_with(('10.91.80.225', 8744), timeout=5.)
        payload = conn.sendall.call_args.args[0]
        self.assertEqual(json.loads(payload), {'command': 'guide', 'ra offset': 1.25, 'dec offset': -2.5})
        conn.__exit__.assert_called_once()

    def test_empty_response(self):
        conn = self.connection(b'')
        with patch('src.base__client_sender.socket.create_connection', return_value=conn):
            with self.assertRaises(ConnectionError):
                MoTSender().send_correction(1, 2)

    def test_timeout_never_retries(self):
        conn = self.connection(b'')
        conn.recv.side_effect = socket.timeout('timeout')
        with patch('src.base__client_sender.socket.create_connection', return_value=conn) as factory:
            with self.assertRaises(TimeoutError):
                MoTSender().send_correction(1, 2)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(conn.sendall.call_count, 1)

    def test_fragmented_expected_response(self):
        conn = self.connection(b'')
        conn.recv.side_effect = [b'O', b'K']
        with patch('src.base__client_sender.socket.create_connection', return_value=conn):
            self.assertEqual(MoTSender(expected_response='OK').send_correction(1, 2), 'OK')

    def test_rejected_response(self):
        conn = self.connection(b'NO')
        with patch('src.base__client_sender.socket.create_connection', return_value=conn):
            with self.assertRaises(RuntimeError):
                MoTSender(expected_response='OK').send_correction(1, 2)

    def test_nonfinite_does_not_connect(self):
        with patch('src.base__client_sender.socket.create_connection') as factory:
            with self.assertRaises(ValueError):
                MoTSender().send_correction(float('nan'), 0)
        factory.assert_not_called()
