import json,math
from pathlib import Path
import numpy as np,pytest,rasterio
from rasterio.transform import from_origin
from ratio_core.dem import load_dem,clear_dem_cache,terrain_derivatives
from ratio_core.registration import fit_affine,transform_points,auto_dimension_registration
from ratio_core.physical import verify_region
from ratio_core.physical import gradient_alignment,resolution_adequacy,weighted_physical_support,unsupported_risk
from ratio_core.policy import evaluate_policy
from ratio_core.provenance import build_passport
from ratio_core.phase2_config import validate_phase2_config
import copy

CONFIG=json.loads((Path(__file__).parents[1]/'configs/phase2.json').read_text())

def write_dem(path,z,nodata=None):
    with rasterio.open(path,'w',driver='GTiff',height=z.shape[0],width=z.shape[1],count=1,dtype='float32',crs='EPSG:3857',transform=from_origin(0,z.shape[0]*10,10,10),nodata=nodata) as dst:dst.write(z.astype('float32'),1)
    clear_dem_cache();return load_dem(str(path))

def test_flat_dem_and_zero_alignment_unresolved(tmp_path):
    dem=write_dem(tmp_path/'flat.tif',np.full((40,40),12.0));d=terrain_derivatives(dem)
    assert np.nanmax(np.abs(d.slope_degrees))<1e-8
    assert np.nanmax(np.abs(d.gradient_magnitude))<1e-8
    score,status=gradient_alignment(np.ones((3,3)),np.zeros((3,3)),np.zeros((3,3)),np.zeros((3,3)))
    assert score is None and status=='GRADIENT_ALIGNMENT_UNRESOLVED'

def test_known_planar_slope_gradient_and_hillshade(tmp_path):
    y,x=np.mgrid[:50,:60];z=.2*(x*10)+.1*(y*10);dem=write_dem(tmp_path/'plane.tif',z);d=terrain_derivatives(dem)
    interior=np.s_[3:-3,3:-3]
    assert np.nanmean(d.gradient_x[interior])==pytest.approx(.2,abs=1e-5)
    assert np.nanmean(d.gradient_y[interior])==pytest.approx(.1,abs=1e-5)
    assert np.nanmean(d.slope_degrees[interior])==pytest.approx(math.degrees(math.atan(math.hypot(.2,.1))),abs=1e-4)
    assert np.nanmin(d.hillshade)>=0 and np.nanmax(d.hillshade)<=1

def test_dem_nodata_mask_and_valid_fraction(tmp_path):
    z=np.ones((20,20),np.float32);z[:10,:]=-9999;dem=write_dem(tmp_path/'nodata.tif',z,-9999)
    assert dem.valid_mask.mean()==.5 and not np.any(dem.elevation_m[dem.valid_mask]==-9999)

def test_gradient_alignment_cases():
    ones=np.ones((4,4));zeros=np.zeros((4,4))
    assert gradient_alignment(ones,zeros,ones,zeros)[0]==pytest.approx(1)
    assert gradient_alignment(ones,zeros,-ones,zeros)[0]==pytest.approx(1)
    assert gradient_alignment(ones,zeros,zeros,ones)[0]==pytest.approx(0)
    assert gradient_alignment(zeros,zeros,ones,zeros)[0] is None
    assert gradient_alignment(ones,zeros,zeros,zeros)[0] is None
    assert gradient_alignment(ones,zeros,ones,zeros,np.zeros((4,4),bool))[0] is None

def test_resolution_adequacy():
    assert resolution_adequacy(10,10,CONFIG)[0]=='REFERENCE_TOO_COARSE'
    assert resolution_adequacy(20,10,CONFIG)[0]=='REFERENCE_UNCERTAIN'
    assert resolution_adequacy(40,10,CONFIG)[0]=='REFERENCE_RESOLUTION_ADEQUATE'

def test_known_affine_recovered_and_rmse():
    src=np.array([[0,0],[100,0],[0,80],[100,80]],float);m=np.array([[1.2,.1,8],[-.05,.9,12],[0,0,1]]);dst=transform_points(m,src)
    result=fit_affine(src,dst,(100,80),CONFIG)
    assert np.asarray(result.matrix)==pytest.approx(m,abs=1e-8)
    assert result.rmse_px==pytest.approx(0,abs=1e-8) and result.status=='REGISTRATION_SUCCESS'

def test_three_point_fit_is_capped_and_bad_points_rejected():
    src=[[0,0],[100,0],[0,100]];dst=[[10,10],[110,10],[10,110]];r=fit_affine(src,dst,(100,100),CONFIG)
    assert r.validation_basis=='MINIMAL_EXACT_FIT' and r.quality_score<=CONFIG['registration']['minimal_fit_quality_cap']
    with pytest.raises(ValueError,match='DEGENERATE'):fit_affine([[0,0],[1,1],[2,2]],dst,(100,100),CONFIG)

