"""Open or file a booking's raw weighbridge ticket."""
import argparse
import base64
import csv
import difflib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def write_revision(client, name, path, version):
    config = json.loads(Path("/workspace/project-access.json").read_bytes())
    if config["interface"] == "socket":
        from socket_worktree import request
        return request(config, "write", name=name,
                       data=base64.b64encode(path.read_bytes()).decode(), base_version=version)
    result = subprocess.run([*client, "write", name, path, "--if-version", str(version)], capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return json.loads(result.stdout)


def terminal_command(terminal):
    # Project checkouts preserve file bytes but do not carry executable modes.
    with terminal.open("rb") as source:
        shebang = source.readline(256).strip()
    if terminal.suffix == ".py" or shebang in (b"#!/usr/bin/env python3", b"#!/usr/bin/python3"):
        return [sys.executable, str(terminal)]
    return [str(terminal)]


def ledger(args, parser, client):
    if not args.booking or args.version is not None or ((args.check_ledger or args.working) and args.if_version is not None):
        parser.error("Select a booking; historical ticket revisions are for retrieval")
    catalog = {r["name"]: r for r in json.loads(subprocess.check_output([*client, "list"]))["artifacts"]}
    desk = Path("/workspace")

    def filed_copy(name):
        row = catalog[name]
        reply = json.loads(subprocess.check_output(
            [*client, "read", name, "--version", str(row["version"])]))
        data = reply["text"].encode()
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            parser.error(f"Filed material differs from its registered bytes: {name}")
        return data

    orders = []
    for name in (f"orders/{args.booking}.json", f"orders/{args.booking}-release.json"):
        path = desk / name
        copies = [path.read_bytes()] if path.is_file() else []
        if name in catalog and (not copies or hashlib.sha256(copies[0]).hexdigest() != catalog[name]["sha256"]):
            copies.append(filed_copy(name))
        for data in copies:
            order = json.loads(data)
            if order["booking"] == args.booking and order["status"] == "in force":
                orders.append(order["approved_edition"])
    if args.working or args.save_working:
        if args.edition is None:
            parser.error("Select an edition for the working ledger")
        edition = args.edition
    else:
        if not orders:
            parser.error(f"No in-force release order for {args.booking}")
        if len(set(orders)) != 1 or orders[0] not in ("A","B"):
            parser.error(f"Conflicting or invalid in-force editions for {args.booking}: {', '.join(orders)}")
        edition = orders[0]
        if args.edition is not None and args.edition != edition:
            parser.error(f"The release order approves {edition}")
    source = f"bookings/{args.booking}/{edition}"
    recipe = [f"{source}/job.json", f"{source}/ledger.sql"]
    filed_recipe = [name for name in recipe if not (desk/name).is_file()]
    for name in filed_recipe:
        if name not in catalog:
            parser.error(f"Booking material unavailable: {name}")
    ticket = f"{source}/loads.csv"
    local_ticket = desk / ticket
    if ticket not in catalog and not local_ticket.is_file():
        parser.error(f"Load sheet unavailable: {ticket}")
    terminal = args.check_ledger or args.issue_ledger
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        issued = root / "issued"
        selected = ["ledgers/bookings.csv", *filed_recipe]
        if ticket in catalog:
            selected.append(ticket)
        output = subprocess.check_output([*client, "checkout", str(issued), *selected])
        records = [json.loads(line) for line in output.splitlines()]
        catalog = {row["name"]:row for part in records for row in part.get("artifacts",())}
        receipts = {r["name"]:r for r in records if "saved_to" in r}
        job_path, sql_path = [(issued if name in filed_recipe else desk) / name for name in recipe]
        job = json.loads(job_path.read_bytes())
        if job != {"argv":["-csv","-batch",":memory:"],"product":"stdout","stdin":"ledger.sql"}:
            parser.error("Unexpected dispatch-ledger job format")
        sql = sql_path.read_bytes()
        if ticket in receipts:
            data = (issued / ticket).read_bytes()
            if local_ticket.is_file() and local_ticket.read_bytes() != data:
                parser.error(f"Filed load sheet differs from the delivered original: {ticket}")
        else:
            data = local_ticket.read_bytes()
        with (issued / "ledgers/bookings.csv").open(newline="") as stream:
            destinations = {r["booking"]:r["release_file"] for r in csv.DictReader(stream)}
        target = destinations[args.booking]
        if target != f"ledgers/{args.booking}.csv":
            parser.error("The release catalog no longer designates the standard booking ledger")
        if next(csv.reader(io.StringIO(data.decode())),None) != ["dock","shift","kg"]:
            parser.error("Filed ticket lacks the dock,shift,kg header")
        if args.working or args.save_working:
            target = f"working-ledgers/{args.booking}/{edition}.csv"
        prior = catalog.get(target, {})
        version = prior.get("version",0)
        if args.if_version is not None and args.if_version != version:
            parser.error(f"{target}: expected version {args.if_version}, current version {version}")

        def evaluate(label, executable):
            work = root / label
            work.mkdir()
            (work / "loads.csv").write_bytes(data)
            result = subprocess.run([*executable,*job["argv"]],cwd=work,input=sql,capture_output=True)
            if result.returncode:
                message = result.stderr.decode(errors="replace").strip()
                raise ValueError(f"{label} exited {result.returncode}: {message}")
            return result.stdout

        stock = evaluate("reference",[sys.executable,"/workspace/dock_reference.py"])
        candidate = evaluate("terminal", terminal_command(terminal.resolve(strict=True))) if terminal else stock
        if candidate != stock:
            diff = difflib.unified_diff(stock.decode(errors="replace").splitlines(),
                                        candidate.decode(errors="replace").splitlines(),
                                        fromfile="stock ledger",tofile="selected terminal",lineterm="")
            print("\n".join(diff) or "Ledger differs in byte formatting",file=sys.stderr)
            return 1
        digest = hashlib.sha256(stock).hexdigest()
        report = {"booking":args.booking,"edition":edition,"ticket":ticket,
                  "ticket_version":receipts.get(ticket, {}).get("version"),"ticket_sha256":hashlib.sha256(data).hexdigest(),
                  "ledger":target,"sha256":digest,"csv":stock.decode(),"current_version":version}
        if args.issue_ledger is not None or args.save_working:
            if prior.get("sha256") == digest:
                report["already_filed" if args.save_working else "already_issued"] = True
            else:
                path = root / "ledger.csv"
                path.write_bytes(stock)
                ack = write_revision(client, target, path, version)
                if ack["sha256"] != digest:
                    raise ValueError("Release receipt differs from the verified ledger")
                report["working_copy" if args.save_working else "release"] = ack
        print(json.dumps(report))
        return 0


def file_ticket(client, name, path, expected, parser):
    data = path.read_bytes()
    if next(csv.reader(io.StringIO(data.decode(), newline="")), None) != ["dock", "shift", "kg"]:
        parser.error("Expected a load sheet with dock,shift,kg columns")
    digest = hashlib.sha256(data).hexdigest()

    def existing_receipt():
        rows = json.loads(subprocess.check_output([*client, "list"]))["artifacts"]
        current = next((row for row in rows if row["name"] == name), None)
        if current is None:
            return False
        if current["sha256"] != digest or current["bytes"] != len(data):
            parser.exit(1, f"{name}: expected version 0, current version {current['version']}\n")
        print(json.dumps({**current, "already_filed": True}))
        return True

    if expected is None and existing_receipt():
        return 0
    with TemporaryDirectory() as scratch:
        frozen = Path(scratch) / "loads.csv"
        frozen.write_bytes(data)
        version = 0 if expected is None else expected
        try:
            receipt = write_revision(client, name, frozen, version)
        except RuntimeError as error:
            conflict = f"{name}: expected version 0, current version "
            if expected is None and str(error).startswith(conflict) and existing_receipt():
                return 0
            parser.exit(1, f"{error}\n")
    print(json.dumps(receipt))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("booking", nargs="?", choices=("north", "crossing", "harbor"))
    parser.add_argument("edition", nargs="?", choices=("A", "B"))
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--file", nargs="?", const="", help="File the delivered load sheet or the selected path")
    actions.add_argument("--output", type=Path, help="Save the retrieved load sheet to a local path")
    actions.add_argument("--check-ledger", type=Path, metavar="TERMINAL", help="Check the signed booking ledger against stock DuckDB using the filed ticket")
    actions.add_argument("--issue-ledger", type=Path, metavar="TERMINAL", help="Issue the signed ledger after the selected terminal agrees with stock DuckDB")
    actions.add_argument("--working", action="store_true", help="Preview the edition’s working ledger on the deployed terminal")
    actions.add_argument("--save-working", action="store_true", help="Record the edition’s working ledger separately from its signed release")
    actions.add_argument("--open-working", action="store_true", help="Retrieve the recorded edition-specific working ledger")
    parser.add_argument("--version", type=int, help="Open this historical revision")
    parser.add_argument("--if-version", type=int, help="Revise this issued ticket (default: new ticket)")
    args = parser.parse_args()
    client = [sys.executable, "/workspace/projects.py"]
    if args.open_working:
        if not args.booking or not args.edition or args.if_version is not None:
            parser.error("Select a booking and edition to read a working ledger")
        command = [*client, "read", f"working-ledgers/{args.booking}/{args.edition}.csv"]
        if args.version is not None:
            command.extend(["--version", str(args.version)])
        return subprocess.call(command)
    if args.check_ledger or args.issue_ledger or args.working or args.save_working:
        try:
            return ledger(args,parser,client)
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
            parser.exit(2, f"{error}\n")
    delivery = json.loads(Path("/workspace/intake-delivery.json").read_bytes())
    if args.booking is None and args.edition is None and all(value is None for value in
                                                            (args.file,args.output,args.version,args.if_version)):
        index = {row["name"]: row for row in
                 json.loads(subprocess.check_output([*client,"list"]))["artifacts"]
                 if row["name"].startswith("bookings/") and row["name"].endswith("/loads.csv")}
        print(json.dumps({"delivered": [{**ticket, "filed_revision": index.get(ticket["name"],{}).get("version")}
                                       for ticket in delivery], "register": list(index.values())}))
        return 0
    if args.booking is None or args.edition is None:
        parser.error("Select a booking and edition")
    name = f"bookings/{args.booking}/{args.edition}/loads.csv"
    if args.file is not None:
        if args.version is not None:
            parser.error("--version is for reading")
        ticket = next((item for item in delivery if item["name"] == name),None)
        if not args.file and not ticket:
            parser.error("No scale delivery for this booking and edition at this workstation")
        path = Path(args.file or ticket["path"])
        return file_ticket(client, name, path, args.if_version, parser)
    if args.if_version is not None:
        parser.error("--if-version applies when filing a ticket")
    command = [*client, "read", name]
    if args.version is not None:
        command.extend(["--version", str(args.version)])
    if args.output is not None:
        command.extend(["--output", args.output])
    return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())

