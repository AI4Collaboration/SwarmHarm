"""Open the selected current products with one version-pinned project checkout."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


@contextmanager
def published_inputs(names, versions):
    names = tuple(names)
    if versions or not names or len(set(names)) != len(names):
        from published_inputs_single import published_inputs as individual
        with individual(names, versions) as products:
            yield products
        return
    with TemporaryDirectory() as tmp:
        root = Path(tmp)/"inputs"
        subprocess.check_output([sys.executable, "/workspace/projects.py", "checkout", root, *names])
        yield root
