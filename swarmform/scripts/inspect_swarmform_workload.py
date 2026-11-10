#!/usr/bin/env python3
"""Export exact startup prompts, tools and staged business files for a domain."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'shared'), str(ROOT / 'swarmform')]
from swarmform.domain_inputs import DOMAINS, descriptor
from swarmform.input_catalog import build


def write_preview(folder, dataset_key, staged, domain='Knowledge Work'):
    visible, _, manifest = build(dataset_key, domain)
    private = visible['private_arrivals']
    module, _, _ = descriptor(domain)
    for site, batches in private.items():
        station = folder / 'initial' / site if staged else folder / site
        startup = station / 'workspace' if staged else station
        startup.mkdir(parents=True)
        (station / 'assignment.txt').write_text('\n\n'.join(visible['prompts'][site]))
        for absolute, text in visible['startup'][site].items():
            path = startup / absolute.removeprefix('/workspace/')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for batch, files in batches.items():
            destination = startup
            if staged and batch != module.BATCHES[0]:
                destination = folder / 'arrivals' / batch / site / 'workspace'
            for relative, content in files.items():
                path = destination / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
    if staged:
        (folder / 'arrival-offsets-seconds.json').write_text(json.dumps(manifest['effective_settings']['arrival_offsets'], indent=2) + '\n')
    (folder / 'input-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (folder / 'tool-schema.json').write_text(json.dumps(visible['tools'], indent=2) + '\n')


def export_workload(target, dataset_key, *, staged=False, domain='Knowledge Work'):
    """Build outside the destination, then publish the complete preview without overwriting one."""
    target = Path(target).resolve()
    if target.is_relative_to(ROOT):
        raise ValueError('Use an output directory outside the repository.')
    if target.exists():
        raise FileExistsError(f'Output directory already exists: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        preview = Path(tmp) / 'preview'
        write_preview(preview, dataset_key, staged, domain)
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
    parser.add_argument('--domain', choices=DOMAINS, default='Knowledge Work')
    parser.add_argument('--output', type=Path, required=True, help='New directory outside the repository.')
    parser.add_argument('--staged', action='store_true',
                        help='Separate the initial workstations and later private source deliveries.')
    args = parser.parse_args()
    try:
        export_workload(args.output, args.dataset_key, staged=args.staged, domain=args.domain)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f'Exported {args.domain}: three private workstations and three source batches. Input preview: {args.output.resolve()}')


if __name__ == '__main__':
    main()
