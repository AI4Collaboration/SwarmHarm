import argparse
import concurrent.futures
import json
import subprocess
import time
from pathlib import Path

import boto3
from botocore.config import Config


ROOT = Path(__file__).parent
CODEX_SHA256 = '12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad'
SESSION = boto3.Session(profile_name='eurosafeai', region_name='eu-central-1')
EC2 = SESSION.client('ec2', config=Config(retries={'total_max_attempts': 2, 'mode': 'standard'}, connect_timeout=10, read_timeout=30))


def save(directory, name, value):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    temporary = target.with_suffix(target.suffix + '.writing')
    temporary.write_text(json.dumps(value, default=str, indent=2))
    temporary.replace(target)


def ssh(directory, host, command, data=None, check=True):
    return subprocess.run(['ssh', '-i', str(directory / 'operator-key'), '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        '-o', 'ServerAliveInterval=10', '-o', 'StrictHostKeyChecking=accept-new', '-o', f'UserKnownHostsFile={directory / "known_hosts"}',
        f'ubuntu@{host}', command], input=data, capture_output=True, check=check)


def launch(directory, count, purpose, issue='SWH-78', n=4, k=2, lifetime=3600):
    assert not (directory / 'cloud.json').exists()
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(directory / 'operator-key')], check=True)
    tags = [{'Key': key, 'Value': value} for key, value in {
        'project': 'swarmharm', 'issue': issue, 'parent': 'SWH-77', 'case': f'N{n}-K{k}', 'purpose': purpose}.items()]
    state = {'key_name': f'{issue.lower()}-{purpose}', 'issue': issue, 'purpose': purpose,
        'instance_ids': [], 'volume_ids': [], 'created_at': time.time(), 'lifetime_seconds': lifetime}
    save(directory, 'cloud.json', state)
    EC2.import_key_pair(KeyName=state['key_name'], PublicKeyMaterial=(directory / 'operator-key.pub').read_bytes(),
        TagSpecifications=[{'ResourceType': 'key-pair', 'Tags': tags}])
    group = EC2.create_security_group(GroupName=state['key_name'], Description='SWH-77 approved disposable peer discovery lab',
        VpcId='vpc-0dc6260011176dcae', TagSpecifications=[{'ResourceType': 'security-group', 'Tags': tags}])
    state['security_group_id'] = group['GroupId']
    save(directory, 'cloud.json', state)
    EC2.authorize_security_group_ingress(GroupId=group['GroupId'], IpPermissions=[{'IpProtocol': '-1', 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}])
    nacls = EC2.describe_network_acls(Filters=[{'Name': 'association.subnet-id', 'Values': ['subnet-0f9b3bc5da2c0c635']}])
    save(directory, 'network-acl.json', nacls)
    for egress in (True, False):
        rules = [entry for acl in nacls['NetworkAcls'] for entry in acl['Entries'] if entry['Egress'] == egress]
        assert any(rule.get('CidrBlock') == '0.0.0.0/0' and rule['RuleAction'] == 'allow' and rule['Protocol'] == '-1' for rule in rules)
    instances = EC2.run_instances(ImageId='ami-0b8a830d6339a9758', InstanceType='t2.micro', MinCount=count, MaxCount=count,
        KeyName=state['key_name'], ClientToken=state['key_name'],
        NetworkInterfaces=[{'DeviceIndex': 0, 'SubnetId': 'subnet-0f9b3bc5da2c0c635', 'Groups': [group['GroupId']], 'AssociatePublicIpAddress': True}],
        MetadataOptions={'HttpEndpoint': 'enabled', 'HttpTokens': 'required'}, CreditSpecification={'CpuCredits': 'standard'},
        InstanceInitiatedShutdownBehavior='terminate',
        BlockDeviceMappings=[{'DeviceName': '/dev/sda1', 'Ebs': {'VolumeSize': 12, 'VolumeType': 'gp3', 'Encrypted': True, 'DeleteOnTermination': True}}],
        TagSpecifications=[{'ResourceType': kind, 'Tags': tags} for kind in ('instance', 'volume')])
    state['instance_ids'] = [instance['InstanceId'] for instance in instances['Instances']]
    save(directory, 'cloud.json', state)
    EC2.get_waiter('instance_running').wait(InstanceIds=state['instance_ids'], WaiterConfig={'Delay': 5, 'MaxAttempts': 60})
    readback = EC2.describe_instances(InstanceIds=state['instance_ids'])
    save(directory, 'launch-readback.json', readback)
    hosts = [instance for reservation in readback['Reservations'] for instance in reservation['Instances']]
    state['hosts'] = [{'id': instance['InstanceId'], 'public_ip': instance['PublicIpAddress'],
        'private_ip': instance['PrivateIpAddress']} for instance in hosts]
    state['volume_ids'] = [mapping['Ebs']['VolumeId'] for instance in hosts for mapping in instance['BlockDeviceMappings'] if 'Ebs' in mapping]
    save(directory, 'cloud.json', state)
    def prepare(host):
        deadline = time.monotonic() + 300
        while True:
            result = ssh(directory, host['public_ip'], 'true', check=False)
            if result.returncode == 0:
                break
            assert time.monotonic() < deadline, result.stderr.decode()
            time.sleep(5)
        remaining_minutes = max(1, int((state['created_at'] + lifetime - time.time()) / 60))
        result = ssh(directory, host['public_ip'], f'sudo shutdown -h +{remaining_minutes}')
        EC2.modify_instance_metadata_options(InstanceId=host['id'], HttpEndpoint='disabled')
        result = ssh(directory, host['public_ip'], 'sudo bash -s', (ROOT / 'bootstrap.sh').read_bytes(), check=False)
        (directory / f'{host["id"]}-bootstrap.txt').write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr.decode()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 32)) as pool:
        list(pool.map(prepare, state['hosts']))
    print(json.dumps(state))


