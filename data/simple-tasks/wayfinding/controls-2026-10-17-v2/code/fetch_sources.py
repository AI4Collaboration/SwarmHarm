#!/usr/bin/env python3
"""Fetch pinned public source files, verify bytes, never execute or edit them."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parent


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify(data, entry):
    if len(data) != entry["size"]:
        raise ValueError(f"Wrong length: {entry['name']}")
    if "lfs_sha256" in entry and sha256(data) != entry["lfs_sha256"]:
        raise ValueError(f"Wrong LFS content: {entry['name']}")
    blob = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    if "git_blob_sha1" in entry and hashlib.sha1(blob).hexdigest() != entry["git_blob_sha1"]:
        raise ValueError(f"Wrong Git blob: {entry['name']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="A new operator-only directory")
    args = parser.parse_args()
    spec_bytes = (ROOT / "source-files.json").read_bytes()
    spec = json.loads(spec_bytes)
    names = [entry["name"] for entry in spec["files"]]
    if len(set(names)) != len(names) or any(Path(name).name != name for name in names):
        raise ValueError("Source names must be unique basenames")
    if any(not 0 < entry["size"] < 10_000_000 for entry in spec["files"]):
        raise ValueError("Unexpected source size")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "source-files.json").write_bytes(spec_bytes)

    def fetch(entry):
        path = urllib.parse.quote(spec["prefix"] + entry["name"], safe="/")
        url = f"https://huggingface.co/datasets/{spec['dataset']}/resolve/{spec['revision']}/{path}"
        request = urllib.request.Request(url, headers={"User-Agent": "SwarmHarm-source-audit/1"})
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read(entry["size"] + 1)
        verify(data, entry)
        with (output / entry["name"]).open("xb") as stream:
            stream.write(data)
        return {**entry, "sha256": sha256(data), "url": url, "verified": True}

    with ThreadPoolExecutor(max_workers=4) as pool:
        files = list(pool.map(fetch, spec["files"]))
    receipt = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": spec["dataset"], "revision": spec["revision"],
        "instance_id": spec["instance_id"], "files": files,
        "source_spec_sha256": sha256(spec_bytes),
        "downloader_sha256": sha256(Path(__file__).read_bytes()),
        "model_requests": 0, "source_tools_executed": 0,
    }
    (output / "source-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"verified_files": len(files), "bytes": sum(x["size"] for x in files),
                      "output": str(output), "model_requests": 0}))


if __name__ == "__main__":
    main()
