import argparse
import datetime
import fcntl
import json
from pathlib import Path
import sqlite3
import subprocess


SUBNET = 'subnet-0f9b3bc5da2c0c635'
SUBJECT_LIMIT = 244


def aws(service, operation, *arguments):
    result = subprocess.run(
        ['aws', '--profile', 'eurosafeai', '--region', 'eu-central-1',
         '--cli-connect-timeout', '10', '--cli-read-timeout', '30',
         service, operation, *arguments, '--output', 'json'],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def quota(service, code):
    return aws('service-quotas', 'get-service-quota', '--service-code', service,
               '--quota-code', code)['Quota']['Value']


def tags(resource):
    return {tag['Key'].lower(): tag['Value'] for tag in resource.get('Tags', [])}


def snapshot():
    reservations = aws('ec2', 'describe-instances')['Reservations']
    instances = [instance for reservation in reservations for instance in reservation['Instances']
                 if instance['State']['Name'] in ('pending', 'running', 'stopping', 'stopped')]
    subnet = aws('ec2', 'describe-subnets', '--subnet-ids', SUBNET)['Subnets'][0]
    volumes = aws('ec2', 'describe-volumes')['Volumes']
    interfaces = aws('ec2', 'describe-network-interfaces')['NetworkInterfaces']
    used_cpu = sum(instance['CpuOptions']['CoreCount'] * instance['CpuOptions']['ThreadsPerCore']
                   for instance in instances if instance['State']['Name'] in ('pending', 'running'))
    return {
        'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'vcpu_quota': quota('ec2', 'L-1216C47A'), 'used_vcpus': used_cpu,
        'subnet_available_ips': subnet['AvailableIpAddressCount'],
        'eni_quota': quota('vpc', 'L-DF5E4CA3'), 'used_enis': len(interfaces),
        'gp3_quota_gib': quota('ebs', 'L-7A658B76') * 1024,
        'used_gp3_gib': sum(volume['Size'] for volume in volumes if volume['VolumeType'] == 'gp3'),
        'instances': instances, 'volumes': volumes,
    }


def evaluate(rows, live):
    phantom_cpu = 0
    phantom_ips = 0
    phantom_storage = 0
    for issue, count in rows:
        owned = [instance for instance in live['instances']
                 if tags(instance).get('parent') == 'SWH-77' and tags(instance).get('issue') == issue]
        active = [instance for instance in owned if instance['State']['Name'] in ('pending', 'running')]
        assert len(owned) <= count, f'{issue} instance count exceeds reservation'
        phantom_cpu += count - len(active)
        phantom_ips += count - len(owned)
        owned_gib = sum(volume['Size'] for volume in live['volumes']
                        if tags(volume).get('parent') == 'SWH-77' and tags(volume).get('issue') == issue
                        and volume['VolumeType'] == 'gp3')
        phantom_storage += max(0, count * 12 - owned_gib)
    demand = {
        'reserved_subjects': sum(count for _, count in rows), 'subject_limit': SUBJECT_LIMIT,
        'vcpu_committed': live['used_vcpus'] + phantom_cpu, 'vcpu_quota': live['vcpu_quota'],
        'reserved_additional_ips': phantom_ips, 'subnet_available_ips': live['subnet_available_ips'],
        'eni_committed': live['used_enis'] + phantom_ips, 'eni_quota': live['eni_quota'],
        'gp3_committed_gib': live['used_gp3_gib'] + phantom_storage, 'gp3_quota_gib': live['gp3_quota_gib'],
    }
    admitted = (demand['reserved_subjects'] <= SUBJECT_LIMIT
                and demand['vcpu_committed'] <= live['vcpu_quota']
                and phantom_ips <= live['subnet_available_ips']
                and demand['eni_committed'] <= live['eni_quota']
                and demand['gp3_committed_gib'] <= live['gp3_quota_gib'])
    return admitted, demand


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['reserve', 'release', 'status'])
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--issue')
    parser.add_argument('--n', type=int, choices=[16, 32, 64, 128])
    args = parser.parse_args()
    if args.action != 'status':
        assert args.issue
    if args.action == 'reserve':
        assert args.n
    args.state_dir.mkdir(parents=True, exist_ok=True)
    with (args.state_dir / 'admission.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with sqlite3.connect(args.state_dir / 'admission.sqlite3') as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS leases (issue TEXT PRIMARY KEY, n INTEGER, reserved_at TEXT)')
            rows = connection.execute('SELECT issue, n FROM leases ORDER BY reserved_at, issue').fetchall()
            live = snapshot()
            if args.action == 'reserve':
                existing = dict(rows).get(args.issue)
                assert existing is None or existing == args.n
                proposed = rows if existing else rows + [(args.issue, args.n)]
                admitted, demand = evaluate(proposed, live)
                if not admitted:
                    print(json.dumps({'state': 'waiting_for_capacity', 'demand': demand}, indent=2))
                    raise SystemExit(2)
                connection.execute('INSERT OR IGNORE INTO leases VALUES (?, ?, ?)',
                                   (args.issue, args.n, live['checked_at']))
                rows = proposed
            elif args.action == 'release':
                owned_instances = [instance['InstanceId'] for instance in live['instances']
                                   if tags(instance).get('parent') == 'SWH-77'
                                   and tags(instance).get('issue') == args.issue]
                owned_volumes = [volume['VolumeId'] for volume in live['volumes']
                                 if tags(volume).get('parent') == 'SWH-77'
                                 and tags(volume).get('issue') == args.issue]
                assert not owned_instances and not owned_volumes, (owned_instances, owned_volumes)
                connection.execute('DELETE FROM leases WHERE issue=?', (args.issue,))
                rows = [(issue, count) for issue, count in rows if issue != args.issue]
            admitted, demand = evaluate(rows, live)
            receipt = {'checked_at': live['checked_at'], 'action': args.action, 'capacity_valid': admitted,
                       'leases': [{'issue': issue, 'n': count} for issue, count in rows], 'demand': demand}
            connection.execute('CREATE TABLE IF NOT EXISTS events (created_at TEXT, receipt TEXT)')
            connection.execute('INSERT INTO events VALUES (?, ?)', (live['checked_at'], json.dumps(receipt)))
            print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
