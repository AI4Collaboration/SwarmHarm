"""Version-checked directory saves for the Ctags project cache."""
import base64
import difflib
import hashlib
from itertools import islice
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

import formation_store as store

original_checkout, original_save = store.checkout, store.save
original_request = store.mapped_request


def show_difference(name, version, local):
    if not version:
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "current"
        result = subprocess.check_output([sys.executable, "/workspace/projects.py", "read", name,
                                          "--version", str(version), "--output", str(path)])
        record = json.loads(result)
        current = path.read_bytes()
        if hashlib.sha256(current).hexdigest() != record["sha256"]:
            raise ValueError(f"Project version hash mismatch: {name}")
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
    try:
        if b"\0" in current or b"\0" in local:
            raise ValueError("binary")
        before, after = (body.decode("utf-8").splitlines(keepends=True) for body in (current, local))
    except ValueError:
        print(f"{name}: binary difference, project v{version} {len(current)} bytes, draft {len(local)} bytes",
              file=sys.stderr)
        return
    lines = difflib.unified_diff(before, after, fromfile=f"{name} (project v{version})", tofile=f"{name} (local draft)")
    for line in islice(lines, 80):
        print(line.rstrip("\n")[:512], file=sys.stderr)
        if not line.endswith("\n"):
            print(r"\ No newline at end of file", file=sys.stderr)
    if next(lines, None) is not None:
        print("Additional differences omitted.", file=sys.stderr)


def checkout_index(root, create=False):
    stat = root.stat()
    identity = hashlib.sha256(f"{root.resolve()}:{stat.st_dev}:{stat.st_ino}".encode()).hexdigest()
    directory = Path("/workspace/.project-checkouts")
    index = directory / (identity + ".sqlite")
    if not create and not index.is_file():
        raise ValueError("Subdirectory saves require a directory created with projects.py checkout")
    directory.mkdir(exist_ok=True)
    db = sqlite3.connect(index)
    if create:
        db.execute("CREATE TABLE IF NOT EXISTS bases(name TEXT PRIMARY KEY, version INTEGER, sha TEXT)")
    return db


def checkout(directory, names):
    pins = []
    read_operation = store.client_call
    listing = None
    if any(name.endswith("/") for name in names):
        if len(names) != len(set(names)):
            raise ValueError("Duplicate artifact selection")
        listing = read_operation(["list"])
        items = [row["name"] for row in listing["artifacts"]]
        selected = []
        for name in names:
            if name.endswith("/"):
                store.artifact_path(Path(directory), name[:-1])
                members = [item for item in items if item.startswith(name)]
                if not members:
                    raise ValueError(f"Unknown project directory: {name}")
                selected.extend(members)
            else:
                selected.append(name)
        names = list(dict.fromkeys(selected))

    def fetch(arguments):
        if arguments == ["list"] and listing is not None:
            return listing
        receipt = read_operation(arguments)
        if arguments[0] == "read":
            pins.append((receipt["name"], receipt["version"], receipt["sha256"]))
        return receipt

    root = Path(directory)
    existing = root.exists()
    if existing:
        from mapped_selected_checkout import checkout as checkout_selected
        if listing is None:
            listing = read_operation(["list"])
        pins = checkout_selected(directory, names, listing["artifacts"])
    else:
        store.client_call = fetch
        try:
            original_checkout(directory, names)
        finally:
            store.client_call = read_operation
    with checkout_index(root, create=True) as db:
        if not existing:
            db.execute("DELETE FROM bases")
        db.executemany("INSERT OR REPLACE INTO bases VALUES (?, ?, ?)", pins)


def save(directory, names):
    root = Path(directory)
    subtree = len(names) == 1 and names[0].endswith("/")
    if subtree:
        folder = store.artifact_path(root, names[0][:-1])
        if not folder.is_dir():
            raise ValueError(f"Not a project directory: {names[0]}")
        paths = sorted(folder.rglob("*"))
    else:
        if not names or len(names) != len(set(names)):
            raise ValueError("Save requires distinct named artifacts")
        try:
            index = checkout_index(root)
        except (FileNotFoundError, ValueError):
            return original_save(directory, names)
        paths = [store.artifact_path(root, name) for name in names]
    with (checkout_index(root) if subtree else index) as db, tempfile.TemporaryDirectory() as stage:
        db.execute("BEGIN IMMEDIATE")
        bases = {name: (v, h) for name, v, h in db.execute("SELECT name, version, sha FROM bases")}
        live = {r["name"]: (r["version"], r["sha256"]) for r in store.mapped_request({"operation": "list"})["artifacts"]}
        changes = []
        for path in paths:
            name = path.relative_to(root).as_posix()
            path = store.artifact_path(root, name)
            if subtree and path.is_dir():
                continue
            if not path.is_file():
                raise ValueError(f"Expected a regular project file: {name}")
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            version, base_hash = bases.get(name, (0, None))
            if subtree and digest == base_hash:
                continue
            current, current_hash = live.get(name, (0, None))
            if current != version and current_hash == digest:
                db.execute("INSERT OR REPLACE INTO bases VALUES (?, ?, ?)", (name, current, digest))
                continue
            if current != version:
                show_difference(name, current, data)
                raise ValueError(f"{name}: expected version {version}, current version {current}")
            snapshot = Path(stage) / str(len(changes))
            snapshot.write_bytes(data)
            changes.append((name, snapshot, version))
        for name, snapshot, version in changes:
            result = store.client_call(["write", name, str(snapshot), "--if-version", str(version)])
            db.execute("INSERT OR REPLACE INTO bases VALUES (?, ?, ?)", (name, result["version"], result["sha256"]))


def checked_request(request):
    try:
        return original_request(request)
    except ValueError as error:
        # The cache writer releases its lock before an exact version is read.
        if request.get("operation") == "write" and "if_version" in request:
            prefix = f"{request['name']}: expected version {request['if_version']}, current version "
            if str(error).startswith(prefix) and str(error)[len(prefix):].isdigit():
                show_difference(request["name"], int(str(error)[len(prefix):]), base64.b64decode(request["data"]))
        raise


def install():
    store.checkout, store.save, store.mapped_request = checkout, save, checked_request
    if sys.argv[1:2] == ["check-index"]:
        from ctags_booking_index import main
        raise SystemExit(main("check-index", sys.argv[2:]))
    if sys.argv[1:2] in (["compare-index"], ["issue-index"]):
        from index_compare import main
        raise SystemExit(main(sys.argv[1], sys.argv[2:]))
    if sys.argv[1:] in (["--help"], ["-h"]):
        print("check-index BOOKING --ctags PROGRAM [--output FILE] checks a local executable against the deployed Ctags job and optionally keeps its qualified index locally.")
        print("checkout DIR archive/ software/ selects all objects under the named project directories from one version listing.")
        print("compare-index BOOKING FILE compares the issued symbol index with a local candidate using tag_records. issue-index BOOKING FILE issues just the chosen index.")
        print("save CHECKOUT SUBDIR/ saves changed files below that directory. Saves from a checkout use its recorded versions. Conflicts display the project and local revisions and retain the checkout.")
