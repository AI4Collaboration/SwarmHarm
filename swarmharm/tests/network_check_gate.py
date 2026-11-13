"""Run a networked preparation check with cross-process host admission."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import runpy
import sys
import tempfile
import time

import launch_capacity


@contextmanager
def serialized(directory=None, timeout=600):
    directory = Path(directory or Path(tempfile.gettempdir()) /
                     f'swarmharm-test-networks-{os.getuid()}')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / 'network-check.lock').open('a+') as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Timed out waiting for another networked preparation check')
                time.sleep(min(1, max(0, deadline - time.monotonic())))
        yield


def admit(timeout=600):
    deadline = time.monotonic() + timeout
    while True:
        try:
            with launch_capacity.reserve(4) as register:
                register(os.getpid())
            return
        except RuntimeError as error:
            if not str(error).startswith('Host capacity occupied:') or time.monotonic() >= deadline:
                raise
            time.sleep(min(5, max(0, deadline - time.monotonic())))


def main(module):
    with serialized():
        admit()
        sys.argv = ['python -m unittest', module, '-v']
        runpy.run_module('unittest', run_name='__main__')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Expected one unittest module')
    main(sys.argv[1])
