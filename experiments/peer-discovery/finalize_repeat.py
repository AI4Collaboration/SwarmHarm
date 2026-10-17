import argparse
import json
import subprocess
import sys
from pathlib import Path

from cloud import ROOT, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('graph', type=Path)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stages = [
        ('compression', ['compress_payloads.py', str(args.directory)]),
        ('recording', ['recording.py', str(args.directory), '--meta-key', str(args.meta_key)]),
        ('evidence', ['verify_evidence.py', str(args.directory), str(args.graph)]),
        ('scoring', ['grade.py', str(args.directory)]),
        ('metrics', ['metrics.py', str(args.directory)]),
        ('resources', ['resources.py', str(args.directory)]),
    ]
    for name, arguments in stages:
        with (args.directory / f'finalize-{name}.log').open('wb') as output:
            subprocess.run([sys.executable, str(ROOT / arguments[0]), *arguments[1:]],
                           stdout=output, stderr=subprocess.STDOUT, check=True)
        print(json.dumps({'stage': name, 'state': 'verified'}), flush=True)
    verification = json.loads((args.directory / 'evidence-verification.json').read_text())
    recording = json.loads((args.directory / 'recording-receipts.json').read_text())
    save(args.directory, 'finalization.json', {'evidence': verification,
        'recorded_requests': recording['requests'], 'recorded_objects': recording['objects'],
        'code_revision': subprocess.run(['git', 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()})
    subprocess.run([sys.executable, str(ROOT / 'publish.py'), str(args.directory), str(args.output)], check=True)


if __name__ == '__main__':
    main()
