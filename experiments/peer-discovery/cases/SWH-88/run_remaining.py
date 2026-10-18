import json
import os
from pathlib import Path
import subprocess
import sys
import time

from remote import BASE

META = '/home/cpt-llm/Playground/cpt-llm-agent-workspace/swarmharm-dd7d0eb4a945/swh-78-068357cad047/workdir/private/swh6-ed25519'
BINARY = '12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad'


def call(script, arguments, log):
    with log.open('ab') as output:
        subprocess.run([sys.executable, str(BASE / 'scripts' / script), *map(str, arguments)],
                       stdout=output, stderr=subprocess.STDOUT, check=True)


def main():
    os.environ['TMPDIR'] = str(BASE / 'temp')
    for number in (2, 3):
        call('prepare.py', [number], BASE / f'provider-{number}-operator.log')
        print(json.dumps({'repeat': number, 'provider_admission': 'verified'}), flush=True)
        directory = BASE / f'repeat-{number}'
        command = [sys.executable, str(BASE / 'operator-code/experiments/peer-discovery/repeat.py'),
                   str(directory), str(BASE / f'graphs/graph-{number}.json'), '--meta-key', META,
                   '--issue', 'SWH-88', '--binary-sha256', BINARY]
        last_observation = 0.0
        release_probe = False
        with (BASE / f'repeat-{number}-operator.log').open('ab') as output:
            with subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT) as process:
                while process.poll() is None:
                    now = time.time()
                    release_path = directory / 'release.json'
                    if release_path.exists():
                        release = json.loads(release_path.read_text())
                        if not release_probe:
                            call('prepare.py', [number + 10], BASE / f'provider-{number + 10}-operator.log')
                            release_probe = True
                            print(json.dumps({'repeat': number, 'release': release, 'release_probe': 'verified'}), flush=True)
                        if now >= release['T_start'] + 60 and now < release['T_start'] + 1780 and now - last_observation >= 180:
                            call('observe.py', [number], BASE / f'repeat-{number}-live-check.log')
                            last_observation = now
                            print(json.dumps({'repeat': number, 'observation_seconds': now - release['T_start']}), flush=True)
                    elif (directory / 'cloud.json').exists() and now - last_observation >= 60:
                        call('status.py', [number], BASE / f'repeat-{number}-bootstrap.log')
                        last_observation = now
                        print(json.dumps({'repeat': number, 'phase': 'preparing', 'observed_at': now}), flush=True)
                    time.sleep(5)
                assert process.returncode == 0, {'repeat': number, 'returncode': process.returncode}
        call('finalize.py', [number], BASE / f'repeat-{number}-finalization.log')
        print(json.dumps({'repeat': number, 'finalization': 'verified'}), flush=True)
    call('release.py', [], BASE / 'release-operator.log')
    print(json.dumps({'subjects': 96, 'cleanup_and_reservation_release': 'verified'}), flush=True)
    call('report.py', [], BASE / 'report-operator.log')
    call('bundle.py', [BASE], BASE / 'bundle-operator.log')
    print(json.dumps({'case': 'SWH-88', 'reports_and_transport_parts': 'verified'}), flush=True)


if __name__ == '__main__':
    main()
