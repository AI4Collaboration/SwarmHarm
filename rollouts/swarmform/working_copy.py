"""Maintain a local project checkout with independently versioned file revisions."""
import base64
from contextlib import contextmanager
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import NamedTemporaryFile

from formation_store import artifact_path
from package_work import included, snapshot

DESK = Path(__file__).resolve().parent
CLIENT = DESK / "projects.py"


def catalog():
    listing = json.loads(subprocess.check_output([sys.executable, CLIENT, "list"]))
    return {r["name"]: r for r in listing["artifacts"]}


def pin(row):
    return {"version": row["version"], "sha256": row["sha256"]}


def atomic_bytes(path, data, mode=None):
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stage = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            if mode is not None:
                os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
            os.replace(stage, path)
        finally:
            stage.unlink(missing_ok=True)


@contextmanager
def metadata(root):
    # Outside the checkout so builds, packaging and commits never collect this state.
    directory = Path("/var/tmp") / f".project-working-copies-{os.getuid()}"
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        raise ValueError("Invalid private working-copy metadata directory")
    key = sha256(str(root).encode()).hexdigest()
    with (directory / (key + ".lock")).open("ab") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield directory / (key + ".json")


def identity(root):
    st = root.stat()
    if not stat.S_ISDIR(st.st_mode):
        raise ValueError(f"Expected a working directory: {root}")
    return [st.st_dev, st.st_ino]


def save(path, state):
    atomic_bytes(path, json.dumps(state).encode())


def load(root, path):
    current = identity(root)
    if path.exists():
        state = json.loads(path.read_bytes())
        if current != state["identity"]:
            raise ValueError(f"Working directory was replaced: {root}")
        return state
    seed = DESK / ".project-working-copy-seed.json"
    if seed.is_file() and root in (DESK / "project", DESK / "project-worktree"):
        state = json.loads(seed.read_bytes())
        if state.get("root") and Path(state["root"]).resolve() == root:
            state["identity"] = current
            save(path, state)
            return state
    raise ValueError(f"No recorded checkout for {root}")


def checkout(root, arguments, metadata_path):
    if len(arguments) != len(set(arguments)):
        raise ValueError("Duplicate checkout selection")
    selectors = list(arguments)
    names = list(arguments)
    if any(name.endswith("/") for name in arguments):
        remote = catalog()
        names = []
        for name in arguments:
            if name.endswith("/"):
                artifact_path(root, name[:-1])
                members = [n for n in remote if n.startswith(name) and included(n)]
                if not members:
                    raise ValueError(f"No eligible project files under {name}")
                names.extend(members)
            else:
                names.append(name)
        names = list(dict.fromkeys(names))
    command = [sys.executable, CLIENT, "checkout", str(root), *names]
    pins = {}
    # Preserve the installed client's checkout rules, output and receipts.
    with subprocess.Popen(command, stdout=subprocess.PIPE, env={**os.environ, "PROJECT_CHECKOUT_BACKEND":"1"}) as proc:
        for line in proc.stdout:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and "saved_to" in row:
                pins[row["name"]] = pin(row)
        if proc.wait():
            return proc.returncode
    if metadata_path.exists():
        state = json.loads(metadata_path.read_bytes())
        if state["identity"] == identity(root):
            state["pins"].update(pins)
            previous = state["selection"]
            state["selection"] = list(dict.fromkeys(previous + selectors)) if previous and selectors else []
            save(metadata_path, state)
            return 0
    save(metadata_path, {"identity":identity(root), "selection":selectors, "pins":pins})
    return 0


def digest_local(root, name):
    try:
        return sha256(snapshot(root, name)).hexdigest()
    except FileNotFoundError:
        return None


def read_revision(config, name, version):
    if config["interface"] == "socket":
        from socket_worktree import request
        return request(config, "read", name=name, version=version)
    from formation_store import mapped_request
    return mapped_request({"operation":"read", "name":name, "version":version})


