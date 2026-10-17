import argparse
import hashlib
import itertools
import json
import secrets
from pathlib import Path

import networkx as nx
import numpy as np


def independent_reachability(rows):
    reached = []
    for source in range(len(rows)):
        seen, pending = {source}, [source]
        while pending:
            for target in rows[pending.pop()]:
                if target not in seen:
                    seen.add(target)
                    pending.append(target)
        reached.append(seen)
    return all(v in reached[u] or u in reached[v] for u, v in itertools.combinations(range(len(rows)), 2))


def validate(rows, n, k):
    assert len(rows) == n
    assert all(len(row) == len(set(row)) == k and i not in row and all(0 <= j < n for j in row) for i, row in enumerate(rows))
    graph = nx.DiGraph()
    graph.add_nodes_from(range(n))
    graph.add_edges_from((i, j) for i, row in enumerate(rows) for j in row)
    predicate = nx.is_semiconnected(graph)
    assert predicate == independent_reachability(rows)
    return predicate, sorted(map(len, nx.strongly_connected_components(graph)), reverse=True)


def sample(n, k, seed, checkpoint):
    assert 0 < k < n
    rng = np.random.Generator(np.random.PCG64(seed))
    proposal = 0
    if checkpoint.exists():
        previous = json.loads(checkpoint.read_text())
        assert previous['seed'] == seed
        rng.bit_generator.state = previous['rng_state']
        proposal = previous['proposal']
    while True:
        rows = []
        for i in range(n):
            choices = rng.choice(n - 1, size=k, replace=False)
            rows.append([int(j + (j >= i)) for j in choices])
        proposal += 1
        if sum(degree == 0 for degree in np.bincount(np.asarray(rows).ravel(), minlength=n)) <= 1:
            accepted, components = validate(rows, n, k)
            if accepted:
                return {'n': n, 'k': k, 'seed': seed, 'proposal': proposal, 'adjacency': rows,
                    'scc_sizes': components, 'rng': 'PCG64', 'rng_state': rng.bit_generator.state,
                    'numpy': np.__version__, 'networkx': nx.__version__, 'assignment_seed': secrets.randbits(128)}
        if proposal % 10000 == 0:
            checkpoint.write_text(json.dumps({'seed': seed, 'proposal': proposal, 'rng_state': rng.bit_generator.state}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--n', type=int, required=True)
    parser.add_argument('--k', type=int, required=True)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    for repeat in range(1, 4):
        target = args.directory / f'graph-{repeat}.json'
        assert not target.exists(), target
        checkpoint = args.directory / f'checkpoint-{repeat}.json'
        seed = json.loads(checkpoint.read_text())['seed'] if checkpoint.exists() else secrets.randbits(128)
        graph = sample(args.n, args.k, seed, checkpoint)
        graph['repeat'] = repeat
        encoded = json.dumps(graph, sort_keys=True).encode()
        target.write_bytes(encoded)
        print(json.dumps({'repeat': repeat, 'proposal': graph['proposal'], 'sha256': hashlib.sha256(encoded).hexdigest()}))


if __name__ == '__main__':
    main()