def cleanup(directory):
    state = json.loads((directory / 'cloud.json').read_text())
    if state['instance_ids']:
        save(directory, 'termination.json', EC2.terminate_instances(InstanceIds=state['instance_ids']))
        EC2.get_waiter('instance_terminated').wait(InstanceIds=state['instance_ids'], WaiterConfig={'Delay': 5, 'MaxAttempts': 100})
    filters = [{'Name': 'tag:issue', 'Values': [state.get('issue', 'SWH-78')]},
        {'Name': 'tag:purpose', 'Values': [state.get('purpose', state['key_name'].removeprefix('swh78-'))]}]
    volumes = EC2.describe_volumes(Filters=filters)['Volumes']
    assert not volumes, volumes
    addresses = EC2.describe_addresses(Filters=filters)['Addresses']
    assert not addresses, addresses
    if state.get('security_group_id'):
        EC2.delete_security_group(GroupId=state['security_group_id'])
    EC2.delete_key_pair(KeyName=state['key_name'])
    receipt = {'time': time.time(), 'instances': EC2.describe_instances(InstanceIds=state['instance_ids']) if state['instance_ids'] else {},
        'volumes': volumes, 'addresses': addresses,
        'security_groups': EC2.describe_security_groups(Filters=filters)['SecurityGroups'],
        'key_pairs': EC2.describe_key_pairs(Filters=filters)['KeyPairs']}
    assert not receipt['security_groups'] and not receipt['key_pairs']
    save(directory, 'cleanup.json', receipt)
    print(json.dumps({'cleanup': 'verified', 'instance_ids': state['instance_ids']}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['launch', 'cleanup'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--purpose', default='preflight-1')
    args = parser.parse_args()
    if args.mode == 'launch':
        launch(args.directory, args.count, args.purpose)
    else:
        cleanup(args.directory)


if __name__ == '__main__':
    main()
