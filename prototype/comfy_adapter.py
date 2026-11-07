"""Opt-in ComfyUI local text-to-image adapter, no arbitrary workflow execution."""
import json
import os
import re
import urllib.request
import urllib.parse
from uuid import uuid4

BASE="http://127.0.0.1:8188"
def _request(path,payload=None,timeout=15):
    url=BASE+path
    data=json.dumps(payload).encode("utf-8") if payload is not None else None
    req=urllib.request.Request(url,data=data,headers={"Content-Type":"application/json"} if data else {},method="POST" if data else "GET")
    with urllib.request.urlopen(req,timeout=timeout) as response:
        raw=response.read(4_000_001)
    if len(raw)>4_000_000:raise ValueError("Comfy response too large")
    return json.loads(raw)
def configured():
    return os.getenv("STUDY_COMFYUI_ENABLED","0")=="1"
def _checkpoint():
    name=os.getenv("STUDY_COMFYUI_CHECKPOINT","")
    if not name or ".." in name or name.startswith(("/", "\\")) or len(name)>180 or not re.fullmatch(r"[a-zA-Z0-9_./\\ ()-]+\.(?:safetensors|ckpt)",name):
        raise ValueError("Set reviewed STUDY_COMFYUI_CHECKPOINT")
    return name
def workflow(prompt,seed=0,width=512,height=512,steps=20):
    if not isinstance(prompt,str) or not 1<=len(prompt)<=1200:raise ValueError("Invalid prompt")
    if type(seed) is not int or not 0<=seed<2**53:raise ValueError("Invalid seed")
    if type(steps) is not int or type(width) is not int or type(height) is not int or width not in (512,768) or height not in (512,768) or not 5<=steps<=35:raise ValueError("Unsupported generation size/steps")
    ckpt=_checkpoint()
    return {
      "1":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":ckpt}},
      "2":{"class_type":"CLIPTextEncode","inputs":{"text":prompt,"clip":["1",1]}},
      "3":{"class_type":"CLIPTextEncode","inputs":{"text":"blurry, low quality, text, watermark","clip":["1",1]}},
      "4":{"class_type":"EmptyLatentImage","inputs":{"width":width,"height":height,"batch_size":1}},
      "5":{"class_type":"KSampler","inputs":{"seed":seed,"steps":steps,"cfg":7,"sampler_name":"euler","scheduler":"normal","denoise":1,"model":["1",0],"positive":["2",0],"negative":["3",0],"latent_image":["4",0]}},
      "6":{"class_type":"VAEDecode","inputs":{"samples":["5",0],"vae":["1",2]}},
      "7":{"class_type":"SaveImage","inputs":{"filename_prefix":"Study","images":["6",0]}}
    }

# The registry owns all job IDs. A Comfy history ID alone never grants access.
import sqlite3
import threading
import time
from pathlib import Path
from io import BytesIO

TERMINAL = {'complete', 'failed', 'cancelled', 'timed_out', 'interrupted'}

class QueueFull(RuntimeError):
    pass

