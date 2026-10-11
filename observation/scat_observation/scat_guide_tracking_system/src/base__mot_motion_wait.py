"""MoTログの今回分だけを読み、guide→方向移動→Q#→OK 36を照合する。

機械的な整定や恒星追尾ONを保証するものではない。送信前に生成すること。
"""
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path


class MotionLogWaiter:
    def __init__(self, directory, ra, dec):
        self.path = Path(directory) / datetime.now().strftime('MonitorLog%Y%m%d.log')
        # 読み取り不可・ログ未生成なら移動を送る前に失敗させる。
        with self.path.open('rb') as stream:
            stream.seek(0, 2)
            self.offset = stream.tell()
        self.command = (float(ra), float(dec))
        self.direction = ('MW' if ra > 0 else 'ME') if ra else ('MS' if dec > 0 else 'MN')
        self.state = 'guide'
        self.allowed_directions = set()
        if ra:
            self.allowed_directions.add('MW#' if ra > 0 else 'ME#')
        if dec:
            self.allowed_directions.add('MS#' if dec > 0 else 'MN#')
        self.seen_directions = set()
        self.pending = b''

    def feed(self, line):
        """ASCII部分だけで判定し、ログの日本語エンコーディングには依存しない。"""
        if 'guideOffset()' in line:
            try:
                payload = json.loads(line[line.index('{'):])
                actual = (float(payload['ra offset']), float(payload['dec offset']))
            except (ValueError, KeyError) as exc:
                raise RuntimeError('MoT guideログを解釈できません') from exc
            matches = all(math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-7)
                          for a, b in zip(actual, self.command))
            if self.state != 'guide' or not matches:
                raise RuntimeError(f'別のguide命令が混在しています。補正を中止します'
                                   f'（送信={self.command}, ログ={actual}, 段階={self.state}）')
            self.state = 'direction'
        match = re.search(r' - Send (\S+)', line)
        if match:
            sent = match.group(1)
            allowed = getattr(self, 'allowed_directions', {self.direction + '#'})
            seen = getattr(self, 'seen_directions', set())
            if self.state in ('direction', 'stop') and sent in allowed and sent not in seen:
                seen.add(sent)
                self.seen_directions = seen
                self.state = 'stop'
            elif self.state == 'stop' and sent == 'Q#':
                self.state = 'ack'
            else:
                # 他の操作を自身の移動終了と誤認しない。重複命令も拒否する。
                raise RuntimeError(f'MoTログに予期しない送信: {sent}（待機段階={self.state}）')
        if self.state == 'ack' and re.search(r' - Read OK 36\s*$', line):
            self.state = 'done'
        return self.state == 'done'

    def wait(self, cancel, timeout=30., tracking_status=None,
             tracking_timeout=10., poll_sec=.2, settle_sec=0.):
        deadline = time.monotonic() + timeout
        while not cancel.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError(f'MoT停止応答待ちがタイムアウトしました（{self.state}）')
            if self.path.stat().st_size < self.offset:
                raise RuntimeError('MoTログが切り詰められました。校正中止')
            with self.path.open('rb') as stream:
                stream.seek(self.offset)
                chunk = stream.read()
                self.offset = stream.tell()
            self.pending += chunk
            while b'\n' in self.pending:
                line, self.pending = self.pending.split(b'\n', 1)
                if self.feed(line.decode('ascii', errors='replace')):
                    if tracking_status is not None:
                        deadline_track = time.monotonic() + tracking_timeout
                        last_status = None
                        while not cancel.is_set() and time.monotonic() < deadline_track:
                            last_status = tracking_status()
                            if last_status is None:
                                raise RuntimeError(
                                    '追尾状態未確認のため、補正を保留します')
                            if last_status == 'track':
                                if settle_sec and cancel.wait(settle_sec):
                                    raise RuntimeError('恒星追尾復帰待ちを中止しました')
                                return
                            cancel.wait(poll_sec)
                        raise TimeoutError(
                            f'移動完了後に恒星追尾へ復帰しませんでした（状態={last_status!r}）')
                    return
            cancel.wait(.1)
        raise RuntimeError('停止応答待ちを中止しました（自動再送なし）')
