"""Run a selected Ctags executable on the signed firmware source and its recorded job."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory

from formation_store import mapped_request
from index_compare import PROJECT, current_object, read_records
from difflib import unified_diff
from itertools import islice

WORKSPACE = Path("/workspace")
FIRMWARE_ARGV = ["--options=NONE", "--fields=+n", "--sort=yes", "-f", "-", "meters.cpp"]


def fetch(catalog, names, root):
    selected = [name for name in names if name in catalog]
    if not selected:
        return {}
    directory = root / "fetched"
    raw = subprocess.check_output([sys.executable, PROJECT, "checkout", str(directory), *selected])
    pins = {r["name"]: r for line in raw.splitlines() if "saved_to" in (r := json.loads(line))}
    contents = {}
    for name in selected:
        listed = catalog[name]
        read = pins[name]
        if read["version"] == listed["version"] and read["sha256"] == listed["sha256"]:
            contents[name] = (directory / name).read_bytes()
        else:
            contents[name] = current_object(catalog, name, root / "historical")
    return contents


def input_bytes(contents, name):
    local = WORKSPACE / name
    if name in contents:
        data = contents[name]
        if local.is_file() and local.read_bytes() != data:
            raise ValueError(f"Local input differs from filed {name}")
        return data
    if local.is_file():
        return local.read_bytes()
    raise ValueError(f"Missing booking input {name} in /workspace and project storage")


def build_index(operation, booking, program, check_reference=False, output=None):
    listed = mapped_request({"operation": "list"})
    catalog = {r["name"]:r for r in listed["artifacts"]}
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        order_name = "orders/" + booking + ".json"
        second = "orders/" + booking + "-release.json"
        local_order = WORKSPACE / order_name
        preferred = json.loads(local_order.read_bytes()).get("approved_edition") if local_order.is_file() else None
        names = [order_name, second]
        if operation != "check-index":
            names.append("indices/bookings.csv")
        if operation == "compare-index":
            names.append("indices/" + booking + ".tags")
        if preferred in ("A","B"):
            prefix = f"bookings/{booking}/{preferred}/"
            names.extend([prefix+"job.json",prefix+"meters.cpp"])
        contents = fetch(catalog,names,root)
        target = None
        if operation != "check-index":
            releases = csv.DictReader(io.StringIO(contents["indices/bookings.csv"].decode()))
            target = {row["booking"]: row["release_file"] for row in releases}[booking]
        orders = [json.loads(input_bytes(contents, order_name))]
        if second in catalog or (WORKSPACE / second).is_file():
            orders.append(json.loads(input_bytes(contents, second)))
        selected = {order["approved_edition"] for order in orders
                    if order["booking"] == booking and order["status"] == "in force"}
        if len(selected) != 1 or not selected <= {"A","B"}:
            raise ValueError(f"{booking}: expected one approved edition across applicable orders")
        edition = selected.pop()
        prefix = f"bookings/{booking}/{edition}/"
        extra = [name for name in [prefix+"job.json",prefix+"meters.cpp"] if name in catalog and name not in contents]
        if operation == "compare-index" and target in catalog and target not in contents:
            extra.append(target)
        if extra:
            more = root / "more"
            more.mkdir()
            contents.update(fetch(catalog,extra,more))
        job = json.loads(input_bytes(contents, prefix+"job.json"))
        if job != {"argv": FIRMWARE_ARGV, "product": "stdout", "stdin": None}:
            raise ValueError("Unrecognized firmware indexing job")
        source = input_bytes(contents, prefix+"meters.cpp")
        (root/"meters.cpp").write_bytes(source)
        executable = program.resolve(strict=True)
        command = [sys.executable, str(executable)] if executable.suffix == ".py" else [str(executable)]
        if check_reference:
            oracle = root / "reference"
            oracle.mkdir()
            (oracle / "meters.cpp").write_bytes(source)
            reference = subprocess.run(["/opt/programbench/invoke", "universal-ctags__ctags.243595e", *job["argv"]],
                                       cwd=oracle, stdin=subprocess.DEVNULL, capture_output=True, check=True)
        run = subprocess.run([*command, *job["argv"]], cwd=root, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE if check_reference else None)
        if check_reference:
            different = run.returncode != reference.returncode
            if different:
                print(f"{booking}/{edition}: candidate exit {run.returncode}, reference exit {reference.returncode}")
            for stream in ("stdout", "stderr"):
                expected, actual = getattr(reference, stream), getattr(run, stream)
                if expected != actual:
                    different = True
                    print(f"{stream}: candidate {len(actual)} bytes, reference {len(expected)} bytes")
                    diff = unified_diff(expected.decode(errors="replace").splitlines(keepends=True),
                                        actual.decode(errors="replace").splitlines(keepends=True),
                                        fromfile=f"{booking}/{edition}/reference.{stream}",
                                        tofile=f"{booking}/{edition}/candidate.{stream}")
                    sys.stdout.writelines(islice(diff, 60))
            if different:
                return 1
        run.check_returncode()
        records = read_records(run.stdout.decode())
        if not records:
            raise ValueError("The selected program produced an empty firmware index")
        if operation == "check-index":
            if output is not None:
                with NamedTemporaryFile(dir=output.parent, delete=False) as temp:
                    pending = Path(temp.name)
                    try:
                        temp.write(run.stdout)
                        temp.close()
                        pending.replace(output)
                    finally:
                        pending.unlink(missing_ok=True)
            print(json.dumps({"booking":booking,"edition":edition,"source":prefix+"meters.cpp",
                              "source_sha256":hashlib.sha256(source).hexdigest(),"records":len(records),
                              "index_sha256":hashlib.sha256(run.stdout).hexdigest(),
                              "local_output":str(output) if output else None}))
            return 0
        draft = root/"firmware.tags"
        draft.write_bytes(run.stdout)
        if operation == "compare-index":
            if target not in catalog:
                print(f"{target}: no issued index; {len(records)} records in {booking} {edition} build")
                return 1
            if contents[target] == run.stdout:
                print(f"{target} v{catalog[target]['version']}  {len(records)} records; Index bytes match.")
                return 0
            diff = unified_diff(contents[target].decode().splitlines(), run.stdout.decode().splitlines(),
                                fromfile=target, tofile=f"{booking} {edition} build", lineterm="")
            for line in islice(diff,60):
                print(line)
            return 1
        version = catalog.get(target, {}).get("version", 0)
        saved = json.loads(subprocess.check_output([sys.executable, PROJECT, "write", target,
                           str(draft), "--if-version", str(version)]))
        if saved["sha256"] != hashlib.sha256(run.stdout).hexdigest():
            raise ValueError("Issued bytes differ from the built firmware index")
        print(json.dumps({"booking":booking,"edition":edition,"source":prefix+"meters.cpp",
                          "source_sha256":hashlib.sha256(source).hexdigest(),"records":len(records),"release":saved}))
        return 0


def main(operation, arguments):
    parser = argparse.ArgumentParser(prog=f"projects.py {operation}",description=__doc__)
    parser.add_argument("booking",choices=("north","crossing","harbor"))
    parser.add_argument("--ctags",required=True,type=Path,help="Local Ctags executable to run on the signed booking")
    if operation == "check-index":
        parser.add_argument("--output", type=Path, help="Keep the qualified local index at this path")
    parser.add_argument("--check-reference", action="store_true", help="Compare the candidate streams with the deployed release")
    args = parser.parse_args(arguments)
    try:
        return build_index(operation,args.booking,args.ctags,operation == "check-index" or args.check_reference,
                           getattr(args, "output", None))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(2,f"{error}\n")
