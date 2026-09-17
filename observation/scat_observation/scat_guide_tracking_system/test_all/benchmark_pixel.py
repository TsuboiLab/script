from pathlib import Path
import sys,time,json,tomllib,platform
from time import perf_counter
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
t0=perf_counter()
import numpy as np
from src.base__fits_utils import read_image
from src.base__point_detector import detect_science_slit,point_sources,pixel_offset
imports=perf_counter()-t0
c=tomllib.loads((root/'.config').read_text(encoding='utf8'))
p=root/c['pixel_test_image_path']; roi=c['pixel_test_slit_roi']
t0=perf_counter(); im=read_image(p); read_first=perf_counter()-t0
t0=perf_counter(); slit=detect_science_slit(im,roi)['center']; slit_first=perf_counter()-t0
t0=perf_counter(); s=point_sources(im,threshold_sigma=c['threshold_sigma']); point_first=perf_counter()-t0
pos=np.array([s[0]['x'],s[0]['y']])
def bench(fn,n=40):
 values=[]
 for _ in range(n):
  t=perf_counter(); fn(); values.append((perf_counter()-t)*1000)
 return {'n':n,'median_ms':float(np.median(values)),'p95_ms':float(np.percentile(values,95)),'min_ms':min(values),'max_ms':max(values)}
def combined():
 a=read_image(p); center=detect_science_slit(a,roi)['center']; source=point_sources(a,threshold_sigma=c['threshold_sigma'])[0]; return pixel_offset([source['x'],source['y']],center)
results={'python':sys.version,'processor':platform.processor(),'shape':list(im.shape),'roi':roi,'import_ms':imports*1000,'first_ms':{'read':read_first*1000,'slit':slit_first*1000,'point':point_first*1000},'read':bench(lambda:read_image(p)),'slit':bench(lambda:detect_science_slit(im,roi)),'point':bench(lambda:point_sources(im,threshold_sigma=c['threshold_sigma'])),'offset':bench(lambda:pixel_offset(pos,slit),1000),'combined':bench(combined)}
print(json.dumps(results,indent=2))
(root/'test_all/pixel_offset_results/timing.json').write_text(json.dumps(results,indent=2),encoding='utf8')
