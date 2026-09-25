"""Persist only slit calibration keys, retaining other TOML settings/comments."""
import os
import re
import tempfile
import tomllib
from pathlib import Path
import numpy as np


def validate_slit(center, shape):
    """保存する中心は(x, y)、画像サイズは(height, width)。範囲外は拒否する。"""
    center = np.asarray(center, dtype=float)
    if len(shape) != 2 or any(type(v) is not int or v <= 0 for v in shape):
        raise ValueError('保存済みスリット画像サイズが不正です')
    h, w = shape
    if center.shape != (2,) or not np.isfinite(center).all() or not (0 <= center[0] < w and 0 <= center[1] < h):
        raise ValueError('保存済みスリット中心が画像範囲外です')
    return center.tolist(), list(shape)


def save_slit(path, center, shape):
    """他の設定とコメントを保持し、検証済みTOMLを一時ファイルから置換する。"""
    center, shape = validate_slit(center, shape)
    path = Path(path)
    content = path.read_text(encoding='utf-8')
    for key, value in (('slit_initial_center_px', center), ('slit_initial_image_shape', shape)):
        line = f'{key} = {value}'
        pattern = rf'(?m)^{key}\s*=.*$'
        content = re.sub(pattern, lambda match: line, content) if re.search(pattern, content) else content.rstrip()+'\n'+line+'\n'
    tomllib.loads(content)
    fd, temporary = tempfile.mkstemp(prefix='.slit-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
