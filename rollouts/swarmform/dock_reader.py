"""Read the unloading desk's JSON change feed from its published North ledger."""
import argparse
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
from published_inputs import published_inputs

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ledger-version', type=int)
parser.add_argument('--terminal', type=Path, help='Installed replacement SQL executable or Python command file')
args = parser.parse_args()
command = [sys.executable, str(Path(__file__).with_name('dock_reference.py'))]
if args.terminal is not None:
    terminal = args.terminal.resolve(strict=True)
    command = [str(terminal)]
    if not os.access(terminal, os.X_OK):
        with terminal.open('rb') as source:
            shebang = source.readline(256).strip()
        if terminal.suffix != '.py' and shebang not in (b'#!/usr/bin/env python3', b'#!/usr/bin/python3'):
            parser.error('The installed terminal must be executable or a Python command file')
        command = [sys.executable, str(terminal)]
ledger = 'ledgers/north.csv'
query = 'exports/dock-changes.sql'
versions = {} if args.ledger_version is None else {ledger: args.ledger_version}
with published_inputs((query, ledger), versions) as root:
    sql = (root / query).read_bytes()
    if sha256(sql).hexdigest() != 'bdae97771251e8354bce6edb0609d866e1026090155af08b75101a0ce9b8eea4':
        raise ValueError('Published query differs from the issued unloading desk query')
    subprocess.run([*command, '-json', '-batch', ':memory:', '-c', sql.decode()], cwd=root, check=True)
