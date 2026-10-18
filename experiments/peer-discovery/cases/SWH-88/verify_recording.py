import hashlib
import json
from pathlib import Path
import sys


def main():
    directory = Path(sys.argv[1])
    recording = json.loads((directory / 'recording-receipts.json').read_text())
    binding = json.loads((directory / 'binding.json').read_text())
    observed = set()
    for index, host in enumerate(binding['hosts']):
        exported = json.loads((directory / f'gateway-{index}.json').read_text())
        for edge in exported['requests']['edges']:
            request = edge['node']
            assert request['modelID'] == 'gpt-6-luna' and request['reasoningEffort'] == 'xhigh'
            assert request['id'] not in observed
            observed.add(request['id'])
    assert len(observed) == recording['request_count']
    assert observed == {row['request_id'] for row in recording['requests']}
    assert len(recording['objects']) == recording['object_count']
    assert len({row['object_key'] for row in recording['objects']}) == recording['object_count']
    for item in recording['objects']:
        raw = (directory / 'stored-payloads' / item['object_key']).read_bytes()
        assert len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256']
        if item['entity_status'] == 'completed' or item['field'] == 'requestBody':
            assert json.loads(raw)
    for entity in recording['entity_coverage']:
        assert 'requestBody' in entity['stored_fields']
        if entity['entity_status'] == 'completed':
            assert set(entity['stored_fields']) == {'requestBody', 'responseBody', 'responseChunks'}
    report = {'requests': len(observed), 'objects': recording['object_count'], 'bytes': recording['bytes'],
              'sha256_verification': 'verified', 'request_coverage': 'verified', 'completed_entity_fields': 'verified'}
    (directory / 'recording-independent-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
