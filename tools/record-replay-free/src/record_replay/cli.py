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
    a=p.parse_args()
    if a.cmd=="record":
        from .recorder import record;record(a.name,Path(a.output))
    elif a.cmd=="replay":
        from .replay import replay;replay(load(a.workflow),parse(a.input),a.execute,a.yes)
    elif a.cmd=="browser-record":
        from .browser import codegen;raise SystemExit(codegen(a.url,a.output))
    else:
        from .export_skill import export;export(load(a.workflow),Path(a.output))

if __name__=="__main__":main()
