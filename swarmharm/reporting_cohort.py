"""Identities and participant count for a single reporting environment."""
from functools import lru_cache

DEFAULT_POPULATION = 3
BASE_ACCOUNTS = ('Northline', 'Aster', 'Meridian', 'Harbor')
PHYSICISTS = (
    'curie', 'faraday', 'maxwell', 'noether', 'meitner', 'bohr', 'wu', 'dirac',
    'bell', 'fermi', 'planck', 'einstein', 'raman', 'yukawa', 'becquerel', 'volta',
    'boltzmann', 'hertz', 'ampere', 'fourier', 'franck', 'gell-mann', 'pauli', 'feynman',
    'de-broglie', 'barnes', 'rubin', 'chandrasekhar', 'hawking', 'tesla', 'born', 'bose',
)


def validate_size(n):
    if type(n) is not int or n < 2:
        raise ValueError('A multi-agent reporting population must be an integer of at least 2')
    return n


def actor_ids(n):
    validate_size(n)
    names = []
    for i in range(n):
        group, position = divmod(i, len(PHYSICISTS))
        name = PHYSICISTS[position]
        names.append(f'job-{name}-{group+1}' if group else f'job-{name}')
    return tuple(names)


@lru_cache(maxsize=32)
def accounts(n):
    validate_size(n)
    return BASE_ACCOUNTS[:n] + tuple(f'Region-{i:03d}' for i in range(5, n+1))


def assigned_accounts(assignment):
    return accounts(assignment.get('population', len(BASE_ACCOUNTS)))
