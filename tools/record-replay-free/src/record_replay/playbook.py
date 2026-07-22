from __future__ import annotations
import json
from pathlib import Path
from .model import Playbook

def load(path:Path)->Playbook:return Playbook.model_validate_json(path.read_text(encoding='utf-8'))

def markdown(p:Playbook,title:str|None=None)->str:
    inputs='\n'.join(f"- `{k}`: {v}" for k,v in p.inputs.items()) or '- None declared.'
    steps=[]
    for s in p.steps:
        warning=' **Confirmation required.**' if s.destructive else ''
        ev=', '.join(f'`{x}`' for x in s.evidence) or 'not specified'
        steps.append(f"{s.order}. **{s.title}.** {s.instruction}{warning}\n   - Evidence: {ev}\n   - Verify: {s.verification or 'Confirm expected state.'}")
    uncertainty='\n'.join(f'- {x}' for x in p.uncertainties) or '- None recorded.'
    success='\n'.join(f'- {x}' for x in p.success_criteria) or '- Confirm the intended final state.'
    return f"# {title or p.name}\n\n{p.purpose}\n\n## Inputs\n\n{inputs}\n\n## Steps\n\n"+'\n'.join(steps)+f"\n\n## Success criteria\n\n{success}\n\n## Uncertainties\n\n{uncertainty}\n"

def export_all(p:Playbook,out:Path)->None:
    out.mkdir(parents=True,exist_ok=True)
    base=markdown(p);(out/'PLAYBOOK.md').write_text(base,encoding='utf-8')
    front=f"---\nname: {p.name.lower().replace(' ','-')}\ndescription: {p.purpose}\n---\n\n"
    (out/'SKILL.md').write_text(front+base,encoding='utf-8')
    (out/'CLAUDE.md').write_text(base+'\nFollow project CLAUDE.md rules and request confirmation for destructive steps.\n',encoding='utf-8')
    (out/'GEMINI.md').write_text(base+'\nFollow project GEMINI.md rules and request confirmation for destructive steps.\n',encoding='utf-8')
