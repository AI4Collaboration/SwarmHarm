"""Persistent workstations using actual shared or private volumes."""
from swarmform.population import account_ids

import base64
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import secrets
import subprocess
import threading
import time

from workstation import DockerWorkstation, IMAGE

EXPORTS = '/var/tmp/exports'
WORKSTATION_ENVIRONMENT = {'HOME': '/workspace'}

# Source deliveries run while this station's processes are quiescent. Do not follow
# a worker-created link or overwrite a modified previous delivery.
INSTALL = r'''
import base64,hashlib,json,os,sys,traceback
from pathlib import Path
def failure(kind,error,tb):
    record={'stage':'intake_install','exception':kind.__name__,
            'errno':getattr(error,'errno',None),'message':str(error)}
    try:
        fs=os.statvfs('/workspace')
        record['filesystem']={'path':'/workspace','capacity_bytes':fs.f_blocks*fs.f_frsize,
            'used_bytes':(fs.f_blocks-fs.f_bfree)*fs.f_frsize,
            'available_bytes':fs.f_bavail*fs.f_frsize,'block_bytes':fs.f_frsize,
            'capacity_inodes':fs.f_files,'available_inodes':fs.f_favail}
    except OSError as extra:record['filesystem_probe_error']=str(extra)
    print('SWARMFORM_INTAKE_FAILURE '+json.dumps(record),file=sys.stderr)
    traceback.print_exception(kind,error,tb)
sys.excepthook=failure
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
        with temp.open('xb') as stream:
            prepared.append((temp,p))
            stream.write(data)
    for temp,p in prepared:temp.replace(p)
finally:
    for temp,p in prepared:temp.unlink(missing_ok=True)
print(json.dumps({relative:hashlib.sha256((Path('/workspace')/relative).read_bytes()).hexdigest() for relative in files}))
'''


class IntakeDeliveryError(subprocess.CalledProcessError):
    """Retain the installer's exact diagnostics instead of only its command."""
    def __init__(self, error):
        super().__init__(error.returncode, error.cmd, output=error.stdout, stderr=error.stderr)
        self.diagnostic = {'returncode':error.returncode,
                           'stdout':error.stdout or '', 'stderr':error.stderr or ''}
        for line in self.diagnostic['stderr'].splitlines():
            if line.startswith('SWARMFORM_INTAKE_FAILURE '):
                try:
                    value=json.loads(line.removeprefix('SWARMFORM_INTAKE_FAILURE '))
                    if isinstance(value,dict):self.diagnostic['installer']=value
                except ValueError:pass

    def __str__(self):
        return 'Private source installation failed: '+json.dumps(
            self.diagnostic.get('installer',{'returncode':self.returncode}))

    def __repr__(self):
        return type(self).__name__+'('+repr(str(self))+')'


def intake_capacity_limit(diagnostic):
    """Only operator-measured ENOSPC qualifies; transport/permission faults do not."""
    failure = diagnostic.get('installer', {}) if isinstance(diagnostic, dict) else {}
    if not isinstance(failure, dict):return None
    fs = failure.get('filesystem', {})
    if not isinstance(fs, dict):return None
    if (failure.get('stage') != 'intake_install' or failure.get('errno') != 28
            or fs.get('path') != '/workspace'):
        return None
    names = ('capacity_bytes','used_bytes','available_bytes','block_bytes',
             'capacity_inodes','available_inodes')
    if any(type(fs.get(k)) is not int or fs[k] < 0 for k in names):return None
    if (fs['capacity_bytes'] <= 0 or fs['block_bytes'] <= 0
            or fs['used_bytes'] > fs['capacity_bytes']
            or fs['available_bytes'] > fs['capacity_bytes']
            or fs['available_inodes'] > fs['capacity_inodes']):return None
    if fs['available_bytes'] < fs['block_bytes']:
        return {'metric':'workspace_bytes','observed':fs['used_bytes'],'limit':fs['capacity_bytes']}
    if fs['capacity_inodes'] and fs['available_inodes'] == 0:
        return {'metric':'workspace_inodes','observed':fs['capacity_inodes'],'limit':fs['capacity_inodes']}
    return None


class FileStation(DockerWorkstation):
    def prepare_continuous_command(self, shared):
        if shared:
            raise ValueError('This deployment uses a live volume, not boundary synchronization')
        return None, [], []


