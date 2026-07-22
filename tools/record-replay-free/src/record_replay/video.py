from __future__ import annotations
import hashlib,json,shutil,subprocess,time
from pathlib import Path

def require(name:str)->str:
    value=shutil.which(name)
    if not value:raise RuntimeError(f"{name} is required and was not found on PATH")
    return value

def run_id(video:Path)->str:
    digest=hashlib.sha256(video.read_bytes()).hexdigest()[:10]
    return time.strftime('%Y%m%d-%H%M%S')+'-'+digest

def duration(video:Path)->float:
    r=subprocess.run([require('ffprobe'),'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(video)],capture_output=True,text=True,check=True)
    return float(r.stdout.strip())

def extract(video:Path,root:Path,interval:float=3.0)->dict:
    rid=run_id(video);out=root/rid
    if out.exists():raise FileExistsError(f"Immutable run already exists: {out}")
    frames=out/'frames';frames.mkdir(parents=True)
    copied=out/('source'+video.suffix.lower());shutil.copy2(video,copied)
    subprocess.run([require('ffmpeg'),'-hide_banner','-loglevel','error','-i',str(copied),'-vf',f"fps=1/{interval},scale=1280:-2",'-q:v','3',str(frames/'frame-%05d.jpg')],check=True)
    audio=out/'audio.wav'
    audio_result=subprocess.run([require('ffmpeg'),'-hide_banner','-loglevel','error','-i',str(copied),'-vn','-ac','1','-ar','16000',str(audio)])
    if audio_result.returncode: audio.unlink(missing_ok=True)
    manifest={'runId':rid,'source':video.name,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'durationSeconds':duration(copied),'frameIntervalSeconds':interval,'frames':[p.name for p in sorted(frames.glob('*.jpg'))],'audio':audio.name if audio.exists() else None,'immutable':True}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return {'directory':str(out),'manifest':manifest}

def transcribe(run_dir:Path,model_size:str='small')->Path|None:
    audio=run_dir/'audio.wav'
    if not audio.exists():return None
    try:from faster_whisper import WhisperModel
    except ImportError:raise RuntimeError("Install video support: pip install -e '.[video]'")
    model=WhisperModel(model_size,device='cpu',compute_type='int8')
    segments,_=model.transcribe(str(audio),vad_filter=True)
    data=[{'start':round(s.start,2),'end':round(s.end,2),'text':s.text.strip()} for s in segments]
    target=run_dir/'transcript.json';target.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8');return target
