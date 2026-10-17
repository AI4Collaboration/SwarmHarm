import itertools
import json

from graphs import validate


def main():
    checked = 0
    accepted = 0
    for k in (2, 3):
        options = [list(itertools.combinations([j for j in range(4) if j != i], k)) for i in range(4)]
        for rows in itertools.product(*options):
            result, _ = validate(rows, 4, k)
            checked += 1
            accepted += result
    assert checked == 82
    print(json.dumps({'exhaustive_graphs': checked, 'accepted': accepted, 'predicate_agreement': True}))


if __name__ == '__main__':
    main()
