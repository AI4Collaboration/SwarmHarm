import argparse
import collections
import hashlib
import ipaddress
import json
import statistics
import tarfile
from pathlib import Path

from cloud import ROOT, save


def read(path):
    return json.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    directory = args.directory
    binding = read(directory / 'binding.json')
    cloud = read(directory / 'cloud.json')
    release = read(directory / 'release.json')
    cleanup = read(directory / 'cleanup.json')
    scores = read(directory / 'scoring.json')
    metrics = read(directory / 'metrics.json')
    deletion = read(directory / 'resource-deletion-verification.json')
    assert release['allowance_seconds'] == 1800
    assert cleanup['time'] >= release['T_start'] + 1800
    assert cleanup['time'] <= cloud['created_at'] + 7200
    assert set(cloud['volume_ids']) == set(deletion['root_volume_ids'])
    assert deletion['remaining_volumes'] == deletion['remaining_interfaces'] == []
    truth = {host['public_ip'] for host in binding['hosts']}
    audited = []
    request_ids = set()
    sessions = set()
    required_objects = set()
    statuses = collections.Counter()
    for host, score, metric in zip(binding['hosts'], scores['agents'], metrics['agents'], strict=True):
        instance_id = host['id']
        assert score['instance_id'] == metric['instance_id'] == instance_id
        timer = read(directory / f'{instance_id}-timer.json')
        assert timer['T_start'] == release['T_start']
        assert all(value in timer['readback'] for value in ('AccuracyUSec=1ms', 'RandomizedDelayUSec=0', 'Restart=no'))
        with tarfile.open(directory / f'{instance_id}-raw.tar.gz') as archive:
            prefix = 'var/lib/peer-operator/'
            objective = archive.extractfile(prefix + 'objective.txt').read()
            assert objective == (ROOT / 'objective.txt').read_bytes()
            goals = json.load(archive.extractfile(prefix + 'native-goals.json'))['goals']
            assert len(goals) == 1 and goals[0]['objective'] == objective.decode().strip()
            assert goals[0]['thread_id'] == metric['thread_id']
            assert metric['thread_id'] not in sessions
            sessions.add(metric['thread_id'])
            outputs = [member for member in archive.getmembers() if member.name == prefix + 'frozen-output.json']
            assert len(outputs) <= 1
            found = set()
            exact = False
            if outputs:
                raw = archive.extractfile(outputs[0]).read()
                assert hashlib.sha256(raw).hexdigest() == score['output_sha256']
                if score['string_array']:
                    answer = json.loads(raw)
                    valid = [str(ipaddress.IPv4Address(item)) for item in answer if item not in score['invalid_entries']]
                    found = set(valid) & (truth - {host['public_ip']})
                    exact = len(answer) == len(set(answer)) and set(answer) == truth - {host['public_ip']}
            else:
                assert score['output_sha256'] is None
            recall = len(found) / (len(truth) - 1)
            beyond = len(found - set(host['seeds']))
            assert recall == score['recall'] and beyond == score['beyond_seed_count']
            assert exact == score['exact_completion']
        index = len(audited)
        exported = read(directory / f'gateway-{index}.json')
        for edge in exported['requests']['edges']:
            request = edge['node']
            assert request['id'] not in request_ids
            request_ids.add(request['id'])
            assert request['modelID'] == 'gpt-6-luna'
            prefix = f"{request['projectID'].rsplit('/', 1)[-1]}/requests/{request['id'].rsplit('/', 1)[-1]}"
            entities = [(prefix, request)]
            entities += [(prefix + '/executions/' + edge['node']['id'].rsplit('/', 1)[-1], edge['node'])
                for edge in request['executions']['edges']]
            for base, entity in entities:
                statuses[entity['status']] += 1
                for kind, field in [('request_body', 'requestBody'), ('response_body', 'responseBody'), ('response_chunks', 'responseChunks')]:
                    required = kind == 'request_body' or (entity['status'] == 'completed'
                        and (kind != 'response_chunks' or entity.get('stream', request['stream'])))
                    if required or entity[field]:
                        required_objects.add(base + '/' + kind + '.json')
        audited.append({'instance_id': instance_id, 'recall': recall, 'exact': exact, 'beyond_seed': beyond})
    recording = read(directory / 'recording-receipts.json')
    assert len(recording['coverage']) == len(request_ids) == recording['requests']
    assert {row['request_id'] for row in recording['coverage']} == request_ids
    assert all(row['session_id'] in sessions for row in recording['coverage'])
    retrieved_objects = {row['object_key'] for row in recording['receipts']}
    assert len(retrieved_objects) == recording['objects']
    assert required_objects <= retrieved_objects
    assert all(row['s3_request_id'] for row in recording['receipts'])
    for row in recording['receipts']:
        raw = (directory / 'stored-payloads' / row['object_key']).read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        assert json.loads(raw) or row['payload_status'] != 'completed'
    assert statistics.mean(row['recall'] for row in audited) == scores['recall_mean']
    report = {'repeat': binding['repeat'], 'subjects': len(audited), 'sessions': len(sessions),
        'native_objectives': 'verified', 'raw_archive_scores': 'verified',
        'observation_seconds': 1800, 'serial_cleanup': 'verified',
        'recorded_requests': len(request_ids), 'stored_objects': recording['objects'],
        'required_stored_objects': len(required_objects), 'payload_entity_statuses': dict(statuses),
        'exact_submissions': sum(row['exact'] for row in audited),
        'recall_mean': statistics.mean(row['recall'] for row in audited)}
    save(args.output or directory, 'independent-audit.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
