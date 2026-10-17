import argparse
import hashlib
import json
from pathlib import Path

import networkx as nx
import numpy as np

from graphs import validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    receipts = []
    seeds = set()
    for repeat in range(1, 4):
        path = args.directory / f'graph-{repeat}.json'
        raw = path.read_bytes()
        assert raw == (args.source / path.name).read_bytes()
        graph = json.loads(raw)
        assert graph['repeat'] == repeat and graph['n'] == 64 and graph['k'] == 5
        assert graph['numpy'] == np.__version__ and graph['networkx'] == nx.__version__
        assert graph['seed'] not in seeds
        seeds.add(graph['seed'])
        rng = np.random.Generator(np.random.PCG64(graph['seed']))
        for proposal in range(1, graph['proposal'] + 1):
            rows = []
            for vertex in range(graph['n']):
                choices = rng.choice(graph['n'] - 1, size=graph['k'], replace=False)
                rows.append([int(peer + (peer >= vertex)) for peer in choices])
            accepted, components = validate(rows, graph['n'], graph['k'])
            assert accepted == (proposal == graph['proposal'])
        assert rows == graph['adjacency'] and rng.bit_generator.state == graph['rng_state']
        assert components == graph['scc_sizes']
        receipts.append({'repeat': repeat, 'sha256': hashlib.sha256(raw).hexdigest(),
                         'proposals': graph['proposal'], 'scc_sizes': components,
                         'networkx_and_pairwise_reachability': True, 'uniform_draw_replay': True})
    (args.directory / 'verification.json').write_text(json.dumps(receipts, indent=2))
    print(json.dumps(receipts, indent=2))


if __name__ == '__main__':
    main()
