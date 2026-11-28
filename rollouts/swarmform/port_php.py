"""Install the port desk's published PHP runtime into a new local directory."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def install(destination):
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        root = Path(staging) / "runtime"
        if Path("/workspace/project-access.json").is_file():
            client = [sys.executable, "/workspace/projects.py"]
            listing = json.loads(subprocess.check_output([*client, "list"]))
            names = [item["name"] for item in listing["artifacts"] if item["name"].startswith("software/")]
            if "software/php" not in names:
                raise FileNotFoundError("software/php")
            subprocess.run([*client, "checkout", str(root), *names], check=True, stdout=subprocess.DEVNULL)
        else:
            shutil.copytree("/var/tmp/exports/project/software", root / "software")
        entry = root / "software/php"
        if not entry.is_file():
            raise FileNotFoundError("software/php")
        for path in (root / "software").rglob("*"):
            if path.is_file():
                with path.open("rb") as stream:
                    signature = stream.read(4)
                if path == entry or signature.startswith(b"#!") or signature == b"\x7fELF":
                    path.chmod(path.stat().st_mode | 0o100)
        root.rename(destination)
    return destination / "software/php"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: port_php.py INSTALL_DIRECTORY")
    try:
        print(install(Path(sys.argv[1])))
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
