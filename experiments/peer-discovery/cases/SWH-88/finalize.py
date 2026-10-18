import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from remote import BASE, REMOTE_BASE, run_analysis, run_remote


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repeat', type=int)
    args = parser.parse_args()
    directory = BASE / f'repeat-{args.repeat}'
    source = BASE / 'operator-code/experiments/peer-discovery'
    remote_directory = f'{REMOTE_BASE}/repeat-{args.repeat}'
    for path in (BASE / f'graphs/graph-{args.repeat}.json', BASE / 'prices.json',
                 BASE / 'graph-verification.json', BASE / 'shared-native-admission.json'):
        shutil.copyfile(path, directory / path.name)
    for script, arguments in (
        ('verify_evidence.py', [remote_directory, f'{REMOTE_BASE}/graphs/graph-{args.repeat}.json']),
        ('grade.py', [remote_directory]),
        ('independent_grade.py', [remote_directory]),
        ('metrics.py', [remote_directory]),
    ):
        result = run_analysis(script, arguments)
        (directory / f'{script}.txt').write_bytes(result.stdout)
        print(json.dumps({'repeat': args.repeat, 'verified': script}), flush=True)
    audit = run_remote(BASE / 'scripts/verify_recording.py', [remote_directory])
    print(audit.stdout.decode(), flush=True)
    result = subprocess.run([sys.executable, str(source / 'resources.py'), str(directory)],
                            check=True, capture_output=True)
    (directory / 'resources.py.txt').write_bytes(result.stdout)
    revision = subprocess.run(['git', '-C', str(BASE / 'repository'), 'rev-parse', 'HEAD'],
                              check=True, capture_output=True, text=True).stdout.strip()
    (directory / 'code-revision.json').write_text(json.dumps({
        'revision': revision, 'shared_harness': '100470a2',
        'shared_native_admission_sha256': hashlib.sha256((BASE / 'SWH-78-admission.tar.gz').read_bytes()).hexdigest(),
        'executed_driver_sha256': hashlib.sha256((source / 'driver.py').read_bytes()).hexdigest(),
        'executed_repeat_sha256': hashlib.sha256((source / 'repeat.py').read_bytes()).hexdigest(),
    }, indent=2))
    publication = run_analysis('publish.py', [remote_directory,
        f'{REMOTE_BASE}/deliverables/SWH-88-repeat-{args.repeat}.tar.gz'])
    (directory / 'publication-receipt.json').write_bytes(publication.stdout)
    score = json.loads((directory / 'scoring.json').read_text())
    metrics = json.loads((directory / 'metrics.json').read_text())
    recording = json.loads((directory / 'recording-receipts.json').read_text())
    print(json.dumps({'repeat': args.repeat, 'subjects': score['denominator'],
        'exact': sum(agent['exact_completion'] for agent in score['agents']),
        'mean_recall': score['recall_mean'], 'requests': metrics['total_requests'],
        'tokens': metrics['total_tokens'], 'recorded_objects': recording['object_count'],
        'cleanup': 'verified'}), flush=True)


if __name__ == '__main__':
    main()
