import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--issue', required=True)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    case = root / '.scratch' / args.issue

    def run(name, *arguments):
        subprocess.run([sys.executable, str(root / name), *map(str, arguments)], check=True)

    for repeat in range(1, 4):
        directory = case / f'repeat-{repeat}'
        assert not (directory / 'cloud.json').exists()
        provider = case / f'provider-admission-{repeat}'
        if provider.exists():
            admission = json.loads((provider / 'provider-admission.json').read_text())
            assert admission['issue'] == args.issue and admission['completed_gateway_requests'] == 3
        else:
            run('provider_probe.py', provider, '--meta-key', args.meta_key, '--issue', args.issue)
        run('repeat.py', directory, case / f'graph-{repeat}.json', '--meta-key', args.meta_key,
            '--issue', args.issue, '--admission', case / 'case-admission.json',
            '--admission-state-dir', args.state_dir)
        run('verify_evidence.py', directory, case / f'graph-{repeat}.json')
        run('infrastructure.py', directory, '--cleanup')
        run('grade.py', directory)
        run('metrics.py', directory)
        run('resources.py', directory)
        print(json.dumps({'issue': args.issue, 'repeat': repeat, 'phase': 'verified'}), flush=True)


if __name__ == '__main__':
    main()
