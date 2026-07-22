from __future__ import annotations
import subprocess
def codegen(url:str,output:str)->int:
    return subprocess.call(["playwright","codegen","--target","python","--output",output,url])
