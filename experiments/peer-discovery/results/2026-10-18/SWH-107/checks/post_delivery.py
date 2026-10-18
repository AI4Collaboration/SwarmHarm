import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--content', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    directory = args.directory
    attachments = [directory / 'deliverables/SWH-107-case.tar.gz',
                   directory / 'deliverables/SWH-107-source.tar.gz']
    attachments.extend(args.report / name for name in
                       ('README.md', 'summary.json.gz', 'observations.md', 'observations.json.gz',
                        'artifacts.md', 'artifacts.json', 'communication.md',
                        'method.md', 'case-audit.json', 'source.json'))
    for repeat in (3, 2, 1):
        manifest_path = directory / f'publication-chunks-repeat-{repeat}.json'
        manifest = json.loads(manifest_path.read_text())
        attachments.append(manifest_path)
        combined = hashlib.sha256()
        size = 0
        for part in manifest['parts']:
            path = directory / 'deliverables' / part['name']
            raw = path.read_bytes()
            assert len(raw) == part['bytes'] and hashlib.sha256(raw).hexdigest() == part['sha256']
            combined.update(raw)
            size += len(raw)
            attachments.append(path)
        assert size == manifest['original_bytes'] and combined.hexdigest() == manifest['original_sha256']
        evidence = json.loads((directory / f'repeat-{repeat}/evidence-verification.json').read_text())
        assert evidence['verified_subjects'] == 32 and evidence['collection_file_bytes'] == 'verified'
        recording = json.loads((directory / f'repeat-{repeat}/independent-recording-verification.json').read_text())
        assert recording['coverage_complete'] and recording['identifier_bindings'] == 'verified'
    assert (directory / 'execution-complete.json').is_file()
    release = json.loads((directory / 'reservation-release.json').read_text())
    assert release['action'] == 'release'
    assert all(row['issue'] != 'SWH-107' for row in release['leases'])
    audit = json.loads((args.report / 'case-audit.json').read_text())
    assert audit['verified_subjects'] == audit['verified_key_revocations'] == 96
    assert audit['verified_root_volumes'] == audit['verified_packet_captures'] == 96
    assert all(row['prior_cleanup_verified_before_provisioning'] for row in audit['repeats'])
    source = json.loads((args.report / 'source.json').read_text())
    assert source['source_revision'] == '7dcb6136816c72c185c2a1bb1d4fa1b5889e44ec'
    assert source['verified_files'] == 76
    assert len(attachments) == len(set(attachments))
    assert all(path.is_file() and path.stat().st_size > 0 for path in attachments)
    assert args.content.is_file()
    result = {'attachments': len(attachments), 'bytes': sum(path.stat().st_size for path in attachments),
              'verified_reconstructed_publications': 3}
    files = []
    for path in attachments:
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        files.append({'name': path.name, 'bytes': path.stat().st_size, 'sha256': digest})
    result['files'] = files
    (directory / 'delivery-preflight.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({name: value for name, value in result.items() if name != 'files'}), flush=True)
    if args.publish:
        command = ['multica', 'issue', 'comment', 'add', '01a14e6b-c232-72f7-8e4b-b48b2ed54e40',
                   '--content-file', str(args.content), '--output', 'table']
        for path in attachments:
            command.extend(['--attachment', str(path)])
        subprocess.run(command, check=True)
        (directory / 'delivery-receipt.json').write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
