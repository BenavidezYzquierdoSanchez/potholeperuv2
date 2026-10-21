from __future__ import annotations
import os, uuid, json, shutil, threading, io, zipfile, csv, time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional
from backend.core import ROOT,DATA,MODELS,model_for,infer,decode,device
from backend import db
from backend.worker import analyze

MAX_UPLOAD_MB=int(os.getenv('MAX_UPLOAD_MB','400'))
API_KEY=os.getenv('BACHES_API_KEY','')
def authorized(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key!=API_KEY:raise HTTPException(401,'Clave API incorrecta')
@asynccontextmanager
async def lifespan(app):
    db.init();yield
app=FastAPI(title='Baches Perú API',version='2.0.0',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=ROOT/'frontend'),name='static')
@app.get('/')
def home():return FileResponse(ROOT/'frontend'/'index.html')
@app.get('/api/health')
def health():return {'status':'ok','models':list(MODELS),'device':device()}
@app.get('/api/models',dependencies=[Depends(authorized)])
def models():return [{'id':k,'file':v,'available':(ROOT/'models'/v).exists()} for k,v in MODELS.items()]
@app.get('/api/jobs',dependencies=[Depends(authorized)])
def jobs():return db.all()
@app.get('/api/jobs/{id}',dependencies=[Depends(authorized)])
def job(id:str):
    r=db.get(id)
    if not r:raise HTTPException(404,'No existe')
    return r
@app.post('/api/analyze',dependencies=[Depends(authorized)])
async def upload(file:UploadFile=File(...),model:str=Form('SM45'),conf:float=Form(.25),iou:float=Form(.5),imgsz:int=Form(640),alpha:float=Form(.4),boxes:bool=Form(True),masks:bool=Form(True),frame_step:int=Form(1),max_frames:int=Form(18000),lat:Optional[float]=Form(None),lon:Optional[float]=Form(None),severity_low:float=Form(.005),severity_high:float=Form(.025)):
    if model not in MODELS:raise HTTPException(422,'Modelo inválido')
    if not 0<severity_low<severity_high<=1:raise HTTPException(422,'Umbrales de severidad visual inválidos')
    if not 0.01<=conf<=1 or not 0.01<=iou<=1 or imgsz not in (320,480,640,800,960,1280) or not 0<=alpha<=1 or not 1<=frame_step<=30 or not 1<=max_frames<=18000:raise HTTPException(422,'Parámetros fuera de rango')
    if (lat is None)!=(lon is None) or (lat is not None and not -90<=lat<=90) or (lon is not None and not -180<=lon<=180):raise HTTPException(422,'Coordenadas inválidas')
    suffix=Path(file.filename or '').suffix.lower()
    kind='image' if suffix in ('.jpg','.jpeg','.png','.webp','.bmp') else 'video' if suffix in ('.mp4','.mov','.avi','.mkv','.webm') else None
    if kind is None:raise HTTPException(415,'Formato no admitido')
    jid=uuid.uuid4().hex;folder=DATA/jid;folder.mkdir()
    total=0
    try:
        with (folder/('input'+suffix)).open('wb') as f:
            while part:=await file.read(1024*1024):
                total+=len(part)
                if total>MAX_UPLOAD_MB*1024*1024:raise HTTPException(413,'Archivo excede límite')
                f.write(part)
        if not total:raise HTTPException(422,'Archivo vacío')
        if kind=='image':decode((folder/('input'+suffix)).read_bytes())
        else:
            import cv2
            cap=cv2.VideoCapture(str(folder/('input'+suffix)));ok=cap.isOpened();cap.release()
            if not ok:raise HTTPException(422,'Video ilegible')
        db.insert(jid,kind,Path(file.filename or 'archivo').name[:200],model,lat,lon)
        params=dict(conf=conf,iou=iou,imgsz=imgsz,alpha=alpha,draw_boxes=boxes,draw_masks=masks)
        if kind=='video':params.update(frame_step=frame_step,max_frames=max_frames)
        threading.Thread(target=analyze,args=(jid,kind,file.filename,model,params,lat,lon,None,severity_low,severity_high),daemon=True).start()
        return {'id':jid,'state':'queued'}
    except Exception:
        if not db.get(jid):shutil.rmtree(folder,ignore_errors=True)
        raise
