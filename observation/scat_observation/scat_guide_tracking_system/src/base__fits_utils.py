import os
from pathlib import Path
from astropy.io import fits
from .base__point_detector import image2d


def read_image(path):
    return image2d(fits.getdata(path))


def save_image(path, image, exposure):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp.fits')
    hdu = fits.PrimaryHDU(image)
    hdu.header['EXPTIME'] = exposure
    hdu.writeto(temporary, overwrite=True)
    os.replace(temporary, path)