class FileDeployment:
    """Own only resources created by this fixture; historical workstations are untouched."""

    def __init__(self, startup, *, shared=True, observation_sink=None, observation_archive=None, profile='content', population=3, observation_settle_seconds=2, ipc_mode=None):
        if profile not in ('content','metadata','state','events','timing'):
            raise ValueError('Unknown file access profile')
        self.profile=profile
        if type(population) is not int or population < 1 or len(startup) != population:
            raise ValueError('The workstation count differs from the registered population')
        self.population = population
        business_ids = account_ids(population)
        self.stations, self.volumes = {}, {}
        self.locks = {actor: threading.RLock() for actor in startup}
        self.resources = ExitStack()
        self.closed = False
        self.ipc_mode = ipc_mode
        try:
            common = self._volume() if shared else None
            for account_index,(actor,files) in enumerate(startup.items()):
                volume = common if common else self._volume()
                self.volumes[actor] = volume
                sink = (lambda phase, values, actor=actor: observation_sink(actor, phase, values)) if observation_sink else None
                station_class, extra = FileStation, {}
                if ipc_mode is not None:
                    extra['ipc_mode'] = ipc_mode
                if observation_archive is not None:
                    from swarmform.read_observer import ObservedFileStation
                    station_class = ObservedFileStation
                    extra['archive'] = Path(observation_archive)/actor
                station = station_class({path: base64.b64encode(text.encode()).decode() for path, text in files.items()},
                    process_lifecycle='continuous', observation_sink=sink,
                    observation_settle_seconds=observation_settle_seconds,
                    environment=WORKSTATION_ENVIRONMENT,
                    registry_enabled=False,
                    business_uid=business_ids[account_index] if profile!='content' else 65534,
                    business_gid=(63000 if profile in ('state','events','timing')
                                  else business_ids[account_index]) if profile!='content' else 65534,
                    creation_mask={'metadata':'0077','state':'0047','events':'0027','timing':'0007'}.get(profile),
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

    def _remove_volume(self, name):
        if any(not station.closed and self.volumes.get(actor) == name
               for actor, station in self.stations.items()):
            return
        subprocess.run(['docker', 'volume', 'rm', name], check=True, capture_output=True, timeout=20)

    def inspect_bindings(self, shared):
        result = {}
        for actor, station in self.stations.items():
            row = json.loads(subprocess.check_output(['docker', 'inspect', station.name], timeout=15))[0]
            mounts = [m for m in row['Mounts'] if m['Destination'] == EXPORTS]
            if (len(mounts) != 1 or mounts[0]['Name'] != self.volumes[actor] or not mounts[0]['RW']
                    or row['HostConfig']['NetworkMode'] != 'none' or row['Config']['User'] != f'{station.business_uid}:{station.business_gid}'
                    or 'HOME=/workspace' not in row['Config']['Env']):
                raise RuntimeError('Workstation differs from its declared mount or isolation')
            if getattr(self, "ipc_mode", None) is not None and row['HostConfig']['IpcMode'] != self.ipc_mode:
                raise RuntimeError('Workstation differs from its declared memory namespace')
            observation_mounts = [m for m in row['Mounts'] if m['Destination'] == '/var/log/workstation']
            if station.trace_commands and (len(observation_mounts) != 1
                    or observation_mounts[0]['Name'] != station.observation_volume):
                raise RuntimeError('Private observation volume differs')
            result[actor] = {'container': station.name,
                             'observation_volume': station.observation_volume if station.trace_commands else None,
                             'volume': mounts[0]['Name'], 'destination': EXPORTS,
                             'network': 'none', 'user': row['Config']['User'], 'image': row['Image'],
                             'environment': dict(WORKSTATION_ENVIRONMENT),'access_profile':self.profile, 'creation_mask':station.creation_mask,
                             'observer_enabled': station.trace_commands,
                             'observation_settle_seconds':station.observation_settle_seconds,
                             'container_cap_add': row['HostConfig']['CapAdd'],
                             'container_cap_drop': row['HostConfig']['CapDrop']}
        if len({v['volume'] for v in result.values()}) != (1 if shared else self.population):
            raise RuntimeError('Shared/private volume scope differs')
        return result

    def execute(self, actor, command):
        requested = time.monotonic()
        with self.locks[actor]:
            acquired = time.monotonic()
            result, snapshot = self.stations[actor].execute(command, {})
            snapshot['workstation_service_timing'] = {'lock_requested': requested,
                'lock_acquired': acquired, 'service_finished': time.monotonic(),
                'scope': 'Workstation service includes command execution and evidence capture.'}
            return result, snapshot

    def deliver(self, actor, batch, files):
        if any(not path.startswith(f'intake/{batch}/') for path in files):
            raise ValueError('Arrival files differ from the stated batch')
        with self.locks[actor]:
            station = self.stations[actor]
            before = station.capture_frozen('before_intake')
            try:
                payload = {path: base64.b64encode(text.encode()).decode() for path, text in files.items()}
                try:
                    result = subprocess.run(['docker', 'exec', '-i', station.name, 'python', '-I', '-c', INSTALL],
                        input=json.dumps(payload), text=True, capture_output=True, check=True, timeout=20)
                except subprocess.CalledProcessError as error:
                    raise IntakeDeliveryError(error) from error
                return json.loads(result.stdout)
            finally:
                station.resume_captured(before)

    def capture_terminal(self):
        errors = []
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(self.stations)))) as pool:
            futures = [pool.submit(station.capture_terminal)
                       for station in self.stations.values() if hasattr(station, 'capture_terminal')]
            for future in futures:
                try:
                    future.result()
                except BaseException as error:
                    errors.append(error)
        if errors:
            raise BaseExceptionGroup('Observation capture failed; cohort resources retained', errors)

    def close(self):
        if not self.closed:
            self.capture_terminal()
            self.resources.close()
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
