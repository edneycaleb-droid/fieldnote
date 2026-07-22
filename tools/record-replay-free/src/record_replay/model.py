from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

class Action(BaseModel):
    kind: Literal["click","double_click","move","scroll","hotkey","type","wait","confirm","assert_pixel"]
    x: int | None = None
    y: int | None = None
    value: str | None = None
    seconds: float | None = None
    button: Literal["left","right","middle"] = "left"
    destructive: bool = False
    note: str = ""

    @model_validator(mode="after")
    def required_fields(self):
        if self.kind in {"click","double_click","move","assert_pixel"} and (self.x is None or self.y is None):
            raise ValueError(f"{self.kind} requires x and y")
        if self.kind in {"hotkey","type"} and not self.value:
            raise ValueError(f"{self.kind} requires value")
        return self

class Workflow(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    version: int = 1
    platform: str = "cross-platform"
    inputs: dict[str, str] = Field(default_factory=dict)
    success_criteria: list[str] = Field(default_factory=list)
    actions: list[Action]

class PlaybookStep(BaseModel):
    order: int
    title: str
    instruction: str
    evidence: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    verification: str = ""
    destructive: bool = False

class Playbook(BaseModel):
    name: str
    purpose: str
    source_video: str
    model_neutral: bool = True
    inputs: dict[str,str] = Field(default_factory=dict)
    steps: list[PlaybookStep]
    success_criteria: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
