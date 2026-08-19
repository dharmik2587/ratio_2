"""Create small, geospatially explicit derivatives from downloaded NASA SVS lunar products.

Sources are not downloaded by this script. Expected source hashes are recorded in the
manifest. Derived controlled enhancement/hazard outputs are DEMO, not mission products.
"""
from pathlib import Path
import hashlib,json
import cv2,numpy as np,rasterio
from rasterio.transform import from_bounds
ROOT=Path(__file__).parents[1];src=ROOT/'datasets/real/source';out=ROOT/'datasets/real/derived';out.mkdir(parents=True,exist_ok=True)
image=cv2.imread(str(src/'lroc_color_2k.jpg'),cv2.IMREAD_COLOR)
with rasterio.open(src/'ldem_4.tif') as ds:dem_km=ds.read(1)
if image is None or image.shape[:2]!=(1024,2048) or dem_km.shape!=(720,1440):raise RuntimeError('Unexpected NASA source dimensions')
# Common geographic footprint: longitude -45..45, latitude -45..45.
image_crop=image[256:768,768:1280]; dem_m=(dem_km[180:540,540:900]*1000).astype('float32')
cv2.imwrite(str(out/'lroc_nearside_original.png'),image_crop)
sharpened=cv2.addWeighted(image_crop,1.18,cv2.GaussianBlur(image_crop,(0,0),1.2),-.18,0);cv2.imwrite(str(out/'lroc_nearside_enhanced.png'),sharpened)
hazard=sharpened.copy();cv2.circle(hazard,(385,145),20,(225,225,225),-1);cv2.circle(hazard,(379,139),14,(35,35,35),-1);cv2.imwrite(str(out/'lroc_nearside_synthetic_hazard.png'),hazard)
R=1737400.0;extent=R*np.pi/4;transform=from_bounds(-extent,-extent,extent,extent,dem_m.shape[1],dem_m.shape[0]);crs=f'+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +R={R} +units=m +no_defs'
with rasterio.open(out/'lola_ldem4_nearside_dem.tif','w',driver='GTiff',height=360,width=360,count=1,dtype='float32',crs=crs,transform=transform,nodata=-99999.0,compress='deflate') as dst:dst.write(dem_m,1)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest={
 'schema_version':'2.0','entries':[
  {'id':'NASA_SVS_LRO_NEARSIDE_45','classification':'REAL','mission':'Lunar Reconnaissance Orbiter','instrument':'LROC WAC composite / LOLA','product_id':'NASA_SVS_4720_LROC_COLOR_2K_AND_LDEM4','data_type':'IMAGE_DEM_PAIR','source':'https://svs.gsfc.nasa.gov/4720','local_path':'datasets/real/derived/lola_ldem4_nearside_dem.tif','image_path':'datasets/real/derived/lroc_nearside_original.png','resolution_m_per_pixel':7580.83760603737,'coordinate_reference_system':crs,'acquisition_date':None,'processing_level':'NASA SVS rendering assets; RATIO geographic crop','coverage':{'longitude_deg':[-45,45],'latitude_deg':[-45,45],'common_footprint':True},'license_notes':'NASA SVS materials; source page credits apply. Usage constraints not independently adjudicated by RATIO.','description':'Real LRO-derived image composite and LOLA-derived elevation crop. The color asset is optimized for rendering, not a calibrated science image.','image_dimensions':[512,512],'reference_dimensions':[360,360],'metadata_alignment_reliable':True,'illumination':None,
   'hashes':{'source_image_sha256':sha(src/'lroc_color_2k.jpg'),'source_dem_sha256':sha(src/'ldem_4.tif'),'derived_image_sha256':sha(out/'lroc_nearside_original.png'),'derived_dem_sha256':sha(out/'lola_ldem4_nearside_dem.tif')}},
  {'id':'NASA_SVS_LRO_SYNTHETIC_HAZARD','classification':'SYNTHETIC_DEMO','mission':'Lunar Reconnaissance Orbiter (base data)','instrument':'LROC WAC composite / LOLA','product_id':'RATIO_CONTROLLED_HAZARD_ON_NASA_SVS_4720','data_type':'IMAGE_DEM_PAIR','source':'https://svs.gsfc.nasa.gov/4720','local_path':'datasets/real/derived/lola_ldem4_nearside_dem.tif','image_path':'datasets/real/derived/lroc_nearside_synthetic_hazard.png','resolution_m_per_pixel':7580.83760603737,'coordinate_reference_system':crs,'acquisition_date':None,'processing_level':'Synthetic visual alteration on real-data-derived crop','coverage':{'longitude_deg':[-45,45],'latitude_deg':[-45,45],'common_footprint':True},'license_notes':'NASA base data with RATIO synthetic modification; not mission evidence.','description':'SYNTHETIC HAZARD DEMONSTRATION. Artificial visual structure is not present in the independent LOLA DEM.','image_dimensions':[512,512],'reference_dimensions':[360,360],'metadata_alignment_reliable':True,'illumination':None,
   'hashes':{'derived_image_sha256':sha(out/'lroc_nearside_synthetic_hazard.png'),'derived_dem_sha256':sha(out/'lola_ldem4_nearside_dem.tif')}}]}
(ROOT/'datasets/manifests/phase2_datasets.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'outputs':[str(p) for p in out.iterdir()],'manifest_entries':2},indent=2))
