import argparse
import concurrent.futures
import hashlib
import json
import tarfile
from pathlib import Path

import numpy as np

from cloud import CODEX_SHA256, SESSION, save
from graphs import validate
from recording import policy
from repeat import gateway


def verify_graph(path, n, k):
    graph = json.loads(path.read_text())
    assert (graph['n'], graph['k']) == (n, k)
    assert path.name == f'graph-{graph["repeat"]}.json'
    if 'algorithm' in graph:
        from rare_graphs import engine, verify
        return verify(path, engine(path.parent / 'build'))
    rng = np.random.Generator(np.random.PCG64(graph['seed']))
    for proposal in range(1, graph['proposal'] + 1):
        rows = [[int(j + (j >= i)) for j in rng.choice(n - 1, size=k, replace=False)]
                for i in range(n)]
        accepted, components = validate(rows, n, k)
        assert accepted == (proposal == graph['proposal'])
    assert rows == graph['adjacency'] and components == graph['scc_sizes']
    assert rng.bit_generator.state == graph['rng_state']
    return {'repeat': graph['repeat'], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'proposal': graph['proposal'], 'scc_sizes': components}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--shared-workspace', type=Path, required=True)
    parser.add_argument('--meta-key', type=Path, required=True)
    parser.add_argument('--n', type=int, default=128)
    parser.add_argument('--k', type=int, default=5)
    args = parser.parse_args()
    if 'algorithm' in json.loads((args.directory / 'graph-1.json').read_text()):
        from rare_graphs import engine
        engine(args.directory / 'build')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        graphs = list(pool.map(lambda repeat: verify_graph(args.directory / f'graph-{repeat}.json', args.n, args.k),
                               (1, 2, 3)))
    source = args.shared_workspace / '.research/native-preflight'
    admission = json.loads((source / 'native-admission.json').read_text())
    assert admission['model'] == 'gpt-6.1-sol' and admission['reasoning'] == 'xhigh'
    assert admission['codex'] == '0.160.0' and admission['native_goal_status'] == 'complete'
    request = json.loads((source / 'gateway.json').read_text())
    executions = [execution['node'] for edge in request['requests']['edges']
                  for execution in edge['node']['executions']['edges']]
    assert any(node['upstreamModelID'] == 'gpt-6.1-sol' and node['reasoningEffort'] == 'xhigh'
               and node['status'] == 'completed' for node in executions)
    checksums = []
    with tarfile.open(source / 'evidence.tar.gz') as archive:
        names = archive.getnames()
        checksum_name = next(name for name in names if name.endswith('/codex.sha256'))
        checksums = archive.extractfile(checksum_name).read().decode().split()[0]
        assert checksums == CODEX_SHA256
        shell = next(name for name in names if name.endswith('/shell-admission.txt'))
        assert archive.extractfile(shell).read().strip()
    cleanup = json.loads((source / 'cleanup.json').read_text())
    assert all(instance['State']['Name'] == 'terminated'
               for reservation in cleanup['instances']['Reservations'] for instance in reservation['Instances'])
    assert all(cleanup[name] == [] for name in ('volumes', 'addresses', 'security_groups', 'key_pairs'))
    revoked = json.loads((source / 'key-revocation-0.json').read_text())['updateAPIKeyStatus']
    assert revoked['status'] == 'disabled'
    settings = policy(args.meta_key)
    save(args.directory, 'recording-policy-admission.json', settings)
    key_id = admission['thread_id']
    known_key = json.loads((source / 'private-key-0.json').read_text())
    metadata = gateway(args.meta_key, 'recording-export', known_key['id'])
    assert metadata['requests']['edges']
    storage = next(edge['node']['settings']['s3'] for edge in settings['dataStorages']['edges']
                   if edge['node']['id'] == settings['defaultDataStorageID'])
    client = SESSION.client('s3', region_name=storage['region'])
    object_receipts = []
    project = next(edge['node']['id'].rsplit('/', 1)[1] for edge in settings['projects']['edges']
                   if edge['node']['name'] == 'SWH-77-peer-discovery')
    request_id = next(edge['node']['id'].rsplit('/', 1)[1] for edge in metadata['requests']['edges']
                      if edge['node']['status'] == 'completed')
    for name in ('request_body', 'response_body', 'response_chunks'):
        object_key = f'{project}/requests/{request_id}/{name}.json'
        target = args.directory / f'admission-stored-{name}.json'
        client.download_file(storage['bucketName'], object_key, str(target))
        raw = target.read_bytes()
        assert json.loads(raw)
        object_receipts.append({'object_key': object_key, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    result = {'graphs': graphs, 'shared_codex_sha256': checksums, 'shared_native_goal_status': 'complete',
              'shared_thread_id': key_id, 'binary_provider': 'Codex 0.160.0 / gpt-6.1-sol / xhigh',
              'shared_preflight_cleanup': 'verified', 'recording_policy': 'verified',
              'paginated_metadata': 'verified', 'stored_object_receipts': object_receipts}
    save(args.directory, 'operator-admission.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
