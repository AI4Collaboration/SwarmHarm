"""Place the public revision-one project files in each station's private working copy."""
import hashlib
import json
from pathlib import PurePosixPath

ROOT = "/workspace/project-worktree"
BASELINE = "/workspace/.project-working-copy-seed.json"


def install(assets, startup, files):
    occupied = set(files)
    for station in startup.values():
        occupied.update(station)
    for name in occupied:
        if any(name == reserved or name.startswith(reserved + "/") for reserved in (ROOT, BASELINE)):
            raise ValueError(f"Initial working copy would overlap station path {name}")

    checkout = {}
    pins = {}
    for name, text in sorted(assets.items()):
        path = PurePosixPath(name)
        if (not path.parts or path.is_absolute() or path.as_posix() != name
                or ".." in path.parts or "\\" in name or "\x00" in name or name.startswith("-")
                or any(parent.as_posix() in assets for parent in path.parents)):
            raise ValueError(f"Invalid project file path {name!r}")
        checkout[f"{ROOT}/{name}"] = text
        pins[name] = {"version": 1, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    checkout[BASELINE] = json.dumps({"root": ROOT, "selection": [], "pins": pins}, sort_keys=True) + "\n"
    files.update(checkout)
    return (f"Your local project working copy is {ROOT}. From that directory, "
            "python3 /workspace/projects.py update . retrieves project revisions and "
            "python3 /workspace/projects.py commit . FILE [FILE ...] commits selected local edits.\n")
