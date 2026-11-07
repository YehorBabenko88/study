"""Opt-in ComfyUI local text-to-image adapter, no arbitrary workflow execution."""
import json
import os
import re
import urllib.request
import urllib.parse
from uuid import uuid4

BASE="http://127.0.0.1:8188"
def _request(path,payload=None):
    url=BASE+path
    data=json.dumps(payload).encode("utf-8") if payload is not None else None
    req=urllib.request.Request(url,data=data,headers={"Content-Type":"application/json"} if data else {},method="POST" if data else "GET")
    with urllib.request.urlopen(req,timeout=15) as response:
        raw=response.read(4_000_000)
    return json.loads(raw)
def configured():
    return os.getenv("STUDY_COMFYUI_ENABLED","0")=="1"
def _checkpoint():
    name=os.getenv("STUDY_COMFYUI_CHECKPOINT","")
    if not name or len(name)>180 or not re.fullmatch(r"[a-zA-Z0-9_./\\ ()-]+\.(?:safetensors|ckpt)",name):
        raise ValueError("Set reviewed STUDY_COMFYUI_CHECKPOINT")
    return name
def workflow(prompt,seed=0,width=512,height=512,steps=20):
    if not isinstance(prompt,str) or not 1<=len(prompt)<=1200:raise ValueError("Invalid prompt")
    if not isinstance(seed,int) or not 0<=seed<2**53:raise ValueError("Invalid seed")
    if width not in (512,768) or height not in (512,768) or not 5<=steps<=35:raise ValueError("Unsupported generation size/steps")
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
def submit(prompt,seed=0):
    if not configured():return {"status":"unavailable","reason":"comfyui_not_enabled"}
    result=_request("/prompt",{"prompt":workflow(prompt,seed=seed),"client_id":str(uuid4())})
    if not isinstance(result.get("prompt_id"),str):raise RuntimeError("ComfyUI did not return prompt ID")
    return {"status":"queued","prompt_id":result["prompt_id"]}
def result(prompt_id):
    if not configured():return {"status":"unavailable","reason":"comfyui_not_enabled"}
    if not re.fullmatch(r"[0-9a-fA-F-]{36}",prompt_id):raise ValueError("Invalid prompt ID")
    history=_request("/history/"+prompt_id)
    job=history.get(prompt_id)
    if not job:return {"status":"pending"}
    outputs=job.get("outputs",{})
    images=[{"filename":x.get("filename"),"subfolder":x.get("subfolder",""),"type":x.get("type","output")}
            for value in outputs.values() for x in value.get("images",[])
            if x.get("type","output")=="output"]
    return {"status":"complete" if images else "no_image","images":images[:4]}
def image_bytes(prompt_id,filename,subfolder=""):
    info=result(prompt_id)
    if info.get("status")!="complete":raise ValueError("Job not ready")
    if not any(i["filename"]==filename and i["subfolder"]==subfolder for i in info["images"]):
        raise ValueError("Image not produced by this job")
    qs=urllib.parse.urlencode({"filename":filename,"subfolder":subfolder,"type":"output"})
    with urllib.request.urlopen(BASE+"/view?"+qs,timeout=15) as response:
        data=response.read(8_000_001)
    if len(data)>8_000_000:raise ValueError("Image too large")
    return data
