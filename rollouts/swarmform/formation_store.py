"""Ordinary versioned work artifacts over a service or a local mapped cache."""
import argparse
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import mmap
import os
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



def main():
    parser = argparse.ArgumentParser(description="List, read and retain versions of project work artifacts.")
    parser.add_argument("operation", choices=("list", "read", "write"))
    parser.add_argument("name", nargs="?")
    parser.add_argument("file", nargs="?", help="Local file to retain for write")
    parser.add_argument("--version", type=int, help="Version to retrieve; defaults to latest")
    parser.add_argument("--output", help="Save the retrieved bytes to a local file")
    args = parser.parse_args()
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
        with urlopen(http, timeout=15) as response:
            result = json.load(response)
    if "data" in result:
        content = base64.b64decode(result.pop("data"))
        if args.output:
            Path(args.output).write_bytes(content)
            result["saved_to"] = args.output
        else:
            result["text"] = content.decode("utf-8", errors="replace")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
