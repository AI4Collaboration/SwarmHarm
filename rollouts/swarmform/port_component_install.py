"""Open a pinned, editable installation of the available port components."""
import json
from pathlib import Path
import subprocess
import sys


def open_installation(destination):
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Choose a new installation directory: {destination}")
    client = [sys.executable, Path(__file__).with_name("projects.py")]
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Checkout directly at the final location so ordinary update/commit retain its pins.
    result = subprocess.run([*client, "checkout", destination, "software/"], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Component checkout failed")
    pins = {}
    for line in result.stdout.splitlines():
        row = json.loads(line)
        if "saved_to" in row:
            pins[row["name"]] = {"version": row["version"], "sha256": row["sha256"]}
            target = destination / row["name"]
            with target.open("rb") as stream:
                signature = stream.read(4)
            if row["name"] == "software/php" or signature.startswith(b"#!") or signature == b"\x7fELF":
                target.chmod(target.stat().st_mode | 0o100)
    if not pins:
        raise ValueError("No port software components were retrieved")
    if "software/php" in pins:
        # Preserve the existing complete-install stdout contract for shell substitution.
        return destination / "software/php"
    return json.dumps({"installation": str(destination), "components": pins,
                       "runtime_entry": None}, sort_keys=True)
