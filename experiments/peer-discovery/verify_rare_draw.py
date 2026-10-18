import argparse
import itertools
import json
from pathlib import Path

import numpy as np

from rare_graphs import engine


def reference(generator, n, limit):
    interface = generator.ctypes
    bound = (n - 1) * (n - 2)
    threshold = 2**32 % bound
    for proposal in range(1, limit + 1):
        rows = []
        for own in range(n):
            value = interface.next_uint32(interface.state)
            while value < threshold:
                value = interface.next_uint32(interface.state)
            first, second = divmod(value % bound, n - 2)
            second += second >= first
            rows.append([first + (first >= own), second + (second >= own)])
        if len(set(itertools.chain.from_iterable(rows))) >= n - 1:
            return proposal, rows
    return limit, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    draw = engine(args.directory / 'build')
    checked = 0
    for n in (3, 4, 16, 64, 128):
        for seed in range(10):
            compiled = np.random.PCG64(seed)
            interpreted = np.random.PCG64(seed)
            assert draw(compiled, n, 1000) == reference(interpreted, n, 1000)
            assert compiled.state == interpreted.state
            checked += 1
        for own in range(n):
            counts = {}
            for choice in range((n - 1) * (n - 2)):
                first, second = divmod(choice, n - 2)
                second += second >= first
                pair = tuple(sorted((first + (first >= own), second + (second >= own))))
                assert own not in pair and pair[0] != pair[1]
                counts[pair] = counts.get(pair, 0) + 1
            assert len(counts) == (n - 1) * (n - 2) // 2
            assert set(counts.values()) == {2}
    generator = np.random.PCG64(113)
    state = generator.state
    first = draw(generator, 128, 10000)
    final_state = generator.state
    generator.state = state
    assert draw(generator, 128, 10000) == first
    assert generator.state == final_state
    generator.state = state
    consumed, rows = draw(generator, 128, 5000)
    assert consumed == 5000 and rows is None
    consumed, rows = draw(generator, 128, 5000)
    assert consumed == 5000 and rows is None
    assert generator.state == final_state
    print(json.dumps({'compiled_reference_agreements': checked, 'uniform_pair_enumeration': True,
                      'checkpoint_resume': True, 'numpy': np.__version__}))


if __name__ == '__main__':
    main()
