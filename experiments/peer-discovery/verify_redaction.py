import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

from cloud import save
from publish import clean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    key_paths = sorted(args.directory.glob('private-key-*.json'))
    secrets = [json.loads(path.read_text())['key'] for path in key_paths]
    credentials = re.compile(b'|'.join(re.escape(secret.encode()) for secret in sorted(set(secrets), key=len, reverse=True)))
    binding = json.loads((args.directory / 'binding.json').read_text())
    host = args.directory / binding['hosts'][0]['id']
    paths = key_paths + [args.directory / 'peer-key',
                        host / 'var/lib/peer-operator/traffic.pcap',
                        next(args.directory.glob('i-*/home/agent/.codex/sessions/**/*.jsonl')),
                        next((args.directory / 'stored-payloads').rglob('request_body.json.gz'))]
    receipts = []
    for path in paths:
        raw = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
        expected = raw
        for secret in secrets:
            expected = expected.replace(secret.encode(), b'[redacted-credential]')
        expected = re.sub(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----(?s:.*?)-----END [A-Z ]*PRIVATE KEY-----',
                          b'[redacted-private-key]', expected)
        expected = re.sub(rb'ah-[A-Za-z0-9_-]{20,}', b'[redacted-credential]', expected)
        observed = clean(raw, credentials)
        assert expected == observed and credentials.search(observed) is None
        receipts.append({'path': str(path.relative_to(args.directory)), 'source_bytes': len(raw),
                         'sanitized_sha256': hashlib.sha256(observed).hexdigest()})
    result = {'credential_count': len(secrets), 'actual_files_compared': len(paths),
              'matching_bytes': sum(row['source_bytes'] for row in receipts), 'receipts': receipts}
    save(args.directory, 'redaction-verification.json', result)
    print(json.dumps({name: value for name, value in result.items() if name != 'receipts'}))


if __name__ == '__main__':
    main()
