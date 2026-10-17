import argparse
import hashlib
import json
import shutil
import tarfile
import tomllib
from pathlib import Path

import numpy as np

from cloud import ROOT, save
from graphs import validate
from recording import retrieve
from repeat import gateway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--parent-workdir', type=Path, required=True)
    parser.add_argument('--admission-workdir', type=Path, required=True)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--issue', required=True)
    parser.add_argument('--n', type=int, required=True)
    parser.add_argument('--k', type=int, required=True)
    args = parser.parse_args()
    directory = args.directory
    directory.mkdir(parents=True, exist_ok=True)
    registrations = []
    for repeat in range(1, 4):
        source = args.parent_workdir / f'.research/graphs-{args.issue}/graph-{repeat}.json'
        target = directory / source.name
        if target.exists():
            assert target.read_bytes() == source.read_bytes()
        else:
            shutil.copyfile(source, target)
        graph = json.loads(target.read_text())
        assert (graph['n'], graph['k'], graph['repeat']) == (args.n, args.k, repeat)
        accepted, components = validate(graph['adjacency'], args.n, args.k)
        assert accepted and components == graph['scc_sizes']
        rng = np.random.Generator(np.random.PCG64(graph['seed']))
        for proposal in range(graph['proposal']):
            rows = []
            for index in range(args.n):
                choices = rng.choice(args.n - 1, size=args.k, replace=False)
                rows.append([int(value + (value >= index)) for value in choices])
            if proposal + 1 < graph['proposal']:
                assert not validate(rows, args.n, args.k)[0]
        assert rows == graph['adjacency']
        registrations.append({'repeat': repeat, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'proposals': graph['proposal'], 'networkx_and_independent_reachability': True, 'rng_replayed': True})
    assert len({json.loads((directory / f'graph-{repeat}.json').read_text())['seed'] for repeat in range(1, 4)}) == 3
    save(directory, 'graph-verification.json', registrations)
    admission = args.admission_workdir / 'SwarmHarm/experiments/peer-discovery/.scratch/admission-publication'
    goals = json.loads((admission / 'preflight-1-native-goals.json').read_text())[0]['rows']
    assert len(goals) == 1 and goals[0]['status'] == 'complete'
    key_id = json.loads((args.admission_workdir / 'private/preflight-1-key.json').read_text())['id']
    settings = gateway(args.meta_key, 'recording', '')
    save(directory, 'recording-settings.json', settings)
    export = gateway(args.meta_key, 'export', key_id)
    executions = [edge['node'] for request in export['requests']['edges'] for edge in request['node']['executions']['edges']]
    assert any(item['upstreamModelID'] == 'gpt-6-luna' and item['reasoningEffort'] == 'xhigh' for item in executions)
    save(directory, 'admission-gateway.json', export)
    recording_key = json.loads((args.admission_workdir / 'SwarmHarm/experiments/peer-discovery/.scratch/repeat-1/private-key-0.json').read_text())['id']
    recording_export = gateway(args.meta_key, 'export', recording_key)
    save(directory, 'recording-gateway.json', recording_export)
    retrieve(directory, settings, [recording_export])
    for number in (1, 2):
        cleanup = json.loads((admission / f'preflight-{number}/cleanup.json').read_text())
        assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
        assert all(instance['State']['Name'] == 'terminated' for reservation in cleanup['instances']['Reservations'] for instance in reservation['Instances'])
        save(directory, f'admission-preflight-{number}-cleanup.json', cleanup)
    frozen = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in ROOT.glob('*') if path.suffix in ('.py', '.sh', '.toml', '.txt')}
    with tarfile.open(args.admission_workdir / 'private/preflight-1-evidence.tar.gz') as archive:
        binary_hash = archive.extractfile('var/lib/peer-operator/codex.sha256').read().decode().split()[0]
        provider = archive.extractfile('home/agent/.codex/config.toml').read()
        expected_provider = (ROOT / 'provider.toml').read_bytes()
        actual_configuration = tomllib.loads(provider.decode())
        assert all(actual_configuration[key] == value for key, value in tomllib.loads(expected_provider.decode()).items())
    save(directory, 'case-admission.json', {'issue': args.issue, 'n': args.n, 'k': args.k,
        'reused_native_goal': goals[0], 'provider': 'gpt-6-luna', 'reasoning': 'xhigh',
        'harness_source': '100470a2', 'codex_binary_sha256': binary_hash,
        'provider_configuration_sha256': hashlib.sha256(expected_provider).hexdigest(), 'frozen_source_sha256': frozen})
    print(json.dumps({'issue': args.issue, 'graphs_verified': 3, 'shared_admission': 'verified', 'recording': 'verified'}))


if __name__ == '__main__':
    main()
