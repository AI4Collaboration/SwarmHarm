import argparse
import gzip
import hashlib
import json
import tarfile
from pathlib import Path

from cloud import save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('publication', type=Path)
    parser.add_argument('--capture-manifest', type=Path)
    args = parser.parse_args()
    if args.capture_manifest:
        captures = {row['instance_id'] + '/' + row['member']: row['member_sha256']
                    for row in json.loads(args.capture_manifest.read_text())['receipts']}
    else:
        binding = json.loads((args.directory / 'binding.json').read_text())
        captures = {host['id'] + '/var/lib/peer-operator/traffic.pcap':
                    hashlib.sha256((args.directory / host['id'] / 'var/lib/peer-operator/traffic.pcap').read_bytes()).hexdigest()
                    for host in binding['hosts']}
    counts = {'json_files': 0, 'jsonl_records': 0, 'stored_payloads': 0, 'captures': 0}
    seen = set()
    with tarfile.open(args.publication, 'r|gz') as archive:
        for member in archive:
            if not member.isfile():
                continue
            name = Path(member.name)
            raw = archive.extractfile(member).read()
            if 'stored-payloads' in name.parts and name.name.endswith('.json.gz'):
                assert json.loads(gzip.decompress(raw))
                counts['stored_payloads'] += 1
            elif name.suffix == '.json' and name.name not in ('frozen-output.json', 'discovered_peers.json'):
                json.loads(raw)
                counts['json_files'] += 1
            elif name.suffix == '.jsonl':
                for line in raw.splitlines():
                    json.loads(line)
                    counts['jsonl_records'] += 1
            if member.name in captures:
                assert hashlib.sha256(raw).hexdigest() == captures[member.name], member.name
                seen.add(member.name)
                counts['captures'] += 1
    assert seen == set(captures)
    result = {**counts, 'publication_sha256': hashlib.sha256(args.publication.read_bytes()).hexdigest(),
              'capture_bytes_match_originals': True}
    save(args.directory, 'publication-verification.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
