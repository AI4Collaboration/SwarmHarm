"""Read your mailbox or send one message to a chosen address."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

MAIL = Path("/var/tmp/exports/messages")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    send = commands.add_parser("send")
    send.add_argument("recipient")
    send.add_argument("text")
    commands.add_parser("inbox")
    args = parser.parse_args()

    addresses = {p.name: p for p in MAIL.iterdir() if p.is_dir() and p.name != "all" and not p.name.startswith(".")}
    own = next(p for p in addresses.values() if p.stat().st_gid == os.getgid())
    public = MAIL / "all"
    if args.command == "inbox":
        paths = sorted((*own.glob("*.json"), *public.glob("*.json")), key=lambda p: p.name)
        for path in paths:
            print(path.read_text())
        return
    target = public if args.recipient == "all" else addresses.get(args.recipient)
    if target is None:
        parser.error("Unknown recipient")
    mid = f"{time.time_ns()}-{uuid.uuid4().hex}"
    message = {"id": mid, "sender": own.name, "recipient": target.name, "text": args.text}
    # Set-group-ID directories assign new files to the recipient's account group.
    fd, tmp = tempfile.mkstemp(dir=target)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(message, f)
            f.write("\n")
            os.fchmod(f.fileno(), 0o644 if target == public else 0o640)
        os.replace(tmp, target / (mid + ".json"))
    finally:
        Path(tmp).unlink(missing_ok=True)
    closed = target != public and (MAIL / ".closed" / target.name).is_file()
    print(f"{mid} recipient_session=closed" if closed else mid)


if __name__ == "__main__":
    main()
