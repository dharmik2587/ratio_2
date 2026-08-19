"""Reproducible Stage-1 QA measurement harness; writes docs/stage1_audit_results.json."""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).parents[1]
import sys
sys.path.insert(0,str(ROOT))
from ratio_core.evidence import analyze_image_pair
from backend.app.services.store import save_upload
from backend.app.services.analysis import run_analysis

CONFIG=json.loads((ROOT/'configs/stage1.json').read_text())


def scene(size=(512,512),seed=4):
    h,w=size; rng=np.random.default_rng(seed); y,x=np.mgrid[:h,:w]
    z=45+18*np.sin(x/(w/8.2))+13*np.cos(y/(h/6.1))
    craters=[(.28,.31,.12,25),(.70,.65,.16,30),(.73,.20,.07,18),(.18,.76,.08,14)]
    for fx,fy,fr,depth in craters:
        d=np.hypot(x-w*fx,y-h*fy); radius=w*fr
        z+=depth*np.exp(-((d-radius)/max(2,w*.015))**2)-depth*.55*np.exp(-(d/(radius*.7))**4)
    z+=rng.normal(0,1.5,z.shape)
    return np.uint8(np.clip(z,0,255))


def summary(result):
    return {"status":result.comparison.comparison_status,"compatibility_score":result.comparison.compatibility_score,
            "analysis_dimensions":result.comparison.analysis_dimensions,"resize_applied":result.comparison.resize_applied,
            "suspicious_area_pct":None if result.global_metrics is None else result.global_metrics['suspicious_area_pct'],
            "regions":len(result.regions)}


def overlap(mask,truth):
    d,t=mask>0,truth>0; inter=np.logical_and(d,t).sum(); union=np.logical_or(d,t).sum()
    return round(float(inter/union),4),round(float(2*inter/(d.sum()+t.sum())),4)


def encode(image):
    ok,data=cv2.imencode('.png',image); assert ok; return data.tobytes()


def benchmark_pair(a,b,label):
    start=time.perf_counter(); ua=save_upload(encode(a),f'{label}-a.png','image/png'); ub=save_upload(encode(b),f'{label}-b.png','image/png')
    upload_ms=round((time.perf_counter()-start)*1000,3)
    record=run_analysis(ua['id'],ub['id'],f'QA benchmark {label}')
    return {"upload_pair_ms":upload_ms,**record['processing_times_ms'],"status":record['status'],
            "compatibility_score":record['compatibility']['score'],
            "suspicious_area_pct":None if record['metrics'] is None else record['metrics']['suspicious_area_pct'],
            "regions":len(record['features'])}


