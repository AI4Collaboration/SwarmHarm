"""Open an issued port statement or retain and inspect an edition-specific draft."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys


def statement(record):
    text = record["text"]
    raw = text.encode("utf-8")
    if len(raw) != record["bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
        raise ValueError("Published statement does not match its recorded byte count and checksum")
    balances, transfers, other = [], [], []
    for row in csv.reader(io.StringIO(text, newline=""), strict=True):
        if len(row) == 3 and row[0] == "received":
            transfers.append({"status": "received", "transfer": row[1], "quantity": row[2]})
        elif len(row) == 2 and row[0] == "pending":
            transfers.append({"status": "pending", "transfer": row[1]})
        elif len(row) == 2 and row[1].isdigit():
            balances.append({"account": row[0], "quantity": row[1]})
        else:
            other.append(row)
    return {**record, "balances": balances, "transfers": transfers, "other_rows": other}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("booking", choices=("north", "crossing", "harbor"))
    parser.add_argument("--version", type=int, help="Use a recorded revision (default: latest)")
    parser.add_argument("--draft", choices=("A", "B"), help="Select the working statement for this edition")
    parser.add_argument("--file", type=Path, help="Save this CSV as a new revision of the selected draft")
    args = parser.parse_args()
    if args.file is not None and (not args.draft or args.version is not None):
        parser.error("--file requires --draft and cannot be used with a historical revision")
    name = f"reports/{args.booking}.csv"
    client = [sys.executable, str(Path(__file__).with_name("projects.py"))]
    if args.draft:
        name = f"drafts/{args.booking}/{args.draft}.csv"
    if args.file is not None:
        try:
            with args.file.open(encoding="utf-8", newline="") as stream:
                for _ in csv.reader(stream, strict=True):
                    pass
        except (OSError, UnicodeError, csv.Error) as error:
            parser.error(str(error))
        return subprocess.call([*client, "write", name, args.file])
    command = [*client, "read", name]
    if args.version is not None:
        command.extend(["--version", str(args.version)])
    result = subprocess.run(command, stdout=subprocess.PIPE)
    if result.returncode:
        return result.returncode
    try:
        record = json.loads(result.stdout)
        if record["name"] != name or (args.version is not None and record["version"] != args.version):
            raise ValueError("Project storage returned a different statement or revision")
        print(json.dumps(statement(record), ensure_ascii=False))
    except (KeyError, ValueError, csv.Error) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
