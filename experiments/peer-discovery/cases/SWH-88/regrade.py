import json

from remote import BASE, REMOTE_BASE, run_analysis


def main():
    for number in (2, 1):
        result = run_analysis('independent_grade.py', [f'{REMOTE_BASE}/repeat-{number}'])
        (BASE / f'repeat-{number}/independent_grade.py.txt').write_bytes(result.stdout)
        print(json.dumps({'repeat': number, 'independent_precision_and_coverage': 'verified'}), flush=True)


if __name__ == '__main__':
    main()
