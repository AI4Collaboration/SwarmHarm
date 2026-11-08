#!/usr/bin/env python3
"""Check exact observed file bytes and observer access using no model calls."""
import argparse
import base64
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'experiments/runtime'), str(ROOT/'experiments/swarmharm-v1')]
from swarmform.read_observer import ObservedFileStation, observed_reads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    station = ObservedFileStation({'/workspace/source.txt': base64.b64encode(b'booked quantity 37\n').decode()},
                                  archive=args.output, process_lifecycle='continuous')
    try:
        result, _ = station.execute('id -u; cat /workspace/source.txt; cat /proc/self/status | rg CapEff', {})
        if result['exit_code'] or '65534' not in result['stdout'] or '0000000000000000' not in result['stdout']:
            raise RuntimeError(f'Business process identity changed: {result}')
        result, _ = station.execute('cat /var/log/workstation/000001.log', {})
        if result['exit_code'] == 0:
            raise RuntimeError('Business process could read observer files')
        script = "import time,pathlib; time.sleep(.3); pathlib.Path('/tmp/received.txt').write_text(pathlib.Path('/workspace/source.txt').read_text())"
        result, _ = station.execute('python -c '+shlex.quote(script)+' </dev/null >/tmp/process.log 2>&1 &', {})
        background_command = station.command_count
        if result['exit_code']:
            raise RuntimeError(result['stderr'])
        time.sleep(.5)
        result, snapshot = station.execute('cat /tmp/received.txt', {})
        if result['stdout'] != 'booked quantity 37\n':
            raise RuntimeError('Background process did not survive its initiating command')
        reads = observed_reads(station.previous[f'{background_command:06d}.log'].decode())
        if not any(row['path'] == '/workspace/source.txt' and base64.b64decode(row['data_base64']) == b'booked quantity 37\n' for row in reads):
            raise RuntimeError('Actual read bytes are absent from command observations')
        result, _ = station.execute('ls /workspace/source.txt', {})
        listed = observed_reads(station.previous[f'{station.command_count:06d}.log'].decode())
        if any(row['path'] == '/workspace/source.txt' for row in listed):
            raise RuntimeError('A listing was incorrectly counted as a content read')
        if not station.pruned:
            raise RuntimeError('Completed observations were not archived out of the workstation')
        counter = "import pathlib,time\np=pathlib.Path('/tmp/counter')\ni=0\nwhile True:\n i+=1\n p.write_text(str(i))\n time.sleep(.02)"
        station.execute('python -c '+shlex.quote(counter)+' </dev/null >/tmp/counter.log 2>&1 &', {})
        time.sleep(.1)
        frozen = station.capture_frozen('counter_check')
        def count():
            return subprocess.check_output(['docker', 'exec', station.name, 'cat', '/tmp/counter'], timeout=5)
        try:
            before = count()
            time.sleep(.2)
            if count() != before:
                raise RuntimeError('A traced background process changed during a frozen observation')
        finally:
            station.resume_captured(frozen)
        time.sleep(.1)
        if count() == before:
            raise RuntimeError('A traced background process did not resume after observation')
        print(json.dumps({'passed': True, 'model_calls': 0, 'observer': station.observer_version,
                          'commands': station.command_count, 'output': str(args.output.resolve()),
                          'background_read_captured': True, 'quiescent_capture_and_resume': True,
                          'unprivileged_business_process': True}))
    finally:
        station.close()


if __name__ == '__main__':
    main()
