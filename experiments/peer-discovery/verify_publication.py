import argparse
import json
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    secrets = [json.loads(path.read_text())['key'] for path in args.directory.rglob('private-key-*.json')]
    for name in ('operator-key', 'peer-key'):
        for line in (args.directory / name).read_text().splitlines():
            if not line.startswith('-----') and len(line) >= 32:
                secrets.append(line)
    patterns = set()
    for secret in secrets:
        patterns.add(secret.encode())
        patterns.add(json.dumps(secret)[1:-1].encode())
        patterns.add(secret[-24:].encode())
    checked = 0
    findings = []
    with tarfile.open(args.archive) as archive:
        for member in archive:
            if member.isfile():
                data = archive.extractfile(member).read()
                if any(pattern in data for pattern in patterns):
                    findings.append(member.name)
                checked += 1
    assert not findings, findings
    report = {'artifact': args.archive.name, 'files_checked': checked,
              'credential_fragment_patterns': len(patterns), 'credential_pattern_matches': 0}
    (args.directory / 'publication-independent-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
