"""Generate reproducible Stage-1 demo imagery. These are synthetic visual test scenes."""
from pathlib import Path
import json
import cv2
import numpy as np

OUT=Path(__file__).parents[1]/"datasets/demo"; OUT.mkdir(parents=True,exist_ok=True)
rng=np.random.default_rng(20250820)
y,x=np.mgrid[:512,:512]
base=(38+33*np.exp(-((x-260)**2+(y-250)**2)/(2*150**2))).astype(np.float32)
for cx,cy,r,depth in [(140,160,58,24),(345,315,78,30),(390,115,31,18),(160,390,38,14)]:
    d=np.hypot(x-cx,y-cy); base += depth*np.exp(-((d-r)/8)**2)-depth*.6*np.exp(-(d/(r*.72))**4)
base+=rng.normal(0,2.5,base.shape); base=np.uint8(np.clip(base,0,255))
cv2.imwrite(str(OUT/'base.png'),base)
clean=cv2.addWeighted(base,1.35,cv2.GaussianBlur(base,(0,0),2),-.35,4); cv2.imwrite(str(OUT/'clean_enhancement.png'),clean)
altered=clean.copy(); cv2.circle(altered,(272,128),19,150,-1); cv2.circle(altered,(266,122),14,72,-1); cv2.imwrite(str(OUT/'synthetic_alteration.png'),altered)
low=cv2.convertScaleAbs(base,alpha=1.01,beta=1); cv2.imwrite(str(OUT/'low_change.png'),low)
manifest={"schema_version":"1.0","notice":"Procedurally generated synthetic visual test scenes; not lunar mission data.","seed":20250820,"base":"base.png","cases":[{"id":"clean","enhanced":"clean_enhancement.png","intent":"deterministic unsharp masking"},{"id":"alteration","enhanced":"synthetic_alteration.png","intent":"controlled artificial circular terrain-like insertion"},{"id":"low_change","enhanced":"low_change.png","intent":"small global intensity transform"}]}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
