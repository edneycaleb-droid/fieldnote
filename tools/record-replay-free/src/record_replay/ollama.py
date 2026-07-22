from __future__ import annotations
import base64,json,urllib.request
from pathlib import Path
from .model import Playbook

SYSTEM="""Convert screen-recording evidence into a precise, model-neutral playbook. Use only visible evidence and transcript facts. Parameterize changing values as uppercase inputs. Flag uncertainty. Mark send, publish, delete, purchase, permission, and submission steps destructive. Return JSON matching: {name,purpose,source_video,model_neutral,inputs,steps:[{order,title,instruction,evidence,inputs,verification,destructive}],success_criteria,uncertainties}."""

def generate(run_dir:Path,model:str='qwen3-vl:30b',host:str='http://127.0.0.1:11434')->Playbook:
    manifest=json.loads((run_dir/'manifest.json').read_text(encoding='utf-8'))
    transcript=(run_dir/'transcript.json').read_text(encoding='utf-8') if (run_dir/'transcript.json').exists() else '[]'
    frames=sorted((run_dir/'frames').glob('*.jpg'))[:24]
    payload={'model':model,'stream':False,'format':'json','messages':[{'role':'system','content':SYSTEM},{'role':'user','content':f"Manifest: {json.dumps(manifest)}\nTranscript: {transcript}",'images':[base64.b64encode(p.read_bytes()).decode() for p in frames]}],'options':{'temperature':0.1}}
    req=urllib.request.Request(host.rstrip('/')+'/api/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=600) as response:data=json.load(response)
    content=data['message']['content'];playbook=Playbook.model_validate_json(content)
    target=run_dir/'playbook.json';target.write_text(playbook.model_dump_json(indent=2)+'\n',encoding='utf-8');return playbook
