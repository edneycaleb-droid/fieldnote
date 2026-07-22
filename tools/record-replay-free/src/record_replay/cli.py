from __future__ import annotations
import argparse
from pathlib import Path
from .storage import load
from .variables import parse

def main():
    p=argparse.ArgumentParser(prog="rrf");sub=p.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("record");r.add_argument("name");r.add_argument("--output",default="workflow.yml")
    x=sub.add_parser("replay");x.add_argument("workflow");x.add_argument("--execute",action="store_true");x.add_argument("--yes",action="store_true");x.add_argument("--input",action="append",default=[])
    b=sub.add_parser("browser-record");b.add_argument("url");b.add_argument("--output",default="browser_workflow.py")
    e=sub.add_parser("export-skill");e.add_argument("workflow");e.add_argument("--output",default="SKILL.md")
    v=sub.add_parser("video-ingest");v.add_argument("video");v.add_argument("--runs",default="runs");v.add_argument("--interval",type=float,default=3.0);v.add_argument("--transcribe",action="store_true");v.add_argument("--whisper-model",default="small")
    g=sub.add_parser("video-playbook");g.add_argument("run_dir");g.add_argument("--model",default="qwen3-vl:30b");g.add_argument("--ollama",default="http://127.0.0.1:11434")
    m=sub.add_parser("export-playbook");m.add_argument("playbook");m.add_argument("--output",default="exports")
    a=p.parse_args()
    if a.cmd=="record":
        from .recorder import record;record(a.name,Path(a.output))
    elif a.cmd=="replay":
        from .replay import replay;replay(load(a.workflow),parse(a.input),a.execute,a.yes)
    elif a.cmd=="browser-record":
        from .browser import codegen;raise SystemExit(codegen(a.url,a.output))
    elif a.cmd=="export-skill":
        from .export_skill import export;export(load(a.workflow),Path(a.output))
    elif a.cmd=="video-ingest":
        from .video import extract,transcribe
        result=extract(Path(a.video),Path(a.runs),a.interval);print(result['directory'])
        if a.transcribe:transcribe(Path(result['directory']),a.whisper_model)
    elif a.cmd=="video-playbook":
        from .ollama import generate;generate(Path(a.run_dir),a.model,a.ollama);print(Path(a.run_dir)/'playbook.json')
    else:
        from .playbook import export_all,load as load_playbook;export_all(load_playbook(Path(a.playbook)),Path(a.output))

if __name__=="__main__":main()
