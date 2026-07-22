from pathlib import Path
import pytest
from record_replay.model import Action,Workflow
from record_replay.storage import load,save
from record_replay.variables import parse,resolve
from record_replay.model import Playbook,PlaybookStep
from record_replay.playbook import export_all

def test_round_trip(tmp_path:Path):
    wf=Workflow(name="Example",actions=[Action(kind="type",value="${NAME}")])
    target=tmp_path/"flow.yml";save(wf,target)
    assert load(target)==wf

def test_variables():
    assert resolve("Hello ${NAME}",{"NAME":"Caleb"})=="Hello Caleb"
    assert parse(["NAME=Caleb"])=={"NAME":"Caleb"}

def test_missing_variable_fails(monkeypatch):
    monkeypatch.delenv("SECRET",raising=False)
    with pytest.raises(ValueError):resolve("${SECRET}",{})

def test_coordinate_required():
    with pytest.raises(ValueError):Action(kind="click")

def test_model_neutral_exports(tmp_path:Path):
    p=Playbook(name="Publish Promo",purpose="Publish a verified promo.",source_video="demo.mp4",steps=[PlaybookStep(order=1,title="Preview",instruction="Open preview.",evidence=["frame-00001.jpg"],verification="Preview appears."),PlaybookStep(order=2,title="Publish",instruction="Select publish.",destructive=True,verification="Confirmation appears.")])
    export_all(p,tmp_path)
    assert {"PLAYBOOK.md","SKILL.md","CLAUDE.md","GEMINI.md"} <= {x.name for x in tmp_path.iterdir()}
    assert "Confirmation required" in (tmp_path/"PLAYBOOK.md").read_text()