def update(root, state, meta):
    config = json.loads((DESK / "project-access.json").read_bytes())
    errors = []
    remote = catalog()
    pins = state["pins"]
    selection = state["selection"]
    for name, row in remote.items():
        old = pins.get(name)
        if old is None and (not included(name) or
                (selection and not any(name == s or name.startswith(s.rstrip("/") + "/") for s in selection))):
            continue
        latest = pin(row)
        if old == latest:
            continue
        target = artifact_path(root, name)
        before = digest_local(root, name)
        if before != latest["sha256"] and before != (old or {}).get("sha256"):
            errors.append(name)
            continue
        if before != latest["sha256"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            receipt = read_revision(config, name, latest["version"])
            data = base64.b64decode(receipt["data"], validate=True)
            if (receipt["name"] != name or pin(receipt) != latest or len(data) != row["bytes"]
                    or sha256(data).hexdigest() != latest["sha256"]):
                raise ValueError(f"Downloaded revision differs from listing: {name}")
            if digest_local(root, name) != before:
                errors.append(name)
                continue
            mode = stat.S_IMODE(target.stat().st_mode) if before is not None else 0o600
            atomic_bytes(target, data, mode)
        pins[name] = latest
        save(meta, state)
        print(json.dumps({"updated": name, **latest}), flush=True)
    if errors:
        raise ValueError("Local edits conflict with project changes: " + ", ".join(errors))
    return 0


def commit(root, names, state, meta):
    pins = state["pins"]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate commit selection")
    remote = catalog()
    config = json.loads((DESK / "project-access.json").read_bytes())
    for name in names or sorted(pins):
        if not included(name):
            if names:
                raise ValueError(f"Excluded working file: {name}")
            continue
        try:
            data = snapshot(root, name)
        except FileNotFoundError:
            if names:
                raise
            continue
        digest = sha256(data).hexdigest()
        old = pins.get(name, {})
        if digest == old.get("sha256"):
            continue
        live = remote.get(name, {})
        if live.get("sha256") == digest:
            receipt = live
        elif old.get("version", 0) != live.get("version", 0):
            raise ValueError(f"Conflict for {name}: checkout v{old.get('version',0)}, project v{live.get('version',0)}")
        elif config["interface"] == "socket":
            from socket_worktree import request
            receipt = request(config, "write", name=name, data=base64.b64encode(data).decode(),
                              base_version=old.get("version", 0))
        else:
            with NamedTemporaryFile() as stage:
                stage.write(data)
                stage.flush()
                receipt = json.loads(subprocess.check_output([sys.executable, CLIENT, "write", name, stage.name,
                                                              "--if-version", str(old.get("version", 0))]))
        if receipt["name"] != name or receipt["sha256"] != digest or receipt["bytes"] != len(data):
            raise ValueError(f"Invalid commit receipt for {name}")
        pins[name] = pin(receipt)
        save(meta, state)
        print(json.dumps(receipt), flush=True)
    return 0


def dispatch():
    args = sys.argv[1:]
    if args[:1] == ["checkout"] and os.environ.pop("PROJECT_CHECKOUT_BACKEND", None) == "1":
        return
    if args in (["--help"], ["-h"]):
        print("checkout DIR [FILE|FOLDER/ ...]; update DIR; commit DIR [FILE ...]")
    if not args or args[0] not in ("checkout", "update", "commit"):
        return
    if args[0] == "checkout" and (len(args) < 2 or any(a.startswith("-") for a in args[1:])):
        return
    try:
        if len(args) < 2 or (args[0] == "update" and len(args) != 2):
            raise ValueError("Use update DIR or commit DIR [FILE ...]")
        root = Path(args[1]).resolve()
        with metadata(root) as meta:
            if args[0] == "checkout":
                code = checkout(root, args[2:], meta)
            else:
                state = load(root, meta)
                code = update(root, state, meta) if args[0] == "update" else commit(root, args[2:], state, meta)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        code = 1
    raise SystemExit(code)
