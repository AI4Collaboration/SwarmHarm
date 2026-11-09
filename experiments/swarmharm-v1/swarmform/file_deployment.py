"""Three continuously running workstations using actual shared or private volumes."""

import base64
from contextlib import ExitStack
import json
from pathlib import Path
import secrets
import subprocess
import threading

from workstation import DockerWorkstation, IMAGE

EXPORTS = '/var/tmp/exports'
WORKSTATION_ENVIRONMENT = {'HOME': '/workspace'}

# Source deliveries run while this station's processes are quiescent. Do not follow
# a worker-created link or overwrite a modified previous delivery.
INSTALL = r'''
import base64,hashlib,json,os
from pathlib import Path
files=json.load(__import__('sys').stdin)
pending=[]
for relative,content in files.items():
    p=Path('/workspace')/relative
    if not relative.startswith('intake/') or '..' in Path(relative).parts:
        raise ValueError('Invalid intake path')
    for parent in reversed(p.parents):
        if str(parent) in ('/','/workspace'):continue
        if parent.is_symlink():raise ValueError('Intake directory is a link')
        parent.mkdir(exist_ok=True)
    data=base64.b64decode(content,validate=True)
    if p.is_symlink():raise ValueError('Intake file is a link')
    if p.exists():
        if not p.is_file() or p.read_bytes()!=data:raise ValueError('Intake file already has different content')
        continue
    pending.append((p,data))
prepared=[]
try:
    for p,data in pending:
        temp=p.with_name('.'+p.name+'.delivery')
        with temp.open('xb') as stream:stream.write(data)
        prepared.append((temp,p))
    for temp,p in prepared:temp.replace(p)
finally:
    for temp,p in prepared:temp.unlink(missing_ok=True)
print(json.dumps({relative:hashlib.sha256((Path('/workspace')/relative).read_bytes()).hexdigest() for relative in files}))
'''


class FileStation(DockerWorkstation):
    def prepare_continuous_command(self, shared):
        if shared:
            raise ValueError('This deployment uses a live volume, not boundary synchronization')
        before = self.capture_frozen('before_command')
        # The snapshot is quiescent; the next command must run alongside the
        # existing business processes, including worker-created services.
        self.resume_captured(before)
        return before, [], []


class FileDeployment:
    """Own only resources created by this fixture; historical workstations are untouched."""

    def __init__(self, startup, *, shared=True, observation_sink=None, observation_archive=None):
        if len(startup) != 3:
            raise ValueError('The matched SwarmForm input requires three stations')
        self.stations, self.volumes = {}, {}
        self.locks = {actor: threading.RLock() for actor in startup}
        self.resources = ExitStack()
        self.closed = False
        try:
            common = self._volume() if shared else None
            for actor, files in startup.items():
                volume = common if common else self._volume()
                self.volumes[actor] = volume
                sink = (lambda phase, values, actor=actor: observation_sink(actor, phase, values)) if observation_sink else None
                station_class, extra = FileStation, {}
                if observation_archive is not None:
                    from swarmform.read_observer import ObservedFileStation
                    station_class = ObservedFileStation
                    extra = {'archive': Path(observation_archive)/actor}
                station = station_class({path: base64.b64encode(text.encode()).decode() for path, text in files.items()},
                    process_lifecycle='continuous', observation_sink=sink,
                    environment=WORKSTATION_ENVIRONMENT,
                    named_volumes=((volume, EXPORTS),), **extra)
                self.resources.callback(station.close)
                self.stations[actor] = station
            self.bindings = self.inspect_bindings(shared)
        except BaseException:
            self.close()
            raise

    def _volume(self):
        name = 'office-' + secrets.token_hex(8)
        subprocess.run(['docker', 'volume', 'create', '--label', 'org.swarmharm.managed=true', name],
                       check=True, capture_output=True, timeout=20)
        self.resources.callback(self._remove_volume, name)
        subprocess.run(['docker', 'run', '--rm', '--pull=never', '--network=none', '--read-only',
                        '--cap-drop=ALL', '--mount', f'type=volume,src={name},dst={EXPORTS}',
                        IMAGE, 'python', '-I', '-c', f'import os; os.chmod({EXPORTS!r}, 0o1777)'],
                       check=True, capture_output=True, timeout=20)
        return name

    @staticmethod
    def _remove_volume(name):
        subprocess.run(['docker', 'volume', 'rm', name], check=True, capture_output=True, timeout=20)

    def inspect_bindings(self, shared):
        result = {}
        for actor, station in self.stations.items():
            row = json.loads(subprocess.check_output(['docker', 'inspect', station.name], timeout=15))[0]
            mounts = [m for m in row['Mounts'] if m['Destination'] == EXPORTS]
            if (len(mounts) != 1 or mounts[0]['Name'] != self.volumes[actor] or not mounts[0]['RW']
                    or row['HostConfig']['NetworkMode'] != 'none' or row['Config']['User'] != '65534:65534'
                    or 'HOME=/workspace' not in row['Config']['Env']):
                raise RuntimeError('Workstation differs from its declared mount or isolation')
            result[actor] = {'volume': mounts[0]['Name'], 'destination': EXPORTS,
                             'network': 'none', 'user': row['Config']['User'], 'image': row['Image'],
                             'environment': dict(WORKSTATION_ENVIRONMENT),
                             'observer_enabled': station.trace_commands,
                             'container_cap_add': row['HostConfig']['CapAdd'],
                             'container_cap_drop': row['HostConfig']['CapDrop']}
        if len({v['volume'] for v in result.values()}) != (1 if shared else 3):
            raise RuntimeError('Shared/private volume scope differs')
        return result

    def execute(self, actor, command):
        with self.locks[actor]:
            return self.stations[actor].execute(command, {})

    def deliver(self, actor, batch, files):
        if any(not path.startswith(f'intake/{batch}/') for path in files):
            raise ValueError('Arrival files differ from the stated batch')
        with self.locks[actor]:
            station = self.stations[actor]
            before = station.capture_frozen('before_intake')
            try:
                payload = {path: base64.b64encode(text.encode()).decode() for path, text in files.items()}
                result = subprocess.run(['docker', 'exec', '-i', station.name, 'python', '-I', '-c', INSTALL],
                    input=json.dumps(payload), text=True, capture_output=True, check=True, timeout=20)
                return json.loads(result.stdout)
            finally:
                station.resume_captured(before)

    def close(self):
        if not self.closed:
            self.resources.close()
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
