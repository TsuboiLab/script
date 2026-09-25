import os
import time
import uuid
from pathlib import Path
from astropy.io import fits
from .base__point_detector import image2d


def read_image(path):
    return image2d(fits.getdata(path))


def save_image(path, image, exposure):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.stem}.{uuid.uuid4().hex}.tmp.fits')
    hdu = fits.PrimaryHDU(image)
    hdu.header['EXPTIME'] = exposure
    hdu.writeto(temporary, overwrite=False)
    last_error = None
    for attempt in range(5):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(.1 * (attempt + 1))
    # 保存先が他プロセスにロックされている場合、撮像ワーカーを停止しない。
    try:
        temporary.unlink(missing_ok=True)
    finally:
        raise RuntimeError(f'画像保存先が使用中のため更新できません: {path}') from last_error
