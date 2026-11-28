"""Qualify and deploy one meter package to project storage."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4


def deploy(checkout, project_client, workdir):
    project = Path(__file__).resolve().parents[2]
    executable = checkout / "cppcheck"
    modules = checkout / "software"
    if not executable.is_file():
        raise ValueError(f"Missing package executable: {executable}")
    files = [executable, *sorted(modules.rglob("*"))]
    with TemporaryDirectory(dir=workdir) as directory:
        stage = Path(directory)
        release = Path("meter-releases") / uuid4().hex
        selected = []
        for item in files:
            name = item.relative_to(checkout)
            if "__pycache__" in name.parts or name.suffix == ".pyc":
                continue
            if item.is_symlink() or not (item.is_file() or item.is_dir()):
                raise ValueError(f"Package requires ordinary files: {name}")
            if item.is_file():
                path = release / name
                target = stage / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item, target)
                selected.append(path.as_posix())
        analyzer = stage / release / "cppcheck"
        analyzer.chmod(0o755)
        subprocess.run([sys.executable, project / "qa/meter/check_meter.py", analyzer], check=True)
        launcher = stage / "cppcheck"
        launcher.write_text('#!/bin/sh\n'
                            'program="$(dirname "$0")/' + release.as_posix() + '/cppcheck"\n'
                            '[ -x "$program" ] || chmod u+x "$program" || exit 1\n'
                            'exec "$program" "$@"\n')
        # A versioned write commits one object. The active launcher changes last.
        subprocess.run([sys.executable, project_client, "save", stage, *selected, "cppcheck"],
                       check=True)
        print(f"Deployed {release} to project storage.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    try:
        deploy(parser.parse_args().package, Path("/workspace/projects.py"), Path("/workspace"))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
