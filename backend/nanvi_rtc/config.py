"""Tiny .env loader (no dependency). Existing environment variables win over the file."""
from __future__ import annotations

import os
from pathlib import Path


def parse_env(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        elif " #" in v:
            v = v.split(" #", 1)[0].strip()
        out[k.strip()] = v
    return out


def load_env(*paths) -> list:
    loaded = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            for k, v in parse_env(p.read_text(encoding="utf-8")).items():
                if v != "":
                    os.environ.setdefault(k, v)
            loaded.append(str(p))
    return loaded


def describe() -> str:
    prov = os.environ.get("NANVI_LLM_PROVIDER", "mock")
    if prov == "groq":
        key, model = os.environ.get("GROQ_API_KEY"), os.environ.get("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
    elif prov == "gemini":
        key, model = os.environ.get("GEMINI_API_KEY"), os.environ.get("GEMINI_LLM_MODEL", "gemini-2.0-flash")
    else:
        key, model = "no key needed", "offline canned replies"
    status = "no key needed" if key == "no key needed" else ("API key found" if key else "NO API KEY: will fall back to mock")
    return f"provider={prov}  model={model}  ({status})"