class JobRegistry:
    def __init__(self, path, *, workers=1, capacity=8, timeout=120, poll=.25, start_workers=True):
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.timeout, self.poll, self.capacity = timeout, poll, capacity
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, request_id TEXT UNIQUE, payload TEXT, state TEXT, remote TEXT, created REAL, updated REAL, images TEXT, error TEXT)')
        self.db.execute("UPDATE jobs SET state='interrupted', error=?, updated=? WHERE state='running'", (json.dumps({'code':'restart_interrupted','message':'Server restarted; submit a new request to retry.'}), time.time()))
        self.db.commit()
        self.threads = []
        if start_workers:
            for _ in range(max(1, min(workers, 4))):
                t=threading.Thread(target=self._worker, daemon=True)
                t.start(); self.threads.append(t)

    def _row(self, job_id):
        if not isinstance(job_id,str) or not re.fullmatch(r'[0-9a-f-]{36}',job_id):
            raise ValueError('Invalid job ID')
        row=self.db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if row is None: raise KeyError('Unknown local job')
        return row

    def _public(self,row):
        return {'prompt_id':row[0], 'job_id':row[0], 'request_id':row[1], 'status':row[3],
                'created_at':row[5], 'updated_at':row[6], 'images':json.loads(row[7] or '[]'),
                'error':json.loads(row[8]) if row[8] else None}

    def submit(self,prompt,seed=0,request_id=None):
        payload=json.dumps({'prompt':workflow(prompt,seed=seed)},sort_keys=True)
        request_id=request_id or str(uuid4())
        if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',request_id):
            raise ValueError('Invalid request_id')
        with self.lock:
            row=self.db.execute('SELECT * FROM jobs WHERE request_id=?',(request_id,)).fetchone()
            if row:
                if row[2]!=payload:raise ValueError('request_id already used for different input')
                return self._public(row)
            count=self.db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
            if count>=self.capacity:raise QueueFull('Local generation queue is full')
            job_id=str(uuid4()); now=time.time()
            self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)',(job_id,request_id,payload,'queued',None,now,now,None,None)); self.db.commit()
            return self._public(self._row(job_id))

    def result(self,job_id):
        with self.lock:return self._public(self._row(job_id))

    def list(self):
        with self.lock:return [self._public(r) for r in self.db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 100')]

    def _finish(self,job_id,state,images=None,error=None):
        with self.lock:
            self.db.execute("UPDATE jobs SET state=?,updated=?,images=?,error=? WHERE id=? AND state='running'",(state,time.time(),json.dumps(images or []),json.dumps(error) if error else None,job_id)); self.db.commit()

    def cancel(self,job_id):
        with self.lock:
            row=self._row(job_id)
            if row[3] not in TERMINAL:
                self.db.execute("UPDATE jobs SET state='cancelled',updated=?,error=? WHERE id=?",(time.time(),json.dumps({'code':'cancelled','message':'Cancelled locally; upstream computation may finish.'}),job_id)); self.db.commit()
            return self._public(self._row(job_id))

    def _worker(self):
        while not self.stop.is_set():
            with self.lock:
                row=self.db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
                if row:
                    self.db.execute("UPDATE jobs SET state='running',updated=? WHERE id=?",(time.time(),row[0])); self.db.commit()
            if not row:
                self.stop.wait(self.poll); continue
            job_id=row[0]; deadline=time.monotonic()+self.timeout
            try:
                response=_request('/prompt',dict(json.loads(row[2]),client_id=job_id),timeout=min(15,self.timeout))
                remote=response.get('prompt_id')
                if not isinstance(remote,str) or not re.fullmatch(r'[0-9a-fA-F-]{36}',remote):raise RuntimeError('Invalid upstream prompt response')
                with self.lock:
                    self.db.execute('UPDATE jobs SET remote=? WHERE id=?',(remote,job_id)); self.db.commit()
                while not self.stop.is_set() and self.result(job_id)['status']=='running':
                    if time.monotonic()>=deadline:
                        self._finish(job_id,'timed_out',error={'code':'generation_timeout','message':'Generation deadline exceeded.'}); break
                    history=_request('/history/'+remote,timeout=max(.01,min(15,deadline-time.monotonic())))
                    job=history.get(remote)
                    if job:
                        if job.get('status',{}).get('status_str')=='error':raise RuntimeError('ComfyUI execution failed')
                        images=[]
                        for value in job.get('outputs',{}).values():
                            for entry in value.get('images',[]):
                                if entry.get('type','output')=='output':
                                    _image_name(entry.get('filename'),entry.get('subfolder',''))
                                    images.append({'filename':entry['filename'],'subfolder':entry.get('subfolder',''),'type':'output'})
                        if images:self._finish(job_id,'complete',images[:4]); break
                        if job.get('status',{}).get('completed'):raise RuntimeError('Completed without image')
                    self.stop.wait(self.poll)
            except Exception as exc:
                expired=time.monotonic()>=deadline
                code='generation_timeout' if expired else 'upstream_failed'
                self._finish(job_id,'timed_out' if expired else 'failed',error={'code':code,'message':'Local ComfyUI request failed. Check service and checkpoint configuration.'})

    def close(self):
        self.stop.set()
        for t in self.threads:t.join(16)
        with self.lock:self.db.close()


def _image_name(filename,subfolder):
    if not isinstance(filename,str) or not re.fullmatch(r'[A-Za-z0-9_ .()-]{1,200}\.png',filename) or '..' in filename:
        raise ValueError('Invalid output filename')
    if not isinstance(subfolder,str) or len(subfolder)>200 or '\\' in subfolder or subfolder.startswith('/') or any(p in ('.','..') for p in subfolder.split('/')):
        raise ValueError('Invalid output subfolder')

_registry=None
_registry_lock=threading.Lock()
def registry():
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry=JobRegistry(os.getenv('STUDY_COMFYUI_DB',str(Path(__file__).with_name('comfy_jobs.sqlite'))),
                workers=int(os.getenv('STUDY_COMFYUI_WORKERS','1')), capacity=int(os.getenv('STUDY_COMFYUI_CAPACITY','8')),
                timeout=float(os.getenv('STUDY_COMFYUI_TIMEOUT','120')))
        return _registry

def submit(prompt,seed=0,request_id=None):
    if not configured():return {'status':'unavailable','reason':'comfyui_not_enabled'}
    return registry().submit(prompt,seed,request_id)

def result(prompt_id):return registry().result(prompt_id)
def cancel(prompt_id):return registry().cancel(prompt_id)
def list_jobs():return registry().list()

def image_bytes(prompt_id,filename,subfolder=''):
    _image_name(filename,subfolder)
    info=result(prompt_id)
    if info['status']!='complete' or not any(i['filename']==filename and i['subfolder']==subfolder for i in info['images']):raise ValueError('Image not produced by this local job')
    qs=urllib.parse.urlencode({'filename':filename,'subfolder':subfolder,'type':'output'})
    with urllib.request.urlopen(BASE+'/view?'+qs,timeout=15) as response:data=response.read(8_000_001)
    if len(data)>8_000_000:raise ValueError('Image too large')
    from PIL import Image
    try:
        with Image.open(BytesIO(data)) as im:
            if im.format!='PNG' or im.width*im.height>16_000_000:raise ValueError('Invalid output image')
            im.verify()
    except (OSError,Image.DecompressionBombError) as exc:raise ValueError('Invalid PNG') from exc
    return data
