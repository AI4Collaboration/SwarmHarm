import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workspace', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    output = args.output.resolve()
    assert not output.exists()
    output.mkdir(parents=True)
    experiment = workspace / 'SwarmHarm/experiments/peer-discovery'
    private = workspace / 'private'
    for repeat in (1, 2):
        source = experiment / f'.scratch/preflight-{repeat}'
        destination = output / f'preflight-{repeat}'
        destination.mkdir()
        for path in source.glob('*'):
            if path.suffix in ('.json', '.txt') and not path.name.startswith('private-key-'):
                shutil.copyfile(path, destination / path.name)
    with tarfile.open(private / 'preflight-1-evidence.tar.gz') as archive:
        archive.extractall(output / 'preflight-1/raw', filter='data')
    for name in ('preflight-1-native-goals.json', 'preflight-1-gateway.json', 'preflight-1-key-revocation.json',
        'permission-probes.json', 'quota-probe.json', 'token-quota-probe.json',
        'preflight-quota-readback.json', 'preflight-token-quota-readback.json', 'gateway-prices.json'):
        shutil.copyfile(private / name, output / name)
    metadata = output / 'case'
    metadata.mkdir()
    manifest = {}
    for path in (experiment / '.scratch/SWH-78').glob('*.json'):
        shutil.copyfile(path, metadata / path.name)
        manifest[path.name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'mtime_ns': path.stat().st_mtime_ns}
    shutil.copyfile(workspace / 'attachments/SWH77-experiment-plan.md', metadata / 'protocol.md')
    (metadata / 'source-manifest.json').write_text(json.dumps(manifest, indent=2))
    costs = []
    for repeat in (1, 2):
        directory = output / f'preflight-{repeat}'
        cloud = json.loads((directory / 'cloud.json').read_text())
        cleanup = json.loads((directory / 'cleanup.json').read_text())
        hours = (cleanup['time'] - cloud['created_at']) / 3600
        costs.append({'preflight': repeat, 'instances': len(cloud['instance_ids']), 'instance_hours': hours,
            'ec2_ipv4_gp3_usd_estimate': hours * (0.0134 + 0.005 + 12 * 0.0952 / 730),
            'subject_invocations': 1 if repeat == 1 else 0})
    (output / 'preflight-costs.json').write_text(json.dumps(costs, indent=2))
    print(json.dumps({'staged_admission_artifact': str(output), 'preflight_instances': 2, 'native_goal_invocations': 1, 'costs': costs}))


if __name__ == '__main__':
    main()
