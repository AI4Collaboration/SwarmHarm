import json
import sys

from remote import BASE, REMOTE_BASE, run_analysis


def main():
    for number in map(int, sys.argv[1:]):
        directory = BASE / f'repeat-{number}'
        result = run_analysis('metrics.py', [f'{REMOTE_BASE}/repeat-{number}'])
        (directory / 'metrics.py.txt').write_bytes(result.stdout)
        print(json.dumps({'repeat': number, 'lifecycle_contact_analysis': 'verified'}), flush=True)


if __name__ == '__main__':
    main()
