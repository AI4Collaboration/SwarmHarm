"""Operator-only snapshot of product state without exposing file bodies."""
from pathlib import Path
import argparse
import hashlib
import json
import sqlite3


def safe(value):
    if isinstance(value, bytes):
        return {"blob_sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
    return value


def snapshot(database: Path, workspace: Path) -> dict:
    con = sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    tables = {}
    for table, in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        tables[table] = [{key: safe(value) for key, value in dict(row).items()} for row in con.execute('SELECT * FROM "' + table.replace('"', '""') + '"')]
    con.close()
    files = {
        str(path.relative_to(workspace)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(workspace.rglob("*")) if path.is_file() and not path.is_symlink()
    }
    return {"tables": tables, "files": files}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("/var/lib/product-world/world.db"))
    parser.add_argument("--workspace", type=Path, default=Path("/work/workspace"))
    args = parser.parse_args()
    print(json.dumps(snapshot(args.database, args.workspace), ensure_ascii=False))
