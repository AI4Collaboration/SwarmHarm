import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from botocore.config import Config

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / 'operator-code/experiments/peer-discovery'
sys.path.insert(0, str(SOURCE))
from cloud import EC2, SESSION, save
from repeat import gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repeat', type=int)
    args = parser.parse_args()
    directory = BASE / f'repeat-{args.repeat}'
    meta_key = Path('/home/cpt-llm/Playground/cpt-llm-agent-workspace/swarmharm-dd7d0eb4a945/swh-78-068357cad047/workdir/private/swh6-ed25519')
    subprocess.run([sys.executable, str(SOURCE / 'monitor.py'), str(directory)], check=True)
    observation = json.loads(max((directory / 'operator-observations').glob('*.json')).read_text())
    if all('codex-process-start' in row['receipts'] and 'native-goals' in row['receipts'] for row in observation):
        starts = []
        goals = []
        for row in observation:
            receipts = row['receipts']
            native = receipts['native-goals']['goals']
            assert len(native) == 1 and native[0]['objective'] == (SOURCE / 'objective.txt').read_text().strip()
            starts.append(receipts['codex-process-start']['create_time'] +
                          receipts['boot-clock-correction']['psutil_epoch_correction_seconds'])
            goals.append(native[0]['created_at_ms'] / 1000)
        launch = {'observed_at': time.time(), 'subjects': len(observation), 'accepted_native_goals': len(goals),
                  'process_start_skew_seconds': max(starts) - min(starts),
                  'goal_acceptance_skew_seconds': max(goals) - min(goals)}
        save(directory, 'launch-verification.json', launch)
        print(json.dumps(launch), flush=True)
    subprocess.run([sys.executable, str(SOURCE / 'contention.py'), str(directory), '--meta-key', str(meta_key)], check=True)
    if (directory / 'hardware-readback.json').exists() and (directory / 'live-recording-check.json').exists():
        return
    cloud = json.loads((directory / 'cloud.json').read_text())
    volumes = EC2.describe_volumes(VolumeIds=cloud['volume_ids'])
    assert len(volumes['Volumes']) == 32
    assert all(item['Encrypted'] and item['Size'] == 12 and item['VolumeType'] == 'gp3' for item in volumes['Volumes'])
    instance_type = EC2.describe_instance_types(InstanceTypes=['t2.micro'])['InstanceTypes'][0]
    assert instance_type['VCpuInfo']['DefaultVCpus'] == 1 and instance_type['MemoryInfo']['SizeInMiB'] == 1024
    save(directory, 'hardware-readback.json', {'volumes': volumes, 'instance_type': instance_type})
    binding = json.loads((directory / 'binding.json').read_text())
    chosen = None
    for index, host in enumerate(binding['hosts']):
        key = json.loads((directory / f'private-key-{index}.json').read_text())
        exported = gateway(meta_key, 'export', key['id'])
        save(directory, f'live-gateway-{index}.json', exported)
        for edge in exported['requests']['edges']:
            request = edge['node']
            executions = [item['node'] for item in request['executions']['edges'] if item['node']['status'] == 'completed']
            if request['status'] == 'completed' and executions:
                chosen = (key, request, executions[0])
                break
        if chosen:
            break
    assert chosen
    key, request, execution = chosen
    policy = json.loads((directory / 'recording-policy.json').read_text())
    storage = next(edge['node'] for edge in policy['dataStorages']['edges'] if edge['node']['id'] == policy['defaultDataStorageID'])
    settings = storage['settings']['s3']
    client = SESSION.client('s3', region_name=settings['region'], endpoint_url=settings['endpoint'] or None,
        config=Config(connect_timeout=10, read_timeout=60, s3={'addressing_style': 'path' if settings['pathStyle'] else 'auto'}))
    prefix = f"{key['project_id'].rsplit('/', 1)[1]}/requests/{request['id'].rsplit('/', 1)[1]}"
    rows = []
    for location in (prefix, f"{prefix}/executions/{execution['id'].rsplit('/', 1)[1]}"):
        for name in ('request_body', 'response_body', 'response_chunks'):
            object_key = f'{location}/{name}.json'
            target = directory / 'live-stored-payloads' / object_key
            target.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(settings['bucketName'], object_key, str(target))
            raw = target.read_bytes()
            assert json.loads(raw)
            rows.append({'object_key': object_key, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    save(directory, 'live-recording-check.json', {'observed_at': time.time(), 'object_count': len(rows),
        'objects': rows, 's3_get_requests': len(rows), 's3_head_requests': len(rows)})
    print(json.dumps({'live_payload_objects': len(rows), 'payload_bytes': sum(row['bytes'] for row in rows)}))


if __name__ == '__main__':
    main()
