import argparse
import concurrent.futures
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

import Cython
import networkx as nx
import numpy as np
import pyximport

from graphs import validate


ALGORITHM = 'PCG64-uint32-ordered-pair-rejection-v1'


def engine(build_directory):
    build_directory.mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(build_directory.resolve())
    pyximport.install(build_dir=str(build_directory), setup_args={'include_dirs': np.get_include()},
                      language_level=3)
    from rare_draw import draw
    return draw


def save(path, value):
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(value, sort_keys=True) + '\n')
    pending.replace(path)


def sample(directory, repeat, n, draw, block):
    target = directory / f'graph-{repeat}.json'
    checkpoint = directory / f'checkpoint-{repeat}.json'
    if target.exists():
        graph = json.loads(target.read_text())
        assert graph['algorithm'] == ALGORITHM and graph['n'] == n and graph['repeat'] == repeat
        assert validate(graph['adjacency'], n, 2)[0]
        return
    if checkpoint.exists():
        record = json.loads(checkpoint.read_text())
        assert record['algorithm'] == ALGORITHM and record['n'] == n and record['repeat'] == repeat
    else:
        record = {'algorithm': ALGORITHM, 'n': n, 'k': 2, 'repeat': repeat,
                  'seed': secrets.randbits(128), 'assignment_seed': secrets.randbits(128),
                  'proposal': 0, 'candidate_proposals': [], 'cpu_seconds': 0.0,
                  'numpy': np.__version__, 'networkx': nx.__version__, 'cython': Cython.__version__,
                  'rng': 'PCG64', 'started_at': time.time()}
        generator = np.random.PCG64(record['seed'])
        record['rng_state'] = generator.state
        save(checkpoint, record)
    generator = np.random.PCG64(record['seed'])
    generator.state = record['rng_state']
    while True:
        started = time.process_time()
        consumed, rows = draw(generator, n, block)
        record['cpu_seconds'] += time.process_time() - started
        record['proposal'] += consumed
        record['rng_state'] = generator.state
        record['updated_at'] = time.time()
        accepted = False
        if rows is not None:
            accepted, components = validate(rows, n, 2)
            record['candidate_proposals'].append({'proposal': record['proposal'], 'accepted': accepted})
        save(checkpoint, record)
        with (directory / f'checkpoints-{repeat}.jsonl').open('a') as history:
            history.write(json.dumps(record, sort_keys=True) + '\n')
        print(json.dumps({'repeat': repeat, 'proposals': record['proposal'],
                          'candidates': len(record['candidate_proposals']), 'accepted': accepted,
                          'cpu_seconds': record['cpu_seconds']}), flush=True)
        if accepted:
            record.update(adjacency=rows, scc_sizes=components)
            save(target, record)
            print(json.dumps({'graph': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}), flush=True)
            return


def verify(path, draw, block=1_000_000):
    graph = json.loads(path.read_text())
    assert graph['algorithm'] == ALGORITHM
    generator = np.random.PCG64(graph['seed'])
    proposal = 0
    candidates = []
    while proposal < graph['proposal']:
        consumed, rows = draw(generator, graph['n'], min(block, graph['proposal'] - proposal))
        proposal += consumed
        if rows is not None:
            accepted, components = validate(rows, graph['n'], 2)
            candidates.append({'proposal': proposal, 'accepted': accepted})
            assert accepted == (proposal == graph['proposal'])
    assert rows == graph['adjacency'] and components == graph['scc_sizes']
    assert candidates == graph['candidate_proposals']
    assert generator.state == graph['rng_state']
    return {'repeat': graph['repeat'], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'proposal': graph['proposal'], 'scc_sizes': components, 'algorithm': ALGORITHM,
            'seeded_replay': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--n', type=int, default=128)
    parser.add_argument('--block', type=int, default=1_000_000)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    draw = engine(args.directory / 'build')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        if args.verify:
            futures = [pool.submit(verify, args.directory / f'graph-{repeat}.json', draw, args.block)
                       for repeat in (1, 2, 3)]
            for future in futures:
                print(json.dumps(future.result()), flush=True)
        else:
            futures = [pool.submit(sample, args.directory, repeat, args.n, draw, args.block)
                       for repeat in (1, 2, 3)]
            for future in futures:
                future.result()


if __name__ == '__main__':
    main()