@app.get('/api/jobs/{id}/result',dependencies=[Depends(authorized)])
def result(id:str):
    r=db.get(id)
    if not r:raise HTTPException(404,'No existe')
    if r['state']!='done':raise HTTPException(409,'Trabajo incompleto')
    return json.loads((DATA/id/'results.json').read_text(encoding='utf-8'))
@app.get('/api/jobs/{id}/file/{filename}',dependencies=[Depends(authorized)])
def get_file(id:str,filename:str):
    r=db.get(id)
    if not r:raise HTTPException(404,'No existe')
    allowed={'result.png','mask.png','result.mp4','results.csv','results.json','results.geojson'}
    if filename not in allowed:raise HTTPException(404,'Archivo no permitido')
    path=DATA/id/filename
    if not path.is_file():raise HTTPException(404,'Archivo no disponible')
    return FileResponse(path,filename=f'{id[:8]}_{filename}')
@app.get('/api/jobs/{id}/export.zip',dependencies=[Depends(authorized)])
def export(id:str):
    r=db.get(id)
    if not r:raise HTTPException(404,'No existe')
    if r['state']!='done':raise HTTPException(409,'Trabajo incompleto')
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in (DATA/id).glob('*'):
            if not p.name.startswith('input.') and p.is_file():z.write(p,p.name)
    mem.seek(0)
    return StreamingResponse(mem,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="baches_{id[:8]}.zip"'})
@app.post('/api/compare',dependencies=[Depends(authorized)])
async def compare(file:UploadFile=File(...),conf:float=Form(.25),iou:float=Form(.5),imgsz:int=Form(640)):
    if not 0.01<=conf<=1 or not 0.01<=iou<=1 or imgsz not in (320,480,640,800,960,1280):raise HTTPException(422,'Parámetros inválidos')
    b=await file.read(25*1024*1024+1)
    if len(b)>25*1024*1024:raise HTTPException(413,'Imagen demasiado grande')
    try:frame=decode(b)
    except Exception as e:raise HTTPException(422,str(e))
    import cv2
    rows=[]
    for name in MODELS:
        try:
            start=time.perf_counter();out,ds,mask,_=infer(frame,name,conf=conf,iou=iou,imgsz=imgsz)
            jid=uuid.uuid4().hex;folder=DATA/jid;folder.mkdir()
            from .core import encode
            (folder/'result.png').write_bytes(encode(out))
            rows.append({'model':name,'detections':len(ds),'mean_confidence':round(sum(x['confianza'] for x in ds)/len(ds),4) if ds else None,'seconds':round(time.perf_counter()-start,3),'preview_id':jid,'error':None})
        except Exception as e:rows.append({'model':name,'error':str(e)[:180]})
    return {'comparison':rows,'notice':'Sin etiquetas de verdad terreno: el conteo, confianza y latencia NO permiten inferir cuál modelo es más preciso.'}
@app.post('/api/benchmark',dependencies=[Depends(authorized)])
def benchmark(dataset_yaml:str=Form(...),split:str=Form('val'),imgsz:int=Form(640)):
    # Solo rutas ubicadas debajo de datasets/ administradas por el operador
    base=(ROOT/'datasets').resolve();base.mkdir(exist_ok=True)
    target=(base/dataset_yaml).resolve()
    if not target.is_relative_to(base) or target.suffix not in ('.yaml','.yml') or not target.is_file():raise HTTPException(422,'Dataset YAML debe existir dentro de datasets/')
    if split not in ('val','test') or imgsz not in (320,480,640,800,960,1280):raise HTTPException(422,'Configuración inválida')
    output=[]
    for name in MODELS:
        try:
            m=model_for(name)
            result=m.val(data=str(target),split=split,imgsz=imgsz,device=device(),plots=False,verbose=False)
            output.append({'model':name,'box_map50':float(result.box.map50),'box_map50_95':float(result.box.map),'mask_map50':float(result.seg.map50) if hasattr(result,'seg') else None,'mask_map50_95':float(result.seg.map) if hasattr(result,'seg') else None})
        except Exception as e:output.append({'model':name,'error':str(e)[:250]})
    return {'benchmark':output,'split':split,'dataset':dataset_yaml}
@app.get('/api/compare-preview/{id}',dependencies=[Depends(authorized)])
def comparison_preview(id:str):
    try:uuid.UUID(hex=id)
    except ValueError:raise HTTPException(404,'Vista no encontrada')
    path=DATA/id/'result.png'
    if not path.is_file():raise HTTPException(404,'Vista no encontrada')
    return FileResponse(path,media_type='image/png')
