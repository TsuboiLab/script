"""Offline slit line-profile inspection; never connects to hardware."""
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
from astropy.io import fits
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
a = fits.getdata(ROOT/'pictures/02_slit_guide_images/slit_guide_image_loop.fit').astype(float)
h, w = a.shape
cx, cy = w*3/5, h*3/7
ys = np.arange(int(cy-150), int(cy+150))
xs = np.arange(int(cx-110), int(cx+110))
smooth = ndi.gaussian_filter(a, 1)
scores = []
for slope in np.linspace(-.25, .25, 51):
    lines = xs[None, :] + slope*(ys[:, None]-cy)
    rows = np.broadcast_to(ys[:, None], lines.shape)
    center = ndi.map_coordinates(smooth, [rows, lines], order=1)
    left = ndi.map_coordinates(smooth, [rows, lines-9], order=1)
    right = ndi.map_coordinates(smooth, [rows, lines+9], order=1)
    response = (left+right)/2-center
    # Suppress bright-star wings and impulsive noise without inventing a line.
    response = np.clip(response, -100, 100)
    profile = response.mean(axis=0)
    k = np.argmax(profile)
    scores.append((float(profile[k]), float(xs[k]), float(slope)))
print(sorted(scores, reverse=True)[:10], flush=True)
score, x, slope = max(scores)
fig, ax = plt.subplots(1, 2, figsize=(11, 8))
ax[0].imshow(a, cmap='gray', vmin=np.percentile(a, 10), vmax=np.percentile(a,90))
ax[0].plot(x+slope*(ys-cy), ys, color='yellow')
ax[0].set_xlim(cx-130,cx+130); ax[0].set_ylim(cy+200,cy-200)
line = x+slope*(ys-cy)
values = ndi.map_coordinates(smooth,[ys,line],order=1)
sides = (ndi.map_coordinates(smooth,[ys,line-9],order=1)+ndi.map_coordinates(smooth,[ys,line+9],order=1))/2
ax[1].plot(ys, ndi.gaussian_filter1d(sides-values,5))
ax[1].axhline(0,color='gray'); ax[1].set_title(f'x={x:.1f}, slope={slope:.3f}, contrast={score:.2f}')
fig.savefig(Path(__file__).with_name('slit_hint_profile.png'))
