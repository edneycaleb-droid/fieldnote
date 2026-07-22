from __future__ import annotations
import os, re
PATTERN=re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")

def resolve(text: str, supplied: dict[str,str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key=match.group(1)
        if key in supplied:return supplied[key]
        if key in os.environ:return os.environ[key]
        raise ValueError(f"Missing workflow input: {key}")
    return PATTERN.sub(repl,text)

def parse(items:list[str]) -> dict[str,str]:
    result={}
    for item in items:
        if "=" not in item: raise ValueError("Inputs must use NAME=value")
        key,value=item.split("=",1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*",key):raise ValueError(f"Invalid input name: {key}")
        result[key]=value
    return result
