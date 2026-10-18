import argparse
import json
import shlex
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
    parser.add_argument('--remote-root', type=Path)
    args = parser.parse_args()
    location = args.directory.parent / 'publication-location.json'
    if location.is_file():
        configured_root = Path(json.loads(location.read_text())['remote_root'])
        assert args.remote_root is None or args.remote_root == configured_root
        args.remote_root = configured_root
    stages = [
        ('cleanup', ['verify_cleanup.py', str(args.directory)]),
        ('compression', ['compress_payloads.py', str(args.directory)]),
        ('recording-verification', ['verify_recording.py', str(args.directory)]),
        ('evidence', ['verify_evidence.py', str(args.directory), str(args.graph)]),
        ('scoring', ['grade.py', str(args.directory)]),
        ('score-verification', ['verify_scores.py', str(args.directory), '--output',
                                str(args.directory / 'independent-scores-verification.json')]),
        ('metrics', ['metrics.py', str(args.directory)]),
        ('resources', ['resources.py', str(args.directory)]),
        ('resource-verification', ['verify_resources.py', str(args.directory), '--output',
                                   str(args.directory / 'independent-resources-verification.json')]),
        ('redaction', ['verify_redaction.py', str(args.directory)]),
    ]
    if not (args.directory / 'recording-receipts.json').exists():
        stages.insert(1, ('recording', ['recording.py', str(args.directory), '--meta-key', str(args.meta_key)]))
    for name, arguments in stages:
        with (args.directory / f'finalize-{name}.log').open('wb') as output:
            subprocess.run([sys.executable, str(ROOT / arguments[0]), *arguments[1:]],
                           stdout=output, stderr=subprocess.STDOUT, check=True)
        print(json.dumps({'stage': name, 'state': 'verified'}), flush=True)
    verification = json.loads((args.directory / 'evidence-verification.json').read_text())
    recording = json.loads((args.directory / 'recording-receipts.json').read_text())
    save(args.directory, 'finalization.json', {'evidence': verification,
        'recorded_requests': recording['requests'], 'recorded_objects': recording['objects'],
        'recording_coverage_complete': recording['coverage_complete'],
        'expected_objects': recording['expected_objects'],
        'stored_expected_objects': recording['stored_expected_objects'],
        'code_revision': subprocess.run(['git', 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()})
    if args.remote_root:
        assert args.directory.parent.resolve() == args.output.parent.parent.resolve()
        remote_directory = args.remote_root / args.directory.name
        remote_output = args.remote_root / 'deliverables' / args.output.name
        command = 'python3 - ' + shlex.join([str(remote_directory), str(remote_output)])
        subprocess.run(['ssh', '-i', str(args.meta_key), '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
                        'ubuntu@63.186.173.73', command], input=(ROOT / 'publish.py').read_bytes(), check=True)
    else:
        subprocess.run([sys.executable, str(ROOT / 'publish.py'), str(args.directory), str(args.output)], check=True)
    subprocess.run([sys.executable, str(ROOT / 'verify_publication.py'), str(args.directory), str(args.output)], check=True)


if __name__ == '__main__':
    main()
