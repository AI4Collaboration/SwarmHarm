import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--n', type=int, required=True)
    parser.add_argument('--k', type=int, required=True)
    args = parser.parse_args()
    instances = set()
    keys = set()
    previous_cleanup = 0
    receipts = []
    for repeat in range(1, 4):
        directory = args.directory / f'repeat-{repeat}'
        cloud = read(directory / 'cloud.json')
        binding = read(directory / 'binding.json')
        graph = args.directory / f'graphs/graph-{repeat}.json'
        definition = read(graph)
        assert definition['n'] == args.n and definition['k'] == args.k
        assert binding['repeat'] == repeat and len(binding['hosts']) == args.n
        assert binding['graph_sha256'] == hashlib.sha256(graph.read_bytes()).hexdigest()
        assert cloud['created_at'] > previous_cleanup
        assert len(cloud['instance_ids']) == args.n and instances.isdisjoint(cloud['instance_ids'])
        instances.update(cloud['instance_ids'])
        cleanup = read(directory / 'cleanup.json')
        release = read(directory / 'release.json')
        assert release['allowance_seconds'] == 1800
        assert cleanup['time'] >= release['T_start'] + release['allowance_seconds']
        previous_cleanup = cleanup['time']
        assert previous_cleanup - cloud['created_at'] <= 7200
        verification = read(directory / 'evidence-verification.json')
        assert verification['verified_subjects'] == args.n
        recording = read(directory / 'recording-verification.json')
        assert len({row['request_id'] for row in recording['coverage']}) == recording['requests']
        expected_objects = {obj for row in recording['coverage'] if row['request_status'] == 'completed'
                            for obj in row['expected_objects']}
        assert expected_objects <= {row['object_key'] for row in recording['receipts']}
        request_count = 0
        for index, host in enumerate(binding['hosts']):
            key = read(directory / f'private-key-{index}.json')
            assert key['id'] not in keys
            keys.add(key['id'])
            assert read(directory / f'key-revocation-{index}.json')['updateAPIKeyStatus']['status'] == 'disabled'
            metadata = read(directory / f'gateway-{index}.json')
            request_count += len(metadata['requests']['edges'])
            for edge in metadata['requests']['edges']:
                request = edge['node']
                assert request['modelID'] == 'gpt-6-luna' and request['reasoningEffort'] == 'xhigh'
                for execution in request['executions']['edges']:
                    node = execution['node']
                    if node['status'] == 'completed':
                        assert node['upstreamModelID'] == 'gpt-6-luna'
        assert request_count == recording['requests']
        scoring = read(directory / 'scoring.json')
        assert scoring['denominator'] == len(scoring['agents']) == args.n
        receipts.append({'repeat': repeat, 'subjects': args.n, 'requests': request_count,
                         'stored_objects': recording['objects'], 'stored_bytes': recording['bytes'],
                         'exact_submissions': sum(agent['exact_completion'] for agent in scoring['agents']),
                         'cleanup_time': cleanup['time']})
    result = {'case': f'N{args.n}-K{args.k}', 'repeats': receipts, 'unique_instances': len(instances),
              'unique_revoked_keys': len(keys), 'serial_fresh_environments': True}
    assert len(instances) == len(keys) == args.n * 3
    (args.directory / 'case-verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