def benchmark(size):
    a=scene((size,size)); b=a.copy(); cv2.circle(b,(int(size*.76),int(size*.27)),max(8,size//55),185,-1)
    return benchmark_pair(a,b,str(size))


def main():
    base=scene(); identical=analyze_image_pair(base,base.copy(),CONFIG)
    original=cv2.resize(base,(1043,1200),interpolation=cv2.INTER_CUBIC)
    resized=cv2.resize(original,(1170,1345),interpolation=cv2.INTER_CUBIC)
    size_case=analyze_image_pair(original,resized,CONFIG)
    altered=original.copy(); truth=np.zeros_like(original); cv2.circle(altered,(780,330),55,190,-1);cv2.circle(truth,(780,330),55,255,-1)
    altered_large=cv2.resize(altered,(1170,1345),interpolation=cv2.INTER_CUBIC)
    altered_result=analyze_image_pair(original,altered_large,CONFIG); iou,dice=overlap(altered_result.suspicious_mask,truth)
    crop=analyze_image_pair(base,base[55:-55,45:-45],CONFIG)
    unrelated_noise=analyze_image_pair(base,np.random.default_rng(99).integers(0,256,base.shape,dtype=np.uint8),CONFIG)
    lunar_b=np.rot90(scene(seed=81),2).copy(); unrelated_lunar=analyze_image_pair(base,lunar_b,CONFIG)

    movement={}
    for name,center in {'top_left':(60,60),'top_right':(452,60),'bottom_left':(60,452),'bottom_right':(452,452),'center':(256,256)}.items():
        b=base.copy(); t=np.zeros_like(base);cv2.circle(b,center,20,210,-1);cv2.circle(t,center,20,255,-1)
        r=analyze_image_pair(base,b,CONFIG); miou,mdice=overlap(r.suspicious_mask,t)
        movement[name]={**summary(r),'iou':miou,'dice':mdice}
    strength={}
    yy,xx=np.ogrid[:512,:512]; roi=(xx-256)**2+(yy-256)**2<=20**2
    for name,value in [('weak',85),('medium',145),('strong',220)]:
        b=base.copy();cv2.circle(b,(256,256),20,value,-1);r=analyze_image_pair(base,b,CONFIG)
        strength[name]={**summary(r),'mean_score_in_ground_truth':round(float(r.visual_score_map[roi].mean()),4)}
    transforms={
      'mild_sharpening':cv2.addWeighted(base,1.2,cv2.GaussianBlur(base,(0,0),1),-.2,0),
      'mild_denoising':cv2.GaussianBlur(base,(3,3),.5),
      'moderate_contrast':cv2.convertScaleAbs(base,alpha=1.12,beta=-4),
      'brightness':cv2.convertScaleAbs(base,alpha=1,beta=8),
      'mild_compression':cv2.imdecode(cv2.imencode('.jpg',base,[cv2.IMWRITE_JPEG_QUALITY,90])[1],cv2.IMREAD_GRAYSCALE),
    }
    legitimate={name:summary(analyze_image_pair(base,img,CONFIG)) for name,img in transforms.items()}
    noise={}
    rng=np.random.default_rng(2026)
    for sigma in (.5,1,2,4,8):
        noisy=np.uint8(np.clip(base.astype(float)+rng.normal(0,sigma,base.shape),0,255))
        noise[str(sigma)]=summary(analyze_image_pair(base,noisy,CONFIG))
    dbase=base.copy();cv2.rectangle(dbase,(380,80),(430,130),200,-1)
    one,two=analyze_image_pair(base,dbase,CONFIG),analyze_image_pair(base,dbase,CONFIG)
    deterministic={"scientific_json_equal":one.comparison==two.comparison and one.global_metrics==two.global_metrics and one.regions==two.regions,
      "visual_map_sha256_equal":hashlib.sha256(one.visual_score_map.tobytes()).hexdigest()==hashlib.sha256(two.visual_score_map.tobytes()).hexdigest(),
      "mask_sha256_equal":hashlib.sha256(one.suspicious_mask.tobytes()).hexdigest()==hashlib.sha256(two.suspicious_mask.tobytes()).hexdigest(),
      "intentional_differences":["analysis_id","created_at"]}
    output={"generated_at":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),"config_sha256":hashlib.sha256((ROOT/'configs/stage1.json').read_bytes()).hexdigest(),
      "image_compatibility":{"identical":summary(identical),"same_scene_different_resolution":summary(size_case),
      "same_scene_alteration_different_resolution":{**summary(altered_result),'iou':iou,'dice':dice},"same_scene_crop":summary(crop),
      "completely_unrelated":summary(unrelated_noise),"unrelated_lunar_looking":summary(unrelated_lunar)},
      "alteration_movement":movement,"alteration_strength":strength,"legitimate_enhancements":legitimate,"noise_robustness":noise,
      "determinism":deterministic,"performance":{**{str(size):benchmark(size) for size in (512,1024,2048)},
      "same_scene_different_dimensions":benchmark_pair(original,resized,"different-dimensions"),
      "incompatible_1024":benchmark_pair(scene((1024,1024)),np.random.default_rng(99).integers(0,256,(1024,1024),dtype=np.uint8),"incompatible")}}
    destination=ROOT/'docs/stage1_audit_results.json';destination.parent.mkdir(exist_ok=True);destination.write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2))

if __name__=='__main__':main()
