"""Run a project work command on an explicitly selected source directory and named products."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

from formation_store import artifact_path

MAX_BYTES = 12 * 1024 * 1024 - 4096


def included(name):
    parts = Path(name).parts
    return '.git' not in parts and '__pycache__' not in parts and not name.endswith(('.pyc', '.pyo'))


def package_files(root, folder):
    directory = artifact_path(root, folder)
    if not directory.is_dir():
        raise ValueError(f"Missing selected project directory: {folder}/")
    for parent, directories, files in os.walk(directory):
        directories[:] = sorted(name for name in directories if name not in ('.git', '__pycache__'))
        for name in directories:
            artifact_path(root, (Path(parent) / name).relative_to(root).as_posix())
        for name in sorted(files):
            if not name.endswith(('.pyc', '.pyo')):
                yield (Path(parent) / name).relative_to(root).as_posix()


def snapshot(root, name):
    path = artifact_path(root, name)
    with open(path, 'rb', opener=lambda p, f: os.open(p, f | os.O_NOFOLLOW | os.O_NONBLOCK)) as src:
        if not stat.S_ISREG(os.fstat(src.fileno()).st_mode):
            raise ValueError(f"Expected a regular project file: {name}")
        data = src.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"Project file too large: {name}")
    return data


def work(targets, command, root):
    if not command or len(targets) != len(set(targets)):
        raise ValueError("Select distinct directories or files and supply a command after --")
    folders = [name[:-1] for name in targets if name.endswith('/')]
    leaves = [name for name in targets if not name.endswith('/')]
    paths = [artifact_path(root, name) for name in folders + leaves]
    if len(paths) != len(set(paths)) or any(a in b.parents for a in paths for b in paths):
        raise ValueError("Overlapping work selections")
    config = json.loads(Path('/workspace/project-access.json').read_text())
    socket = config['interface'] == 'socket'
    if socket:
        from socket_worktree import request
        def access(operation, **kwargs):
            return request(config, operation, **kwargs)
    else:
        from formation_store import mapped_request
        def access(operation, **kwargs):
            return mapped_request(dict(operation=operation, **kwargs))

    catalog = {r['name']: r for r in access('list')['artifacts']}
    selected = set(leaves)
    for folder in folders:
        selected.update(n for n in catalog if n.startswith(folder + '/') and included(n))
        artifact_path(root, folder).mkdir(parents=True)
    for name in sorted(selected):
        path = artifact_path(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if name not in catalog:
            continue
        item = catalog[name]
        if socket:
            receipt = access('materialize', name=name, version=item['version'], worktree=root.name)
        else:
            receipt = access('read', name=name, version=item['version'])
        data = base64.b64decode(receipt['data'], validate=True)
        if (receipt['version'] != item['version'] or len(data) != item['bytes']
                or hashlib.sha256(data).hexdigest() != item['sha256']):
            raise ValueError(f"Project revision differs from listing: {name}")
        path.write_bytes(data)

    run = subprocess.run(command, cwd=root)
    if run.returncode:
        return run.returncode if run.returncode > 0 else 128 - run.returncode
    for folder in folders:
        selected.update(package_files(root, folder))
    with tempfile.TemporaryDirectory(prefix='project-save-') as stage:
        changes = []
        for name in sorted(selected):
            path = artifact_path(root, name)
            if name not in catalog and not path.exists():
                continue
            data = snapshot(root, name)
            item = catalog.get(name, {})
            if hashlib.sha256(data).hexdigest() != item.get('sha256'):
                frozen = Path(stage) / str(len(changes))
                frozen.write_bytes(data)
                changes.append((name, frozen, item.get('version', 0)))
        for name, frozen, version in changes:
            if socket:
                receipt = access('write', name=name, data=base64.b64encode(frozen.read_bytes()).decode(),
                                 base_version=version, worktree=root.name)
                print(json.dumps(receipt), flush=True)
            else:
                subprocess.run([sys.executable, '/workspace/projects.py', 'write', name, str(frozen),
                                '--if-version', str(version)], check=True)
    return 0


def dispatch():
    args = sys.argv[1:]
    if args in (['--help'], ['-h']):
        print("work DIR/ [FILE ...] -- COMMAND opens a source package and optional named products. "
              "A successful command saves changed files and new package members; Python bytecode and .git are excluded.")
    if args[:1] != ['work'] or '--' not in args:
        return
    cut = args.index('--')
    targets = args[1:cut]
    if not any(t.endswith('/') for t in targets):
        return
    root = Path(tempfile.mkdtemp(prefix='project-work-'))
    code = 1
    try:
        code = work(targets, args[cut + 1:], root)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
    finally:
        if code:
            print(f"Local project files retained in {root}", file=sys.stderr)
        else:
            shutil.rmtree(root)
    raise SystemExit(code)
