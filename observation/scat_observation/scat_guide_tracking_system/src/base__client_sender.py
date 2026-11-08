"""MoT TCP sender. Importing this module never opens a connection."""
import argparse
import json
import math
import socket
import time


class MoTSender:
    def __init__(self, host='10.91.80.225', port=8744, timeout=5., expected_response=''):
        if not host or type(port) is not int or not 1 <= port <= 65535 or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('MoT接続設定が不正です')
        self.host, self.port = host, port
        self.timeout, self.expected_response = timeout, expected_response

    def send_correction(self, ra, dec):
        """Send relative RA/Dec offsets in arcseconds, without unit conversion.

        This is the single socket protocol used by both the app's tracking
        correction and manual hardware tests.
        """
        if not math.isfinite(ra) or not math.isfinite(dec):
            raise ValueError('RA/Dec補正量は有限値が必要です')
        payload = json.dumps({'command': 'guide', 'ra offset': float(ra),
                              'dec offset': float(dec)}, allow_nan=False).encode('utf-8')
        return self._send_payload(payload)

    def send_target(self, ra_hours, dec_deg):
        """J2000絶対座標をtrackで指定。RAは時、Decは度。自動再送しない。"""
        if not math.isfinite(ra_hours) or not 0 <= ra_hours < 24:
            raise ValueError('RAは0以上24未満の有限値（時）を指定してください')
        if not math.isfinite(dec_deg) or not -90 <= dec_deg <= 90:
            raise ValueError('Decは-90〜90度の有限値を指定してください')
        return self._send_payload(json.dumps(dict(command='track', ra=float(ra_hours),
            dec=float(dec_deg), pmra=0.0, pmdec=0.0), allow_nan=False).encode('utf-8'))

    def _send_payload(self, payload):
        # One request per connection, no delimiter, as in the supplied script.
        # Never retry: the mount may already have applied an offset on timeout.
        deadline = time.monotonic() + self.timeout
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as connection:
            connection.settimeout(max(.001, deadline - time.monotonic()))
            connection.sendall(payload)
            if self.expected_response:
                expected = self.expected_response.encode('utf-8')
                received = bytearray()
                while len(received) < len(expected):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('MoT応答がタイムアウトしました')
                    connection.settimeout(remaining)
                    part = connection.recv(len(expected) - len(received))
                    if not part:
                        break
                    received.extend(part)
                if bytes(received) != expected:
                    raise RuntimeError(f'MoT応答が期待値と異なります: {bytes(received)!r}')
                return received.decode('utf-8')
            connection.settimeout(max(.001, deadline - time.monotonic()))
            response = connection.recv(4096)
            if not response.strip():
                raise ConnectionError('MoTから応答を受信できませんでした')
            # Original code specifies neither response framing nor success schema.
            return response.decode('utf-8', errors='replace')


def main():
    parser = argparse.ArgumentParser(description='MoTへ相対RA/Dec補正を秒角で送信')
    parser.add_argument('ra', type=float, help='RA相対補正 [arcsec]')
    parser.add_argument('dec', type=float, help='Dec相対補正 [arcsec]')
    parser.add_argument('--host', default='10.91.80.225')
    parser.add_argument('--port', type=int, default=8744)
    args = parser.parse_args()
    print(MoTSender(args.host, args.port).send_correction(args.ra, args.dec))


if __name__ == '__main__':
    main()
