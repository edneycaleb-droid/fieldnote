from __future__ import annotations
import platform,time
from pathlib import Path
from .model import Action,Workflow
from .storage import save

def record(name:str,output:Path)->None:
    from pynput import keyboard,mouse
    actions:list[Action]=[]; started=time.monotonic(); last=started
    def gap():
        nonlocal last
        now=time.monotonic(); delta=now-last; last=now
        if delta>.7: actions.append(Action(kind="wait",seconds=round(min(delta,5),2)))
    def click(x,y,button,pressed):
        if pressed:gap();actions.append(Action(kind="click",x=int(x),y=int(y),button=str(button).split('.')[-1]))
    def scroll(x,y,dx,dy):gap();actions.append(Action(kind="scroll",x=int(x),y=int(y),value=str(int(dy))))
    held:set[str]=set()
    def press(key):
        text=str(key).replace('Key.','').strip("'")
        if text in {'ctrl','ctrl_l','ctrl_r','alt','alt_l','alt_r','shift','shift_l','shift_r','cmd','cmd_l','cmd_r'}:held.add(text.split('_')[0]);return
        if held:gap();actions.append(Action(kind="hotkey",value='+'.join(sorted(held)+[text])))
    def release(key):
        text=str(key).replace('Key.','').strip("'").split('_')[0];held.discard(text)
        if key==keyboard.Key.f12:return False
    print("Recording clicks, scrolling, and hotkeys. Text is intentionally not captured. Press F12 to stop.")
    ml=mouse.Listener(on_click=click,on_scroll=scroll);kl=keyboard.Listener(on_press=press,on_release=release);ml.start();kl.start();kl.join();ml.stop()
    wf=Workflow(name=name,description="Locally recorded workflow. Replace typed values with ${VARIABLE} actions before replay.",platform=platform.system(),actions=actions,success_criteria=["Operator verifies the intended final state"])
    save(wf,output);print(output)
