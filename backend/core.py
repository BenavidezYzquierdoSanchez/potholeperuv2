from __future__ import annotations
import os, csv, json, time, uuid, shutil, subprocess, threading
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.environ.get('BACHES_DATA',str(ROOT/'data'))); DATA.mkdir(parents=True,exist_ok=True)
MODELS={'S43':'exp-s43.pt','S44':'exp-s44.pt','V1':'exp-v1.pt','SM45':'expsm45.pt'}
_lock=threading.RLock(); _loaded={}
def model_for(name):
    if name not in MODELS: raise ValueError('Modelo no permitido')
    with _lock:
        if name not in _loaded:
            from ultralytics import YOLO
            path=ROOT/'models'/MODELS[name]
            if not path.is_file(): raise FileNotFoundError(path)
            _loaded[name]=YOLO(str(path)) # checkpoints locales confiables; nunca cargar un .pt del usuario
        return _loaded[name]
def device():
    import torch
    return '0' if torch.cuda.is_available() else 'cpu'
def infer(frame, name, conf=.25, iou=.5, imgsz=640, alpha=.4, draw_boxes=True, draw_masks=True, tracking=False, tracker='bytetrack.yaml'):
    model=model_for(name)
    params=dict(source=frame,conf=conf,iou=iou,imgsz=imgsz,device=device(),verbose=False)
    with _lock: # compartición segura de instancia/caché YOLO
        r=(model.track(**params,persist=True,tracker=tracker) if tracking else model.predict(**params))[0]
    img=frame.copy(); det=[]; polys=[]; fullmask=np.zeros(frame.shape[:2],np.uint8)
    if r.boxes is None: return img,det,fullmask,polys
    b=r.boxes; ids=b.id.int().cpu().tolist() if b.id is not None else [None]*len(b)
    for n,(rect,prob,cl,trackid) in enumerate(zip(b.xyxy.cpu().numpy(),b.conf.cpu().numpy(),b.cls.int().cpu().numpy(),ids)):
        xy=[int(v) for v in rect]; poly=[]; mask=np.zeros(frame.shape[:2],np.uint8)
        if r.masks is not None and n<len(r.masks.xy):
            poly=np.asarray(r.masks.xy[n],dtype=np.int32).reshape(-1,2).tolist()
            if len(poly)>=3:cv2.fillPoly(mask,[np.asarray(poly,dtype=np.int32)],255)
        fullmask=cv2.bitwise_or(fullmask,mask)
        if draw_masks and mask.any():
            tint=np.zeros_like(img); tint[:]=(45,186,37)
            merged=cv2.addWeighted(img,1-alpha,tint,alpha,0)
            img[mask>0]=merged[mask>0]; cv2.polylines(img,[np.asarray(poly,dtype=np.int32)],True,(70,255,135),2)
        if draw_boxes:
            x1,y1,x2,y2=xy; cv2.rectangle(img,(x1,y1),(x2,y2),(36,224,112),2)
            label=f'{r.names.get(int(cl),str(cl))} {prob:.0%}'+(f' #{trackid}' if trackid is not None else '')
            cv2.putText(img,label,(x1,max(18,y1-6)),cv2.FONT_HERSHEY_SIMPLEX,.55,(36,224,112),2)
        area=int(np.count_nonzero(mask)); boxarea=max(0,xy[2]-xy[0])*max(0,xy[3]-xy[1])
        det.append({'id':n+1,'track_id':trackid,'clase':str(r.names.get(int(cl),str(cl))),'confianza':round(float(prob),5),'bbox':xy,'area_mascara_px':area,'area_caja_px':boxarea,'area_relativa':round(area/max(1,frame.shape[0]*frame.shape[1]),6),'polygon':poly})
        polys.append(poly)
    return img,det,fullmask,polys
def add_visual_severity(detections, width, height, low=0.005, high=0.025):
    """Screening by segmented image coverage only; NOT actual depth or engineering severity."""
    if not (0 < low < high <= 1): raise ValueError('Umbrales de cobertura inválidos')
    for d in detections:
        coverage = d.get('area_mascara_px', 0) / max(1, width*height)
        d['cobertura_imagen_pct'] = round(100*coverage, 3)
        d['severidad_visual'] = ('sin_mascara' if d.get('area_mascara_px', 0) <= 0 else
                                 'baja' if coverage < low else 'media' if coverage < high else 'alta')
        d['severidad_metodo'] = 'heuristica_cobertura_2d_no_validada'
    return detections

def encode(img,ext='.png'):
    ok,b=cv2.imencode(ext,img)
    if not ok:raise ValueError('No se pudo codificar la imagen')
    return b.tobytes()
def decode(data):
    image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    if image is None:raise ValueError('Imagen inválida')
    h,w=image.shape[:2]
    if w*h>40_000_000:raise ValueError('Imagen excede 40 megapíxeles')
    return image
def geojson(dets,lat=None,lon=None):
    # Las coordenadas de píxel NO son coordenadas geográficas; GPS de imagen se representa como punto.
    features=[]
    for d in dets:
        geom={'type':'Point','coordinates':[lon,lat]} if lat is not None and lon is not None else None
        features.append({'type':'Feature','geometry':geom,'properties':{k:v for k,v in d.items() if k!='polygon'}|{'pixel_polygon':d['polygon']}})
    return {'type':'FeatureCollection','features':features}
def export_csv(dets,path):
    import io
    rows=[{k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v) for k,v in d.items()} for d in dets]
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['id','track_id','clase','confianza','bbox','area_mascara_px','area_caja_px','area_relativa','polygon']);writer.writeheader();writer.writerows(rows)
def severity_note():
    return 'El área visible en píxeles NO determina profundidad ni gravedad estructural. Se requiere inspección/calibración.'
