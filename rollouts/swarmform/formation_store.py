"""Ordinary versioned project storage over a service or mapped store."""
import argparse
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import mmap
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

HEADER = 40
CACHE = "/dev/shm/project-work-cache"


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def apply(state, request):
    operation = request["operation"]
    name = request.get("name", "")
    objects = state.setdefault("objects", {})
    if operation == "list":
        return {"artifacts": [
            {"name": key, "version": len(versions),
             "sha256": versions[-1]["sha256"], "bytes": versions[-1]["bytes"]}
            for key, versions in sorted(objects.items())]}
    if not isinstance(name, str) or not name or len(name) > 256:
        raise ValueError("Use a nonempty artifact name of at most 256 characters")
    if operation == "write":
        payload = base64.b64decode(request["data"], validate=True)
        record = {"data": request["data"], "bytes": len(payload),
                  "sha256": hashlib.sha256(payload).hexdigest()}
        versions = objects.setdefault(name, [])
        versions.append(record)
        return {"name": name, "version": len(versions), **{k: record[k] for k in ("bytes", "sha256")}}
    if operation != "read":
        raise ValueError("Unknown artifact operation")
    versions = objects.get(name)
    if not versions:
        raise ValueError("Artifact does not exist")
    version = request.get("version")
    if version is None:
        version = len(versions)
    if type(version) is not int or not 1 <= version <= len(versions):
        raise ValueError("Unknown artifact version")
    return {"name": name, "version": version, **versions[version - 1]}


@contextmanager
def cache_file(path=CACHE):
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if os.fstat(fd).st_size == 0:
            os.ftruncate(fd, 4096)
        yield fd
    finally:
        os.close(fd)


def mapped_request(request, path=CACHE):
    with cache_file(path) as fd:
        with mmap.mmap(fd, 0) as region:
            offset, state = 0, {"objects": {}}
            while offset + HEADER <= len(region):
                size = int.from_bytes(region[offset:offset + 8], "big")
                end = offset + HEADER + size
                if size == 0 or end > len(region):
                    break
                data = region[offset + HEADER:end]
                if hashlib.sha256(data).digest() != region[offset + 8:offset + HEADER]:
                    break
                record = json.loads(data)
                if "objects" in record:
                    state = record
                else:
                    apply(state, record)
                offset = end
        result = apply(state, request)
        if request["operation"] == "write":
            # Retain only the new write. Repeated full-state snapshots make
            # an ordinary growing artifact collection consume quadratic space.
            data = encode({"operation": "write", "name": request["name"], "data": request["data"]})
            end = offset + HEADER + len(data)
            os.ftruncate(fd, max(os.fstat(fd).st_size, (end + 4095) // 4096 * 4096))
            with mmap.mmap(fd, 0) as region:
                # New records append after the last valid commit. A torn final
                # record leaves that prior state readable and is replaced on retry.
                region[offset:offset + 8] = bytes(8)
                region[offset + HEADER:end] = data
                region[offset + 8:offset + HEADER] = hashlib.sha256(data).digest()
                region.flush()
                region[offset:offset + 8] = len(data).to_bytes(8, "big")
                region.flush()
        return result



def artifact_path(root, name):
    """Accept only unambiguous relative object paths inside root."""
    if (not isinstance(name, str) or not name or "\\" in name or "\x00" in name
            or name.startswith(("/", "-")) or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError(f"Unsafe artifact name: {name!r}")
    target = root.joinpath(*name.split("/"))
    current = root
    for part in name.split("/"):
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink in artifact path: {name!r}")
    return target


def client_call(arguments):
    """Use the unchanged one-object protocol and expose its normal receipts."""
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), *arguments],
                            capture_output=True, text=True)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        raise RuntimeError(f"Project operation failed: {arguments[0]}")
    record = json.loads(result.stdout)
    print(result.stdout, end="")
    return record


