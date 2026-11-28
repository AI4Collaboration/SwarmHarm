"""Materialize a pinned mapped checkout in the calling process."""
import base64
import json
from pathlib import Path
import sys


def mapped_checkout_call(arguments):
    operation = arguments[0]
    if operation == "list":
        result = store.mapped_request({"operation": "list"})
    else:
        _, name, _, version, _, output = arguments
        result = store.mapped_request({"operation": "read", "name": name, "version": int(version)})
        Path(output).write_bytes(base64.b64decode(result.pop("data"), validate=True))
        result["saved_to"] = output
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


if __name__ == "__main__" and sys.argv[1:2] == ["checkout"]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import formation_store as store
    store.client_call = mapped_checkout_call
    raise SystemExit(store.main())

"""Work on named files from the versioned project cache using ordinary commands."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

# The workstation seeds the cache with run_path in an isolated interpreter.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import formation_store as store
mapped_request = store.mapped_request


def client_call(arguments):
    # Each object operation has its own process and ordinary project receipt.
    output = subprocess.check_output([sys.executable, str(Path(__file__).resolve()), *arguments])
    receipt = json.loads(output)
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()
    return receipt


def conditional_write(arguments):
    parser = argparse.ArgumentParser(prog="projects.py write")
    parser.add_argument("name")
    parser.add_argument("file", type=Path)
    parser.add_argument("--if-version", required=True, type=int)
    args = parser.parse_args(arguments)
    apply_record = store.apply

    def apply_checked(state, request):
        if "if_version" in request:
            current = len(state.get("objects", {}).get(request["name"], ()))
            if current != request["if_version"]:
                raise ValueError(f"{request['name']}: expected version {request['if_version']}, current version {current}")
        return apply_record(state, request)

    # mapped_request applies the new record while holding the cache's write lock.
    store.apply = apply_checked
    try:
        record = store.mapped_request(dict(operation="write", name=args.name, if_version=args.if_version,
                                           data=base64.b64encode(args.file.read_bytes()).decode()))
    finally:
        store.apply = apply_record
    print(json.dumps(record))


def work(arguments):
    cut = arguments.index("--")
    names, command = arguments[:cut], arguments[cut+1:]
    if not names or len(set(names)) != len(names) or not command:
        raise ValueError("Select distinct project files and a command after --")
    index = {item["name"]: item for item in store.mapped_request({"operation":"list"})["artifacts"]}
    root = Path(tempfile.mkdtemp(prefix="project-work-"))
    retain = False
    try:
        paths = {name:store.artifact_path(root, name) for name in names}
        for name, path in paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if name in index:
                item = index[name]
                receipt = mapped_checkout_call(["read", name, "--version", str(item["version"]), "--output", str(path)])
                if receipt["sha256"] != item["sha256"] or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError(f"Checkout does not match the requested version: {name}")
        retain = True
        status = subprocess.run(command, cwd=root).returncode
        if status:
            return status if status > 0 else 128-status
        for name in names:
            path = store.artifact_path(root, name)
            item = index.get(name, {})
            if not item and not path.exists():
                continue
            if not path.is_file():
                raise ValueError(f"Expected a regular project file: {name}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
                client_call(["write", name, str(path), "--if-version", str(item.get("version",0))])
        retain = False
        return 0
    finally:
        if retain:
            print(f"Local project files retained in {root}", file=sys.stderr)
        else:
            shutil.rmtree(root)


if __name__ == "__main__":
    args = sys.argv[1:]
    try:
        if args[:1] == ["work"]:
            raise SystemExit(work(args[1:]))
        if args[:1] == ["write"] and "--if-version" in args:
            conditional_write(args[1:])
        else:
            if args in (["-h"], ["--help"]):
                print("work PATH [PATH ...] -- COMMAND [ARG ...] runs a command on named project files. Changes to those files are saved on success if the base version still matches. Failed commands or saves retain the working directory. Each file is committed independently.")
            store.client_call = client_call
            raise SystemExit(store.main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
