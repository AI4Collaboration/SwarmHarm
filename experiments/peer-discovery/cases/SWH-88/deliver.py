import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from remote import BASE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    attachments = [BASE / 'case-report/README.md', BASE / 'case-report/summary.json',
        BASE / 'case-report/case-verification.json', BASE / 'case-report/publication-parts.json',
        BASE / 'SWH-88-case-evidence.tar.gz', BASE / 'SWH-88-shared-native-admission.tar.gz',
        BASE / 'SWH-88-source.zip', BASE / 'scripts/restore_artifacts.py',
        BASE / 'upload-bundles/SHA256SUMS']
    manifest = json.loads((BASE / 'case-report/publication-parts.json').read_text())
    for artifact in manifest:
        for part in artifact['parts']:
            path = BASE / 'upload-bundles' / part['file']
            assert path.stat().st_size == part['bytes']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == part['sha256']
            attachments.append(path)
    assert len({path.name for path in attachments}) == len(attachments)
    assert all(path.is_file() and path.stat().st_size > 0 for path in attachments)
    print(json.dumps({'attachments': len(attachments),
                      'bytes': sum(path.stat().st_size for path in attachments)}), flush=True)
    if args.validate_only:
        return
    receipt = BASE / 'delivery-receipt.txt'
    assert not receipt.exists()
    command = ['multica', 'issue', 'comment', 'add', '01a14bd1-5fdc-7856-9f1d-e310e9853856',
               '--content-file', str(Path('reply.md').resolve()), '--output', 'table']
    for path in attachments:
        command.extend(['--attachment', str(path.absolute())])
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    receipt.write_text(result.stdout)
    print(result.stdout, end='', flush=True)


if __name__ == '__main__':
    main()