def checkout(directory, names):
    # Pin all reads to the exact versions in this single listing.
    listed = client_call(["list"])["artifacts"]
    index = {entry["name"]: entry for entry in listed}
    selected = names or list(index)
    if len(selected) != len(set(selected)):
        raise ValueError("Duplicate artifact name")
    root = Path(directory)
    for name in selected:
        artifact_path(root, name)
        if name not in index:
            raise ValueError(f"Unknown artifact: {name}")
    root.mkdir()  # Never replace, merge with, or clean up an existing directory.
    try:
        for name in selected:
            target = artifact_path(root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            item = index[name]
            client_call(["read", name, "--version", str(item["version"]),
                         "--output", str(target)])
            data = target.read_bytes()
            if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError(f"Downloaded bytes differ from listing: {name}")
    except BaseException:
        shutil.rmtree(root)
        raise


def save(directory, names):
    if not names or len(names) != len(set(names)):
        raise ValueError("Save requires distinct named artifacts")
    root = Path(directory)
    if not root.is_dir():
        raise ValueError("Save directory does not exist")
    # Validate the entire selection before appending any object version.
    for name in names:
        if not artifact_path(root, name).is_file():
            raise ValueError(f"Not a regular file: {name}")
    for name in names:
        client_call(["write", name, str(artifact_path(root, name))])


def main():
    parser = argparse.ArgumentParser(description="List, read and retain versions of project work artifacts.",
        epilog="checkout DIR [NAME ...] creates a new directory from one version-pinned listing; omitted names select all objects. save DIR NAME [NAME ...] appends only named files. Save is per-object: an error may leave earlier saves completed. Object names must be clean relative paths without a leading dash. These commands never execute downloaded files or synchronize automatically.")
    parser.add_argument("operation", choices=("list", "read", "write", "checkout", "save"))
    parser.add_argument("name", nargs="?")
    parser.add_argument("file", nargs="?", help="Local file for write; first selected object for checkout/save")
    parser.add_argument("names", nargs="*", help="Additional selected objects for checkout/save")
    parser.add_argument("--version", type=int, help="Version to retrieve; defaults to latest")
    parser.add_argument("--output", help="Save the retrieved bytes to a local file")
    args = parser.parse_args()
    if args.operation in ("checkout", "save"):
        if args.name is None or args.output is not None or args.version is not None:
            parser.error("checkout/save require DIR and do not accept --output/--version")
        selected = ([args.file] if args.file is not None else []) + args.names
        try:
            (checkout if args.operation == "checkout" else save)(args.name, selected)
        except (OSError, ValueError, RuntimeError) as error:
            parser.exit(1, f"{error}\n")
        return
    if args.names:
        parser.error("Extra object names are only valid for checkout/save")
    request = {"operation": args.operation, "name": args.name, "version": args.version}
    if args.operation == "write":
        if args.file is None:
            parser.error("write needs an artifact name and a local file")
        request["data"] = base64.b64encode(Path(args.file).read_bytes()).decode()
    config = json.loads(Path("/workspace/project-access.json").read_text())
    if config["interface"] == "mapped_memory":
        result = mapped_request(request)
    else:
        http = Request(config["url"] + "/artifacts", data=encode(request),
                       headers={"Authorization": config["key"], "Content-Type": "application/json"})
        from urllib.error import HTTPError
        try:
            with urlopen(http, timeout=15) as response:
                result = json.load(response)
        except HTTPError as error:
            try:
                detail = json.load(error)
            except (OSError, ValueError):
                raise error
            if not isinstance(detail, dict) or not isinstance(detail.get("error"), str):
                raise error
            print(json.dumps({"name": args.name, "error": detail["error"]}, ensure_ascii=False), file=sys.stderr)
            return 1
    if "data" in result:
        content = base64.b64decode(result.pop("data"))
        if args.output:
            Path(args.output).write_bytes(content)
            result["saved_to"] = args.output
        else:
            result["text"] = content.decode("utf-8", errors="replace")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
