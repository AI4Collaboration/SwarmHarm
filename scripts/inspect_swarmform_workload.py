#!/usr/bin/env python3
"""Export the three private fulfillment intakes and run the independent input checks."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments/swarmharm-v1'))
from swarmform import fulfillment


def export_workload(target, dataset_key, *, staged=False):
    """The staged export separates startup bytes from operator-held future deliveries."""
    audit = fulfillment.check_workload(dataset_key)
    private, _ = fulfillment.source_material(dataset_key)
    target.mkdir(parents=True, exist_ok=False)
    for site, batches in private.items():
        station = target / 'initial' / site if staged else target / site
        startup = station / 'workspace' if staged else station
        startup.mkdir(parents=True)
        (station / 'assignment.txt').write_text(fulfillment.assignment(site) + '\n')
        (startup / 'work-order.md').write_text(fulfillment.WORK_ORDER)
        for batch, files in batches.items():
            folder = startup
            if staged and batch != fulfillment.BATCHES[0]:
                folder = target / 'arrivals' / batch / site / 'workspace'
            for relative, content in files.items():
                path = folder / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
    if staged:
        schedule = dict(zip(fulfillment.BATCHES, fulfillment.ARRIVAL_SECONDS, strict=True))
        (target / 'arrival-offsets-seconds.json').write_text(json.dumps(schedule, indent=2) + '\n')
    (target / 'input-audit.json').write_text(json.dumps(audit, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-key', required=True, help='Selects the synthetic business data.')
    parser.add_argument('--output', type=Path, required=True, help='New directory outside the repository.')
    parser.add_argument('--staged', action='store_true',
                        help='Separate the initial workstations and later private source deliveries.')
    args = parser.parse_args()
    target = args.output.resolve()
    if target.is_relative_to(ROOT) or target.exists():
        parser.error('Use a new external output directory.')
    export_workload(target, args.dataset_key, staged=args.staged)
    print(f'Checked {len(fulfillment.SITES)} sites and {len(fulfillment.BATCHES)} batches. Input preview: {target}')



if __name__ == '__main__':
    main()
