from pathlib import Path
import pytest
from record_replay.model import Action,Workflow
from record_replay.storage import load,save
from record_replay.variables import parse,resolve

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
