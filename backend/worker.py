import json, time, subprocess, shutil, threading
from pathlib import Path
import cv2
from .core import DATA,infer,decode,encode,export_csv,geojson,model_for,device,severity_note,add_visual_severity
from . import db

def analyze(jobid,kind,name,model,params,lat=None,lon=None,gps=None,severity_low=.005,severity_high=.025):
    folder=DATA/jobid; original=next(folder.glob('input.*')); started=time.perf_counter()
    try:
        db.update(jobid,state='running',progress=.01)
        if kind=='image':
            img=decode(original.read_bytes());out,det,mask,_=infer(img,model,**params)
            add_visual_severity(det,img.shape[1],img.shape[0],severity_low,severity_high)
            (folder/'result.png').write_bytes(encode(out));(folder/'mask.png').write_bytes(encode(mask))
            result={'detections':det,'total_observations':len(det),'unique_tracks':None,'width':img.shape[1],'height':img.shape[0],'geojson':geojson(det,lat,lon),'severity_notice':severity_note()}
        else:
            cap=cv2.VideoCapture(str(original));fps=cap.get(cv2.CAP_PROP_FPS) or 25.; count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));w=int(cap.get(3));h=int(cap.get(4))
            if not cap.isOpened() or w<1 or h<1 or w*h>40_000_000:raise ValueError('Video inválido o demasiado grande')
            raw=folder/'raw.mp4'; writer=cv2.VideoWriter(str(raw),cv2.VideoWriter_fourcc(*'mp4v'),fps,(w,h))
            if not writer.isOpened():raise RuntimeError('No pudo inicializarse el codificador MP4')
            det=[]; tracks=set();n=0;step=int(params.pop('frame_step',1)); maxframes=int(params.pop('max_frames',18000))
            try:
                while n<maxframes:
                    ok,frame=cap.read()
                    if not ok:break
                    if n%step==0:
                        overlay,rows,_,_=infer(frame,model,tracking=True,**params)
                        add_visual_severity(rows,w,h,severity_low,severity_high)
                        for r in rows:
                            if r['track_id'] is not None:tracks.add(r['track_id'])
                            det.append({'frame':n,'second':round(n/fps,3),**r})
                        writer.write(overlay)
                    else:writer.write(frame)
                    n+=1
                    if n%12==0:db.update(jobid,progress=min(.95,n/max(count,1)))
            finally:cap.release();writer.release()
            if n==0:raise ValueError('Video vacío')
            dst=folder/'result.mp4';ffmpeg=shutil.which('ffmpeg')
            if ffmpeg:
                proc=subprocess.run([ffmpeg,'-y','-loglevel','error','-i',str(raw),'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(dst)],capture_output=True,timeout=600)
                if proc.returncode:shutil.copy2(raw,dst)
            else:shutil.copy2(raw,dst)
            raw.unlink(missing_ok=True)
            result={'detections':det,'total_observations':len(det),'unique_tracks':len(tracks) if tracks else None,'frames':n,'seconds':round(n/fps,2),'fps':fps,'truncated':n>=maxframes,'geojson':geojson(det,lat,lon),'severity_notice':severity_note(),'tracking_notice':'IDs temporales dentro del video; no garantizan el conteo de baches físicos únicos entre reapariciones.'}
        result['severity_summary']={level:sum(x['severidad_visual']==level for x in result['detections']) for level in ('baja','media','alta','sin_mascara')}
        result['severity_thresholds']={'low':severity_low,'high':severity_high,'unit':'fraccion_del_area_de_imagen'}
        result['model']=model;result['device']=device();result['elapsed_seconds']=round(time.perf_counter()-started,3)
        (folder/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'results.geojson').write_text(json.dumps(result['geojson'],ensure_ascii=False,indent=2),encoding='utf-8')
        export_csv(result['detections'],folder/'results.csv')
        db.update(jobid,state='done',progress=1,result_json=json.dumps({k:v for k,v in result.items() if k not in ('detections','geojson')},ensure_ascii=False))
    except Exception as exc:db.update(jobid,state='failed',error=str(exc)[:500])
