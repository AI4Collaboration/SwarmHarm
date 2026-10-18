import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path

from cloud import save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.directory / 'recording-receipts.json').read_text())
    binding = json.loads((args.directory / 'binding.json').read_text())
    requests = []
    executions = []
    expected = set()
    completed_expected = set()
    for index, host in enumerate(binding['hosts']):
        key = json.loads((args.directory / f'private-key-{index}.json').read_text())
        metadata = json.loads((args.directory / f'gateway-{index}.json').read_text())
        for edge in metadata['requests']['edges']:
            request = edge['node']
            requests.append(request)
            link = next(row for row in manifest['metadata'] if row['request_id'] == request['id'])
            assert link['instance_id'] == host['id'] and link['api_key_id'] == key['id']
            client_key = next(name for name in link['objects']
                              if name.endswith('/request_body.json') and '/executions/' not in name)
            prefix = client_key.removesuffix('request_body.json')
            entities = [(request, prefix)]
            for item in request['executions']['edges']:
                execution = item['node']
                executions.append(execution)
                entities.append((execution, prefix + f'executions/{execution["id"].rsplit("/", 1)[1]}/'))
            for entity, base in entities:
                expected.add(base + 'request_body.json')
                if entity['status'] == 'completed':
                    fields = {base + name + '.json' for name in ('request_body', 'response_body', 'response_chunks')}
                    expected.update(fields)
                    completed_expected.update(fields)
    stored = set()
    total_bytes = 0
    provider_sessions = collections.defaultdict(set)
    provider_triggers = collections.Counter()
    for receipt in manifest['receipts']:
        assert receipt['object_key'] not in stored
        stored.add(receipt['object_key'])
        path = args.directory / 'stored-payloads' / (receipt['object_key'] + '.gz')
        raw = gzip.decompress(path.read_bytes())
        assert len(raw) == receipt['bytes'] and hashlib.sha256(raw).hexdigest() == receipt['sha256']
        payload = json.loads(raw)
        assert payload
        if receipt['object_key'].endswith('/request_body.json') and '/executions/' not in receipt['object_key']:
            metadata = payload['client_metadata']
            session_id = metadata['session_id']
            assert session_id == metadata['thread_id'] == payload['prompt_cache_key']
            if receipt['session_id'] is not None:
                assert session_id == receipt['session_id']
            provider_sessions[receipt['instance_id']].add(session_id)
            turn = json.loads(metadata['x-codex-turn-metadata'])
            assert turn['session_id'] == session_id
            assert payload['model'] == turn['model'] == 'gpt-6.1-sol'
            assert payload['reasoning']['effort'] == turn['reasoning_effort'] == 'xhigh'
            provider_triggers[turn['turn_trigger']] += 1
        total_bytes += len(raw)
    assert len(requests) == manifest['requests'] and len(stored) == manifest['objects']
    assert total_bytes == manifest['bytes']
    assert len(expected) == manifest['expected_objects']
    assert len(expected & stored) == manifest['stored_expected_objects']
    assert all(len(sessions) == 1 for sessions in provider_sessions.values())
    result = {'subjects': len(binding['hosts']), 'requests': len(requests), 'executions': len(executions),
              'client_states': dict(collections.Counter(row['status'] for row in requests)),
              'execution_states': dict(collections.Counter(row['status'] for row in executions)),
              'verified_objects': len(stored), 'verified_bytes': total_bytes,
              'expected_objects': len(expected), 'stored_expected_objects': len(expected & stored),
              'completed_entity_expected_objects': len(completed_expected),
              'completed_entity_stored_objects': len(completed_expected & stored),
              'provider_session_bindings': {instance: next(iter(sessions))
                                            for instance, sessions in sorted(provider_sessions.items())},
              'provider_turn_triggers': dict(provider_triggers),
              'unrecorded_objects': sorted(expected - stored),
              'coverage_complete': expected <= stored}
    save(args.directory, 'independent-recording-verification.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
