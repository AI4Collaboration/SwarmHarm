#!/usr/bin/env python3
"""Export the three private fulfillment intakes and run the independent input checks."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments/swarmharm-v1'))
from swarmform import fulfillment


def write_preview(folder, dataset_key, staged):
    audit = fulfillment.check_workload(dataset_key)
    private, _ = fulfillment.source_material(dataset_key)
    for site, batches in private.items():
        station = folder / 'initial' / site if staged else folder / site
        startup = station / 'workspace' if staged else station
        startup.mkdir(parents=True)
        (station / 'assignment.txt').write_text(fulfillment.assignment(site) + '\n')
        (startup / 'work-order.md').write_text(fulfillment.WORK_ORDER)
        for batch, files in batches.items():
            destination = startup
            if staged and batch != fulfillment.BATCHES[0]:
                destination = folder / 'arrivals' / batch / site / 'workspace'
            for relative, content in files.items():
                path = destination / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
    if staged:
        (folder / 'arrival-offsets-seconds.json').write_text(json.dumps(fulfillment.ARRIVAL_OFFSETS, indent=2) + '\n')
    (folder / 'input-audit.json').write_text(json.dumps(audit, indent=2) + '\n')


def export_workload(target, dataset_key, *, staged=False):
    """Build outside the destination, then publish the complete preview without overwriting one."""
    target = Path(target).resolve()
    if target.is_relative_to(ROOT):
        raise ValueError('Use an output directory outside the repository.')
    if target.exists():
        raise FileExistsError(f'Output directory already exists: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        preview = Path(tmp) / 'preview'
        write_preview(preview, dataset_key, staged)
        # Reserve the name only after export succeeds. Concurrent exporters cannot
        # take over an existing destination, including an empty directory.
        target.mkdir()
        try:
            preview.replace(target)
        except OSError:
            target.rmdir()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-key', required=True, help='Selects the synthetic business data.')
    parser.add_argument('--output', type=Path, required=True, help='New directory outside the repository.')
    parser.add_argument('--staged', action='store_true',
                        help='Separate the initial workstations and later private source deliveries.')
    args = parser.parse_args()
    try:
        export_workload(args.output, args.dataset_key, staged=args.staged)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f'Checked {len(fulfillment.SITES)} sites and {len(fulfillment.BATCHES)} batches. Input preview: {args.output.resolve()}')


if __name__ == '__main__':
    main()
