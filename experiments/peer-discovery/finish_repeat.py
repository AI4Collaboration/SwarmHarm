import argparse
import json
import subprocess
import sys
from pathlib import Path

from cloud import save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('graph', type=Path)
    parser.add_argument('--prices', type=Path, required=True)
    parser.add_argument('--recording-passes', type=int, default=1)
    args = parser.parse_args()
    root = Path(__file__).parent
    assert (args.directory / 'cleanup.json').is_file()
    assert (args.directory / 'recording-verification.json').is_file()
    commands = [
        ('verify_evidence.py', [str(args.directory), str(args.graph)]),
        ('grade.py', [str(args.directory)]),
        ('metrics.py', [str(args.directory)]),
        ('resources.py', [str(args.directory)]),
        ('cost_accounting.py', [str(args.directory), '--prices', str(args.prices),
                                '--collection-count', str(args.recording_passes)]),
    ]
    for name, arguments in commands:
        with (args.directory / f'{Path(name).stem}-console.txt').open('w') as stream:
            subprocess.run([sys.executable, str(root / name), *arguments], stdout=stream, stderr=subprocess.STDOUT, check=True)
    save(args.directory, 'analysis-revision.json', {'revision': subprocess.run(
        ['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()})
    scoring = json.loads((args.directory / 'scoring.json').read_text())
    metrics = json.loads((args.directory / 'metrics.json').read_text())
    print(json.dumps({'repeat': scoring['repeat'], 'subjects': scoring['denominator'],
        'exact': sum(agent['exact_completion'] for agent in scoring['agents']),
        'mean_recall': scoring['recall_mean'], 'coverage': scoring['repeat_coverage'],
        'requests': metrics['total_requests'], 'tokens': metrics['total_tokens'],
        'process_start_skew_seconds': metrics['process_start_skew_seconds'], 'cleanup': 'verified'}))


if __name__ == '__main__':
    main()
