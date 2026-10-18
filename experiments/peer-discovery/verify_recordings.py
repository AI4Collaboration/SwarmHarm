import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    report = json.loads((args.directory / 'recording-verification.json').read_text())
    receipts = {row['object_key']: row for row in report['receipts']}
    assert len(receipts) == report['objects']
    assert sum(row['bytes'] for row in receipts.values()) == report['bytes']
    for object_key, receipt in receipts.items():
        raw = (args.directory / 'stored-payloads' / object_key).read_bytes()
        assert len(raw) == receipt['bytes']
        assert hashlib.sha256(raw).hexdigest() == receipt['sha256']
        value = json.loads(raw)
        assert bool(value) == receipt['nonempty_json']
    completed_executions = 0
    entities = 0
    required_objects = set()
    for row in report['coverage']:
        request_id = row['request_id'].rsplit('/', 1)[1]
        request_keys = row['stored_objects']
        prefix = next(key.split(f'/requests/{request_id}/')[0] + f'/requests/{request_id}/'
                      for key in request_keys)
        required = {prefix + 'request_body.json'}
        entities += 1
        if row['request_status'] == 'completed':
            required.update(prefix + name + '.json' for name in ('request_body', 'response_body', 'response_chunks'))
        for edge in row['executions']['edges']:
            execution = edge['node']
            execution_id = execution['id'].rsplit('/', 1)[1]
            required.add(prefix + f'executions/{execution_id}/request_body.json')
            entities += 1
            if execution['status'] == 'completed':
                completed_executions += 1
                required.update(prefix + f'executions/{execution_id}/' + name + '.json'
                                for name in ('request_body', 'response_body', 'response_chunks'))
        assert required <= set(request_keys) <= receipts.keys()
        assert all(receipts[key]['nonempty_json'] for key in required)
        required_objects.update(required)
    result = {'requests': report['requests'], 'completed_executions': completed_executions,
              'objects': report['objects'], 'bytes': report['bytes'],
              'client_and_execution_entities': entities, 'required_request_bodies': entities,
              'required_objects': len(required_objects),
              'stored_json_hashes_and_completion_coverage': 'verified'}
    (args.directory / 'recording-independent-verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
