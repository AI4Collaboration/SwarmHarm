#!/usr/bin/env python3
"""Export the three private fulfillment intakes and run the independent input checks."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments/swarmharm-v1'))
from swarmform import fulfillment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-key', required=True, help='Selects the synthetic business data.')
    parser.add_argument('--output', type=Path, required=True, help='New directory outside the repository.')
    args = parser.parse_args()
    target = args.output.resolve()
    if target.is_relative_to(ROOT) or target.exists():
        parser.error('Use a new external output directory.')
    audit = fulfillment.check_workload(args.dataset_key)
    private, _ = fulfillment.source_material(args.dataset_key)
    target.mkdir(parents=True)
    for site, batches in private.items():
        folder = target / site
        folder.mkdir()
        (folder / 'assignment.txt').write_text(fulfillment.assignment(site) + '\n')
        (folder / 'work-order.md').write_text(fulfillment.WORK_ORDER)
        for files in batches.values():
            for relative, content in files.items():
                path = folder / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
    # This file is operator-only. Batches are exported for inspection; live arrival is a runtime concern.
    (target / 'input-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(f'Checked all four sites and three batches. Inspect private intakes in {target}.')


if __name__ == '__main__':
    main()
