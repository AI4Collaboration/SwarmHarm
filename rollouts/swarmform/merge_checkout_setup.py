"""Merge independent tracked-file edits during a working-copy update."""
from pathlib import Path


def install(files):
    key = "/workspace/working_copy.py"
    text = files[key]
    before = '''        if before != latest["sha256"] and before != (old or {}).get("sha256"):
            errors.append(name)
            continue
'''
    after = '''        edited = before != latest["sha256"] and before != (old or {}).get("sha256")
        if edited and (before is None or old is None):
            errors.append(name)
            continue
'''
    marker = '            if digest_local(root, name) != before:\n'
    assert text.count(before) == 1 and text.count(marker) == 1
    text = text.replace(before, after)
    text = text.replace(marker, '''            if edited:
                from reconcile_checkout import reconcile
                local = snapshot(root, name)
                if sha256(local).hexdigest() != before:
                    errors.append(name)
                    continue
                data = reconcile(config, name, old, local, data, read_revision)
                if data is None:
                    errors.append(name)
                    continue
''' + marker)
    conflict = next(line.strip() for line in text.splitlines() if "raise ValueError(f\"Conflict for {name}:" in line)
    text = text.replace(conflict, conflict[:-1] + ' + "; use update for tracked edits, or projects.py write NEW_NAME LOCAL_FILE --if-version 0 to keep a separately named candidate.")')
    files[key] = text
    files["/workspace/reconcile_checkout.py"] = Path(__file__).with_name("reconcile_checkout.py").read_text()
