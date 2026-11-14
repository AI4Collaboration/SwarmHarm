"""One Linux work environment with a shared project, and private per-account home views."""
import base64
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading

from swarmform.file_deployment import FileDeployment, EXPORTS
from swarmform.formation_inputs import PROJECT
from swarmform.participant_stop import ParticipantStop
from swarmform.population import account_ids
from swarmform.read_observer import ObservedFileStation
from workstation import HYDRATE, IMAGE, native_cwd_alias_code


def run(argv, data=None):
    result = subprocess.run(argv, input=data, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(f"Common workspace operation failed ({result.returncode}): {result.stderr[-1500:]}")
    return result.stdout.strip()


# Only operator processes set up mounts. All worker commands use an unprivileged
# UID. PID, IPC, network and container identities are shared across the cohort.
START_VIEW = r'''
set -eu
uid=$1
home=/run/formation/$uid
mkdir -m 700 "$home"
for spec in "/workspace:32m" "/tmp:32m" "/private/tmp:1m"; do
    dest=${spec%:*}
    size=${spec#*:}
    mount -t tmpfs -o "size=$size,nosuid,nodev,mode=1777" tmpfs "$dest"
done
mount --bind "/var/log/workstation/$uid" /var/log/workstation
echo $$ > "$home/pid"
exec setpriv --reuid="$uid" --regid="$uid" --clear-groups --no-new-privs python -I -c 'import time;time.sleep(172900)'
'''


class AccountStation(ObservedFileStation):
    def __init__(self, name, uid, pid, archive, sink):
        self.name = name
        self.business_uid = self.business_gid = uid
        self.account_view = ['nsenter', f'--mount=/proc/{pid}/ns/mnt', '--wdns=/workspace', '--']
        self.creation_mask = None
        self.observation_roots = [EXPORTS]
        self.observation_settle_seconds = 2
        self.registry_enabled = False
        self.process_lifecycle = 'continuous'
        self.initialized = self.trace_commands = True
        self.closed = False
        self.observation_sink = sink
        self.configure_archive(archive)
        self.observer_version = run(['docker', 'exec', name, 'strace', '--version']).splitlines()[0]

    def as_account(self, argv, data=None):
        return run(['docker', 'exec', '-i', self.name, *self.account_view, 'setpriv',
                    f'--reuid={self.business_uid}', f'--regid={self.business_gid}',
                    '--clear-groups', '--no-new-privs', *argv], data)

    def bind_native_cwd(self, path):
        self.as_account(['python', '-I', '-c', native_cwd_alias_code(path)])
        self.native_cwd = path

    def close(self):
        if self.closed:
            return
        self.capture_frozen('terminal')
        self.retain_traces()
        self.closed = True


class CommonWorkspace(FileDeployment):
    def __init__(self, startup, registration, *, observation_sink=None, observation_archive):
        self.name = 'formation-team-' + secrets.token_hex(8)
        self.stations, self.bindings = {}, {}
        self.locks = {actor: threading.RLock() for actor in startup}
        self.resources = ExitStack()
        self.closed = False
        n = len(startup)
        if n < 2 or registration.get("population", n) != n:
            raise ValueError("Common workspace population differs from its inputs")
        volume = self.name + '-observations'
        label = ['--label', 'org.swarmharm.managed=true', '--label', f'org.swarmharm.owner-pid={os.getpid()}']
        try:
            run(['docker', 'volume', 'create', *label, volume])
            self.resources.callback(run, ['docker', 'volume', 'rm', volume])
            options = []
            if registration.get('reference_program'):
                from swarmform.program_reference import create_volume
                ref = create_volume(registration['reference_program'], self.resources)
                options = ['--mount', f'type=volume,src={ref},dst=/opt/reference,readonly']
            project_volume = self.name + '-project'
            run(['docker', 'volume', 'create', *label, project_volume])
            self.resources.callback(run, ['docker', 'volume', 'rm', project_volume])
            run(self.container_args(n, label, options, volume))
            self.resources.callback(run, ['docker', 'rm', '-f', self.name])
            ids = account_ids(n)
            root = ['docker', 'exec', self.name]
            run([*root, 'mkdir', '-p', PROJECT, EXPORTS + '/messages'])
            run([*root, 'chmod', '1777', PROJECT, EXPORTS + '/messages', EXPORTS])
            properties = json.loads(run(['docker', 'inspect', self.name]))[0]
            for (actor, files), uid in zip(startup.items(), ids):
                run([*root, 'mkdir', '-m', '700', f'/var/log/workstation/{uid}'])
                run(['docker', 'exec', '-d', self.name, 'unshare', '--mount', '--propagation', 'private',
                     'sh', '-c', START_VIEW, 'setup', str(uid)])
                pid = run([*root, 'sh', '-ec', 'for i in $(seq 1 200); do if test -s "$1"; then cat "$1"; exit; fi; sleep .02; done; exit 1',
                           'wait', f'/run/formation/{uid}/pid'])
                if not pid.isdigit():
                    raise RuntimeError('Missing account namespace owner')
                sink = (lambda phase, value, actor=actor: observation_sink(actor, phase, value)) if observation_sink else None
                station = AccountStation(self.name, uid, int(pid), Path(observation_archive)/actor, sink)
                self.stations[actor] = station
                payload = {path: base64.b64encode(content.encode()).decode() for path, content in files.items()}
                station.as_account(['python', '-I', '-c', HYDRATE], json.dumps({'files': payload}))
                self.bindings[actor] = {'container': self.name, 'container_id': properties['Id'],
                    'user': str(uid), 'sentinel_pid': int(pid), 'image': properties['Image'],
                    'network': properties['HostConfig']['NetworkMode'], 'observation_volume': volume,
                    'shared_project': PROJECT, 'observer_enabled': True}
            self.verify_access(startup, properties)
            if registration.get('reference_program'):
                from swarmform.programbench_pilot import probe_reference
                for actor in self.stations:
                    self.bindings[actor]['reference_probe'] = probe_reference(self, actor)
        except BaseException:
            self.resources.close()
            raise

    def container_args(self, n, label, options, volume):
        return ['docker', 'run', '-d', '--rm', '--pull=never', '--name', self.name, *label,
                '--network=none', '--init', '--read-only', '--cap-drop=ALL', '--cap-add=SYS_ADMIN',
                '--cap-add=SYS_CHROOT', '--cap-add=SYS_PTRACE', '--cap-add=SETUID', '--cap-add=SETGID', '--cap-add=DAC_READ_SEARCH',
                '--security-opt=no-new-privileges', f'--cpus={n}', f'--memory={512*n}m', f'--pids-limit={64*n}',
                '-e', 'HOME=/workspace', '--mount', f'type=volume,src={volume},dst=/var/log/workstation',
                '--tmpfs', '/run/formation:rw,nosuid,nodev,size=1m,mode=0700',
                '--tmpfs', '/workspace:rw,nosuid,nodev,size=1m,mode=0700',
                '--tmpfs', '/private/tmp:rw,nosuid,nodev,size=1m,mode=0700',
                '--mount', f'type=volume,src={self.name}-project,dst={EXPORTS}',
                *options, IMAGE, 'sleep', 'infinity']

    def verify_access(self, startup, properties):
        n = len(startup)
        conf = properties['HostConfig']
        if (conf['NanoCpus'], conf['Memory'], conf['PidsLimit']) != (n*10**9, n*512*2**20, n*64):
            raise RuntimeError('Aggregate resource budget differs')
        nonce = secrets.token_hex(12)
        # Probe foreign sources as the participant, including a real intake record when present.
        pids = {actor: b['sentinel_pid'] for actor, b in self.bindings.items()}
        names = {actor: next((p for p in files if '/intake/' in p), '/workspace/task.md')
                 for actor, files in startup.items()}
        probe = """
import hashlib,json,os,pathlib,sys
p=pathlib.Path
spec=json.load(sys.stdin)
def digest(path):return hashlib.sha256(p(path).read_bytes()).hexdigest()
caps=[l for l in p('/proc/self/status').read_text().splitlines() if l.startswith(('CapEff:','CapPrm:','NoNewPrivs:'))]
assert all(int(l.split()[1],16)==0 for l in caps if l.startswith('Cap')) and 'NoNewPrivs:\\t1' in caps
denied=[]
for foreign in spec['private']:
    try: p(foreign).read_bytes()
    except PermissionError: denied.append(foreign)
    else: raise ValueError('Foreign opening source was readable')
print(json.dumps({'installed':{f:digest(f) for f in spec['own']},'denied':denied,'caps':caps,
 'messages':{f:digest(f) for f in spec['messages']},'project':{f:digest(f) for f in spec['project']},
 'pid_ns':os.readlink('/proc/self/ns/pid'),'net_ns':os.readlink('/proc/self/ns/net'),
 'ipc_ns':os.readlink('/proc/self/ns/ipc'),'mnt_ns':os.readlink('/proc/self/ns/mnt')}))
"""
        project, messages = {}, {}
        for actor, station in self.stations.items():
            content = secrets.token_hex(20)
            for base, inventory in ((PROJECT, project), (EXPORTS+'/messages', messages)):
                filename = f'{base}/.probe-{nonce}-{actor}'
                station.as_account(['python', '-I', '-c', 'from pathlib import Path;import sys;Path(sys.argv[1]).write_text(sys.stdin.read())', filename], content)
                inventory[filename] = sha256(content.encode()).hexdigest()
        for actor, station in self.stations.items():
            foreign = [f'/proc/{pid}/root{names[a]}' for a, pid in pids.items() if a != actor]
            expected = {p: sha256(v.encode()).hexdigest() for p,v in startup[actor].items()}
            row = json.loads(station.as_account(['python','-I','-c',probe], json.dumps(
                {'private': foreign, 'own': list(expected), 'messages': list(messages), 'project': list(project)})))
            if (row['denied'] != foreign or row['installed'] != expected
                    or row['messages'] != messages or row['project'] != project):
                raise RuntimeError('Shared/private control failed for '+actor)
            self.bindings[actor].update(initial_materials_verified=True, startup_sha256=expected, access_control=row)
        for key in ('pid_ns', 'net_ns', 'ipc_ns', 'mnt_ns'):
            count = len({r['access_control'][key] for r in self.bindings.values()})
            if count != (n if key == 'mnt_ns' else 1):
                raise RuntimeError('Common workspace namespace verification failed: '+key)
        for actor, station in self.stations.items():
            station.as_account(['rm', f'{PROJECT}/.probe-{nonce}-{actor}', f'{EXPORTS}/messages/.probe-{nonce}-{actor}'])
        if run(['docker','exec',self.name,'find',PROJECT,EXPORTS+'/messages','-mindepth','1']):
            raise RuntimeError('Control artifacts remain in the initial shared workspace')

    def deliver(self, actor, batch, files):
        if batch != 'opening' or files or actor not in self.stations:
            raise ValueError('Expected the matched empty opening arrival')
        return {}

    def close(self):
        if not self.closed:
            try:
                for station in self.stations.values():
                    station.close()
            finally:
                self.resources.close()
                self.closed = True
