"""Reserve host capacity before starting a collector or making model calls."""
from collections import Counter
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile


DEFAULT_NETWORK_LIMIT = 16  # Four four-workstation rollouts on the default Docker host.


def managed_networks():
    ids = subprocess.check_output([
        'docker', 'network', 'ls', '--filter', 'label=org.swarmharm.managed=true',
        '--format', '{{.ID}}'], text=True, timeout=20).split()
    if not ids:
        return Counter()
    networks = json.loads(subprocess.check_output(
        ['docker', 'network', 'inspect', *ids], text=True, timeout=20))
    return Counter(str(row.get('Labels', {}).get('org.swarmharm.owner-pid', 'unknown'))
                   for row in networks)


def process_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def reserve(networks, *, directory=None):
    """Count live reservations and actual networks without double-counting owners.

    The lock spans admission and child registration, including the interval before
    Docker creates its first network. Nothing is removed from Docker here.
    """
    if networks < 1:
        raise ValueError('A collector must reserve at least one workstation network')
    limit = int(os.environ.get('SWARMHARM_MAX_WORKSTATION_NETWORKS', DEFAULT_NETWORK_LIMIT))
    if limit < 1:
        raise ValueError('SWARMHARM_MAX_WORKSTATION_NETWORKS must be positive')
    directory = Path(directory or Path(tempfile.gettempdir()) /
                     f'swarmharm-launch-{os.getuid()}')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    state = directory / 'reservations.json'
    with (directory / 'capacity.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        reservations = json.loads(state.read_text()) if state.exists() else {}
        reservations = {pid: count for pid, count in reservations.items() if process_alive(pid)}
        occupied = managed_networks()
        for pid, count in reservations.items():
            occupied[pid] = max(occupied[pid], count)
        if sum(occupied.values()) + networks > limit:
            raise RuntimeError(
                f'Host capacity occupied: {sum(occupied.values())}/{limit} '
                f'workstation networks; this rollout needs {networks}. '
                'Wait for a collector to finish, then launch this unstarted registration. '
                'No model request or trajectory has started.')

        def register(pid):
            reservations[str(pid)] = networks
            temporary = state.with_suffix('.tmp')
            temporary.write_text(json.dumps(reservations, sort_keys=True) + '\n')
            temporary.replace(state)

        yield register
