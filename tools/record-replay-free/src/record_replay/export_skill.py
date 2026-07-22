from __future__ import annotations
from pathlib import Path
from .model import Workflow

def export(workflow:Workflow,target:Path)->None:
    actions='\n'.join(f"{i}. `{a.kind}` — {a.note or 'Replay the recorded action.'}" for i,a in enumerate(workflow.actions,1))
    inputs='\n'.join(f"- `{k}`: {v}" for k,v in workflow.inputs.items()) or "- None declared."
    checks='\n'.join(f"- {x}" for x in workflow.success_criteria) or "- Confirm the intended final state."
    text=f'''---
name: {workflow.name.lower().replace(' ','-')}
description: {workflow.description or 'Replay a demonstrated workflow safely.'}
---

# {workflow.name}

## Inputs

{inputs}

## Safety

Run a dry-run first. Never persist secrets in workflow files. Require confirmation for destructive actions and stop when verification fails.

## Steps

{actions}

## Verification

{checks}
'''
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
