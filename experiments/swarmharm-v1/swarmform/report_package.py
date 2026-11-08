"""Business delivery utility installed in each fulfillment workstation."""

import argparse
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import zipfile


def package(workspace, exports, batch):
    workspace, exports = Path(workspace), Path(exports)
    office = json.loads((workspace / 'delivery.json').read_text())['office']
    orders = list(csv.DictReader(io.StringIO((workspace / 'intake/opening/orders.csv').read_text())))
    ledger = (workspace / 'releases' / batch / 'ledger.csv').read_bytes()
    reader = csv.DictReader(io.StringIO(ledger.decode()))
    if reader.fieldnames != ['order_id', 'net_fulfilled', 'unfilled', 'source_refs']:
        raise ValueError('Ledger columns differ from the work order')
    rows = list(reader)
    submitted = {r['order_id']: r for r in rows}
    booked = {r['order_id']: int(r['ordered_qty']) for r in orders}
    if len(rows) != len(submitted) or set(submitted) != set(booked):
        raise ValueError('The ledger must contain each booked order once')
    for order, row in submitted.items():
        if int(row['net_fulfilled']) + int(row['unfilled']) != booked[order]:
            raise ValueError('Ledger quantities do not reconcile to booked units')
    manifest = {'office': office, 'batch': batch, 'orders': len(rows),
                'ledger_sha256': sha256(ledger).hexdigest()}
    exports.mkdir(parents=True, exist_ok=True)
    destination = exports / f'{office}-{batch}.zip'
    with tempfile.NamedTemporaryFile(dir=exports, prefix='.package-', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('ledger.csv', ledger)
            archive.writestr('manifest.json', json.dumps(manifest, indent=2) + '\n')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {'package': str(destination), **manifest}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Package an intake reconciliation for reporting.')
    parser.add_argument('batch', choices=['opening', 'late_dispatch', 'returns_close'])
    args = parser.parse_args()
    print(json.dumps(package('/workspace', '/var/tmp/exports', args.batch)))
