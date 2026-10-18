import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    rows = []
    total_objects = total_requests = total_archives = 0
    for repeat in (3, 2, 1):
        target = args.directory / f'repeat-{repeat}'
        binding = json.loads((target / 'binding.json').read_text())
        evidence = json.loads((target / 'evidence-verification.json').read_text())
        cleanup = json.loads((target / 'independent-cleanup-verification.json').read_text())
        assert evidence['verified_subjects'] == 32 and evidence['collection_file_bytes'] == 'verified'
        assert len(cleanup['original_interface_ids']) == 32 and cleanup['remaining_interfaces'] == []
        exports = json.loads((target / 'export-manifest.json').read_text())
        assert len(exports) == len(binding['hosts']) == 32
        assert {row['instance_id'] for row in exports} == {host['id'] for host in binding['hosts']}
        for row in exports:
            path = target / f'{row["instance_id"]}-raw.tar.gz'
            assert digest(path) == row['archive_sha256']
            assert path.stat().st_size == row['archive_bytes']
        chunks = json.loads((args.directory / f'publication-chunks-repeat-{repeat}.json').read_text())
        publication = json.loads((target / 'publication-verification.json').read_text())
        assert chunks['original_sha256'] == publication['publication_sha256']
        combined = hashlib.sha256()
        for part in chunks['parts']:
            path = args.directory / 'deliverables' / part['name']
            assert path.stat().st_size == part['bytes'] and digest(path) == part['sha256']
            with path.open('rb') as stream:
                while raw := stream.read(2**20):
                    combined.update(raw)
        assert combined.hexdigest() == chunks['original_sha256']
        recording = json.loads((target / 'independent-recording-verification.json').read_text())
        assert recording['stored_expected_objects'] == recording['expected_objects']
        total_objects += recording['expected_objects']
        total_requests += recording['requests']
        total_archives += len(exports)
        rows.append({'repeat': repeat, 'subjects': len(binding['hosts']),
                     'original_archives': len(exports), 'publication': chunks,
                     'archive_command_exits': [row['archive_returncode'] for row in exports],
                     'original_archive_manifest_sha256': digest(target / 'export-manifest.json'),
                     'cleanup_receipt_sha256': digest(target / 'independent-cleanup-verification.json'),
                     'recording_receipt_sha256': digest(target / 'independent-recording-verification.json')})
    result = {'issue': 'SWH-107', 'source_revision': args.revision,
              'subjects': total_archives, 'original_archives': total_archives,
              'requests': total_requests, 'stored_expected_objects': total_objects, 'repeats': rows}
    source = args.directory / 'deliverables/SWH-107-source.tar.gz'
    result['source_archive'] = {'name': source.name, 'bytes': source.stat().st_size, 'sha256': digest(source)}
    args.report.mkdir(parents=True, exist_ok=True)
    (args.report / 'artifacts.json').write_text(json.dumps(result, indent=2))
    lines = ['# Evidence artifacts', '', f'Source revision: `{args.revision}`.', '',
             'Each publication has ordered 8-MiB attachment parts. Concatenate the parts in numeric order '
             'and verify the complete SHA256 against the attached manifest before extracting.', '',
             '| Repeat | Original host archives | Publication bytes | Parts | SHA256 |',
             '| --- | ---: | ---: | ---: | --- |']
    for row in rows:
        item = row['publication']
        lines.append(f"| {row['repeat']} | {row['original_archives']} | {item['original_bytes']} | "
                     f"{len(item['parts'])} | `{item['original_sha256']}` |")
    lines.extend(['', 'Private original host archives retain the complete exported bytes. '
                  'Sanitized publications include sessions, native goals, frozen outputs, stored provider '
                  'payloads, packet captures, command exits, resources, scoring and cleanup receipts.', ''])
    (args.report / 'artifacts.md').write_text('\n'.join(lines))
    print(json.dumps({name: value for name, value in result.items() if name != 'repeats'}))


if __name__ == '__main__':
    main()