def test_physical_support_omits_unavailable_and_risk_is_deterministic():
    components={'dem_support':.8,'gradient_alignment':None,'hillshade_support':None,'local_relief_support':.4}
    score,available,coverage=weighted_physical_support(components,CONFIG['physical_support']['weights'])
    assert set(available)=={'dem_support','local_relief_support'} and score==pytest.approx(.6909,abs=1e-4) and coverage==.55
    assert unsupported_risk(.8,.25,.9,.8,.7)==pytest.approx(.3024)

def feature(**overrides):
    base={'feature_id':'F01','physical_support':.9,'unsupported_risk':.05,'registration_quality':.95,'reference_quality':.95,'status':'SUPPORTED'};base.update(overrides);return base

def test_policy_gates_and_coarse_reference_safeguard():
    safe=evaluate_policy('ROUTE_PLANNING','COMPARABLE',[feature()],CONFIG);assert safe.decision=='SAFE_TO_EXPORT'
    low=evaluate_policy('ROUTE_PLANNING','COMPARABLE',[feature(physical_support=.1,unsupported_risk=.8,status='CONTRADICTED')],CONFIG);assert low.decision=='NOT_SAFE'
    coarse=evaluate_policy('ROUTE_PLANNING','COMPARABLE',[feature(physical_support=.1,unsupported_risk=.1,reference_quality=.3,status='REFERENCE_INADEQUATE')],CONFIG);assert coarse.decision=='REVIEW_REQUIRED'
    science=evaluate_policy('SCIENTIFIC_VISUALIZATION','COMPARABLE',[feature(physical_support=.4,unsupported_risk=.3,reference_quality=.7,registration_quality=.7,status='PARTIALLY_SUPPORTED')],CONFIG);assert science.decision=='SAFE_TO_EXPORT'
    assert evaluate_policy('ROUTE_PLANNING','COMPARABLE',[],CONFIG,True).decision=='NO_SIGNIFICANT_CHANGE'
    assert evaluate_policy('ROUTE_PLANNING','INCOMPARABLE_IMAGES',[],CONFIG).decision=='REVIEW_REQUIRED'

def test_passport_integrity():
    analysis={'id':'a','inputs':{'original':{'sha256':'o'},'enhanced':{'sha256':'e'}}};dataset={'id':'d','product_id':'p','classification':'TEST_DATA','sha256':'h'}
    phase={'configuration':CONFIG,'mission_profile':'MAPPING','features':[],'policy':{'decision':'SAFE_TO_EXPORT'}}
    passport=build_passport(analysis,dataset,None,phase,{'x':'y'})
    assert len(passport['passport_sha256'])==64 and passport['dem_hash']=='h' and passport['dataset_classification']=='TEST_DATA'

def test_too_coarse_reference_never_becomes_contradicted(tmp_path):
    y,x=np.mgrid[:40,:40];dem=write_dem(tmp_path/'coarse.tif',x+y)
    reg=auto_dimension_registration((40,40),(40,40));image=np.uint8((x+y)%255)
    f={'id':'F01','bbox':(10,10,1,1),'visual_score':.9}
    evidence=verify_region(f,image/255,image/255,dem,reg,.95,CONFIG).to_dict()
    assert evidence['reference_resolution']['status']=='REFERENCE_TOO_COARSE'
    assert evidence['status']=='REFERENCE_INADEQUATE' and evidence['status']!='CONTRADICTED'

def test_low_nodata_coverage_is_reference_unavailable(tmp_path):
    z=np.full((40,40),-9999.,dtype=float);z[15:20,15:20]=10
    dem=write_dem(tmp_path/'sparse.tif',z,-9999);reg=auto_dimension_registration((40,40),(40,40));image=np.ones((40,40),float)
    f={'id':'F01','bbox':(0,0,40,40),'visual_score':.8}
    evidence=verify_region(f,image,image,dem,reg,.95,CONFIG).to_dict()
    assert evidence['coverage_status']=='REFERENCE_UNAVAILABLE' and evidence['physical_support'] is None

def test_invalid_phase2_configuration_rejected():
    bad=copy.deepcopy(CONFIG);bad['physical_support']['weights']['dem_support']=-.2
    with pytest.raises(ValueError,match='physical support weights'):validate_phase2_config(bad)
    bad=copy.deepcopy(CONFIG);bad['risk']['review_threshold']=.9
    with pytest.raises(ValueError,match='Risk thresholds'):validate_phase2_config(bad)
