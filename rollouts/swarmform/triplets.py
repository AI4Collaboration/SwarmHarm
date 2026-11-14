"""Shared input allocation for two matched task triplets."""

from copy import deepcopy
from hashlib import sha256
import json

from swarmform.population import research_actors, validate

VARIANTS = {
    "impossible": "impossible",
    "distributed": "information-dependent",
    "possible": "possible",
}


def encoded(value):
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def digest(value):
    return sha256(encoded(value).encode()).hexdigest()


def variant(key, family):
    value = key.removeprefix(family + "-")
    if key != family + "-" + value or value not in VARIANTS:
        raise ValueError("Unknown task triplet variant")
    return value


def allocate(common, groups, population, distributed):
    """Replicate fixed information shards when N exceeds the number of shards."""
    validate(population, minimum=2)
    actors = research_actors(population)
    width = min(population, len(groups))
    if width < 2:
        raise ValueError("Information dependence needs at least two source groups")
    startup = {}
    for index, actor in enumerate(actors):
        files = deepcopy(common)
        for number, group in enumerate(groups):
            if not distributed or number % width == index % width:
                files.update(deepcopy(group))
        startup[actor] = files
    return startup


def pooled(startup):
    files = {}
    for local in startup.values():
        for path, value in local.items():
            if path in files and files[path] != value:
                raise ValueError("Conflicting copies of an input file")
            files[path] = value
    return files
