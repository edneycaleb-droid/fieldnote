from __future__ import annotations
import time
from getpass import getpass
from .model import Workflow, Action
from .variables import resolve

def describe(a:Action)->str:
    bits=[a.kind]
    if a.x is not None:bits.append(f"({a.x},{a.y})")
    if a.value:bits.append(a.value if a.kind!="type" else "<text>")
    return " ".join(bits)

def replay(workflow:Workflow,values:dict[str,str],execute:bool=False,yes:bool=False)->None:
    if not execute:
        print(f"DRY RUN: {workflow.name}")
        for i,a in enumerate(workflow.actions,1): print(f"{i:03}: {describe(a)}")
        return
    import pyautogui
    pyautogui.FAILSAFE=True
    pyautogui.PAUSE=.12
    for i,a in enumerate(workflow.actions,1):
        if a.destructive and not yes:
            answer=input(f"Step {i} may be destructive ({describe(a)}). Continue? [y/N] ")
            if answer.lower()!="y":raise RuntimeError("Replay cancelled")
        if a.kind=="wait":time.sleep(a.seconds or 1)
        elif a.kind=="confirm":
            if not yes and input(f"Confirm: {a.note or 'continue'} [y/N] ").lower()!="y":raise RuntimeError("Replay cancelled")
        elif a.kind=="move":pyautogui.moveTo(a.x,a.y,duration=.2)
        elif a.kind=="click":pyautogui.click(a.x,a.y,button=a.button)
        elif a.kind=="double_click":pyautogui.doubleClick(a.x,a.y,button=a.button,interval=.12)
        elif a.kind=="scroll":pyautogui.scroll(int(a.value or "0"),x=a.x,y=a.y)
        elif a.kind=="hotkey":pyautogui.hotkey(*[x.strip() for x in resolve(a.value or "",values).split("+")])
        elif a.kind=="type":pyautogui.write(resolve(a.value or "",values),interval=.025)
        elif a.kind=="assert_pixel":
            expected=tuple(int(v) for v in resolve(a.value or "",values).split(","))
            actual=pyautogui.pixel(a.x or 0,a.y or 0)
            if sum(abs(int(actual[j])-expected[j]) for j in range(3))>45:raise AssertionError(f"Pixel assertion failed at {a.x},{a.y}: {actual} != {expected}")
