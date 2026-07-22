from __future__ import annotations
from pathlib import Path
import yaml
from .model import Workflow

def load(path: str | Path) -> Workflow:
    return Workflow.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

def save(workflow: Workflow, path: str | Path) -> None:
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(yaml.safe_dump(workflow.model_dump(exclude_none=True),sort_keys=False,allow_unicode=True),encoding="utf-8")
