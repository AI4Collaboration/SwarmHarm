"""Host reference for ranked tree comparisons and ancestral reconstruction."""

from functools import lru_cache
from itertools import combinations, permutations, product
from math import prod


def _agreement(left, right, rank):
    def flatten(root):
        children = {}
        def visit(node):
            label = node["label"]
            children[label] = tuple(child["label"] for child in node["children"])
            for child in node["children"]:
                visit(child)
        visit(root)
        return children

    a, b = flatten(left), flatten(right)
    labels = sorted({key for key, kids in a.items() if not kids}
                    & {key for key, kids in b.items() if not kids})
    bit = {label: 1 << i for i, label in enumerate(labels)}

    @lru_cache(None)
    def best(x, y):
        if not a[x] and not b[y]:
            return {bit[x]} if x == y else {0}
        # If one root becomes unary, every selected leaf lies in a single
        # child there. Otherwise their surviving child branches form a bijection.
        candidates = {0}
        for child in a[x]:
            candidates.update(best(child, y))
        for child in b[y]:
            candidates.update(best(x, child))
        for n in range(2, min(len(a[x]), len(b[y])) + 1):
            for lhs in combinations(a[x], n):
                for rhs in permutations(b[y], n):
                    blocks = [best(i, j) for i, j in zip(lhs, rhs)]
                    if all(0 not in block for block in blocks):
                        candidates.update(sum(selection) for selection in product(*blocks))
        size = max(mask.bit_count() for mask in candidates)
        return {mask for mask in candidates if mask.bit_count() == size}

    matches = best(left["label"], right["label"])
    size = next(iter(matches)).bit_count()
    selected = None
    if 0 <= rank < len(matches):
        groups = sorted(tuple(label for label in labels if mask & bit[label]) for mask in matches)
        selected = groups[rank]
    return {"size": size, "count": len(matches), "leaves": selected}


def _ancestry(root, model, rank):
    states, costs = model["states"], model["costs"]
    allowed = model["allowed"]
    labels = []

    def collect(node):
        labels.append(node["label"])
        for child in node["children"]:
            collect(child)

    collect(root)
    fixed = {}

    def minimum(pairs):
        pairs = list(pairs)
        best = min(cost for cost, _ in pairs)
        return best, sum(count for cost, count in pairs if cost == best)

    def table(node):
        label = node["label"]
        children = [table(child) for child in node["children"]]
        possible = [fixed[label]] if label in fixed else allowed.get(label, states)
        result = {}
        for state in possible:
            i = states.index(state)
            choices = [minimum((cost + costs[i][j], count) for j, (cost, count) in child.items())
                       for child in children]
            result[i] = sum(cost for cost, _ in choices), prod(count for _, count in choices)
        return result

    optimum, count = minimum(table(root).values())
    if 0 <= rank < count:
        for label in sorted(labels):
            for state in states:
                if state not in allowed.get(label, states):
                    continue
                fixed[label] = state
                cost, block = minimum(table(root).values())
                if cost == optimum:
                    if rank < block:
                        break
                    rank -= block
        assignment = fixed
    else:
        assignment = None
    return {"cost": optimum, "count": count, "assignment": assignment}
