"""Materialize a pinned project checkout into a new or caller-owned empty directory."""
import base64
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path

import formation_store as store


def owned(stat):
    return (stat.st_dev, stat.st_ino)


def checkout(directory, names, listing):
    pins = []
    index = {entry["name"]: entry for entry in listing}
    selected = names or list(index)
    if len(selected) != len(set(selected)):
        raise ValueError("Duplicate artifact name")
    root = Path(directory)
    for name in selected:
        store.artifact_path(root, name)
        if name not in index:
            raise ValueError(f"Unknown artifact: {name}")
    made_root = False
    try:
        root.mkdir()
        made_root = True
    except FileExistsError:
        pass
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as handles:
        root_fd = os.open(root, directory_flags)
        handles.callback(os.close, root_fd)
        fcntl.flock(root_fd, fcntl.LOCK_EX)
        if owned(root.lstat()) != owned(os.fstat(root_fd)):
            raise ValueError(f"Checkout directory changed: {root}")
        if not names and os.listdir(root_fd):
            raise ValueError(f"Checkout directory is not empty: {root}")
        for name in selected:
            target = store.artifact_path(root, name)
            if target.exists():
                raise ValueError(f"Checkout target already exists: {target}")
        directories = {(): root_fd}
        created = []
        try:
            for name in selected:
                item = index[name]
                receipt = store.mapped_request({"operation":"read","name":name,"version":item["version"]})
                data = base64.b64decode(receipt.pop("data"), validate=True)
                if (receipt["version"] != item["version"] or receipt["sha256"] != item["sha256"]
                        or len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]):
                    raise ValueError(f"Downloaded bytes differ from listing: {name}")
                parts = tuple(name.split("/"))
                parent = root_fd
                for i, part in enumerate(parts[:-1],1):
                    prefix = parts[:i]
                    if prefix not in directories:
                        try:
                            os.mkdir(part,dir_fd=parent)
                        except FileExistsError:
                            new_directory = False
                        else:
                            new_directory = True
                        child = os.open(part,directory_flags,dir_fd=parent)
                        handles.callback(os.close,child)
                        directories[prefix] = child
                        if new_directory:
                            created.append((parent,part,os.fstat(child),True))
                    parent = directories[prefix]
                leaf = parts[-1]
                fd = os.open(leaf,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o666,dir_fd=parent)
                with os.fdopen(fd,"wb",buffering=0) as out:
                    try:
                        view = memoryview(data)
                        while view:
                            count = out.write(view)
                            if not count:
                                raise OSError("Short checkout write")
                            view = view[count:]
                    finally:
                        created.append((parent,leaf,os.fstat(out.fileno()),False))
                destination = store.artifact_path(root, name)
                if (owned(root.lstat()) != owned(os.fstat(root_fd))
                        or owned(destination.lstat()) != owned(created[-1][2])):
                    raise ValueError(f"Checkout destination changed: {destination}")
                receipt["saved_to"] = str(destination)
                print(json.dumps(receipt,ensure_ascii=False),flush=True)
                pins.append((name, receipt["version"], receipt["sha256"]))
        except BaseException:
            for parent, leaf, original, is_dir in reversed(created):
                try:
                    current = os.stat(leaf,dir_fd=parent,follow_symlinks=False)
                    if owned(current) != owned(original):
                        continue
                    if is_dir:
                        os.rmdir(leaf,dir_fd=parent)
                    elif (current.st_size,current.st_mtime_ns)==(original.st_size,original.st_mtime_ns):
                        os.unlink(leaf,dir_fd=parent)
                except OSError:
                    # Leave any replaced or non-empty entries untouched during rollback.
                    pass
            if made_root:
                try:
                    if owned(root.lstat())==owned(os.fstat(root_fd)):
                        root.rmdir()
                except OSError:
                    pass
            raise
    return pins
