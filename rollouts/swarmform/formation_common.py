"""One Linux work environment with a shared project, and private per-account home views."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading

from swarmform.file_deployment import FileDeployment, EXPORTS, install_project_files
from swarmform.formation_inputs import PROJECT
from swarmform.participant_stop import ParticipantStop
from swarmform.population import account_ids
from swarmform.read_observer import ObservedFileStation
from swarmform.workstation import HYDRATE, IMAGE, WORKSTATION_PIDS, docker_workers, native_cwd_alias_code, remove_volume, remove_workstation


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
    def __init__(self, name, uid, pid, archive, sink, *, observer_version=None):
        self.name = name
        self.business_uid = self.business_gid = uid
        self.account_view = ['nsenter', f'--mount=/proc/{pid}/ns/mnt', '--wdns=/workspace', '--']
        self.creation_mask = None
        self.observation_roots = [EXPORTS]
        self.observation_settle_seconds = 10
        self.registry_enabled = False
        self.process_lifecycle = 'continuous'
        self.initialized = self.trace_commands = True
        self.closed = False
        self.observation_sink = sink
        self.configure_archive(archive)
        self.observer_version = observer_version or run(['docker', 'exec', name, 'strace', '--version']).splitlines()[0]

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
        self.capture_terminal()
        self.closed = True


class CommonWorkspace(FileDeployment):
    def __init__(self, startup, registration, *, observation_sink=None, observation_archive):
        self.freeform = registration.get('freeform', False)
        self.name = 'formation-team-' + secrets.token_hex(8)
        self.stations, self.bindings = {}, {}
        self.locks = {actor: threading.RLock() for actor in startup}
        self.resources = ExitStack()
        self.closed = False
        n = len(startup)
        if n < 2 or registration.get("population", n) != n:
            raise ValueError("Common workspace population differs from its inputs")
        volume = self.name + '-observations'
        label = ['--label', 'org.swarmform.managed=true', '--label', f'org.swarmform.owner-pid={os.getpid()}']
        try:
            security = json.loads(run(['docker', 'info', '--format', '{{json .SecurityOptions}}']))
            self.apparmor_mounts = any(option.split(',')[0] == 'name=apparmor' for option in (security or []))
            run(['docker', 'volume', 'create', *label, volume])
            self.resources.callback(remove_volume, volume)
            project_volume = self.name + '-project'
            run(['docker', 'volume', 'create', *label, project_volume])
            self.resources.callback(remove_volume, project_volume)
            try:
                run(self.container_args(n, label, volume))
            except subprocess.TimeoutExpired:
                remove_workstation(self.name)
                raise
            self.resources.callback(remove_workstation, self.name)
            ids = account_ids(n)
            root = ['docker', 'exec', '-i', self.name]
            mail = EXPORTS + '/messages'
            run([*root, 'mkdir', '-p', PROJECT, mail + '/all'])
            run([*root, 'chmod', '1777', mail + '/all', EXPORTS])
            # A freeform project is an editable worktree, including its seeded files.
            run([*root, 'chmod', '777' if self.freeform else '1777', PROJECT])
            run([*root, 'chmod', '755', mail])
            if registration.get('closed_mail_receipts'):
                run([*root, 'mkdir', '-m', '711', mail + '/.closed'])
            make_boxes = '''
import json, os, pathlib, sys
mail = pathlib.Path(sys.argv[1])
for actor, gid in json.load(sys.stdin):
    os.setegid(gid)
    folder = mail / actor
    folder.mkdir()
    folder.chmod(0o3773)
'''
            run([*root, 'python', '-I', '-c', make_boxes, mail], json.dumps(list(zip(startup, ids))))
            properties = json.loads(run(['docker', 'inspect', self.name]))[0]
            shared_obs_ver = run(['docker', 'exec', self.name, 'strace', '--version']).splitlines()[0]
            run([*root, 'mkdir', '-m', '700', *[f'/var/log/workstation/{uid}' for uid in ids]])
            def _setup_account(pair):
                (actor, files), uid = pair
                startup_log = f'/run/formation/setup-{uid}.log'
                run(['docker', 'exec', '-d', self.name, 'sh', '-c',
                     'log=$1; shift; exec "$@" >"$log" 2>&1', 'setup', startup_log,
                     'unshare', '--mount', '--propagation', 'private',
                     'sh', '-c', START_VIEW, 'setup', str(uid)])
                pid = run([*root, 'sh', '-ec', 'for i in $(seq 1 500); do if test -s "$1"; then cat "$1"; exit; fi; sleep .02; done; cat "$2" >&2 || true; exit 1',
                           'wait', f'/run/formation/{uid}/pid', startup_log])
                if not pid.isdigit():
                    raise RuntimeError('Missing account namespace owner')
                sink = (lambda phase, value, actor=actor: observation_sink(actor, phase, value)) if observation_sink else None
                station = AccountStation(self.name, uid, int(pid), Path(observation_archive)/actor, sink, observer_version=shared_obs_ver)
                payload = {path: base64.b64encode(content.encode()).decode() for path, content in files.items()}
                station.as_account(['python', '-I', '-c', HYDRATE], json.dumps({'files': payload}))
                binding = {'container': self.name, 'container_id': properties['Id'],
                           'user': str(uid), 'sentinel_pid': int(pid), 'image': properties['Image'],
                           'network': properties['HostConfig']['NetworkMode'], 'observation_volume': volume,
                           'apparmor_profile': properties.get('AppArmorProfile'),
                           'security_options': properties['HostConfig']['SecurityOpt'],
                           'read_only_rootfs': properties['HostConfig']['ReadonlyRootfs'],
                           'shared_project': PROJECT, 'observer_enabled': True}
                return actor, station, binding
            acct_pairs = list(zip(startup.items(), ids))
            if len(acct_pairs) >= 4:
                with ThreadPoolExecutor(max_workers=docker_workers(len(acct_pairs))) as pool:
                    built_accts = list(pool.map(_setup_account, acct_pairs))
            else:
                built_accts = [_setup_account(p) for p in acct_pairs]
            for actor, station, binding in built_accts:
                self.stations[actor] = station
                self.bindings[actor] = binding
            self.verify_access(startup, properties)
            if registration.get("project_artifacts"):
                install_project_files(self.name, registration["project_artifacts"])
        except BaseException:
            self.resources.close()
            raise

    def container_args(self, n, label, volume):
        apparmor = ['--security-opt=apparmor=unconfined'] if getattr(self, 'apparmor_mounts', False) else []
        return ['docker', 'run', '-d', '--rm', '--pull=never', '--name', self.name, *label,
                '--network=none', '--init', '--read-only', '--cap-drop=ALL', '--cap-add=SYS_ADMIN',
                '--cap-add=SYS_CHROOT', '--cap-add=SYS_PTRACE', '--cap-add=SETUID', '--cap-add=SETGID', '--cap-add=DAC_READ_SEARCH',
                '--security-opt=no-new-privileges', *apparmor, '--cpu-period=100000', f'--cpu-quota={100000*n}', f'--memory={512*n}m', f'--pids-limit={WORKSTATION_PIDS*n}',
                '-e', 'HOME=/workspace', '--mount', f'type=volume,src={volume},dst=/var/log/workstation',
                '--tmpfs', '/run/formation:rw,nosuid,nodev,size=1m,mode=0700',
                '--tmpfs', '/workspace:rw,nosuid,nodev,size=1m,mode=0700',
                '--tmpfs', '/private/tmp:rw,nosuid,nodev,size=1m,mode=0700',
                '--mount', f'type=volume,src={self.name}-project,dst={EXPORTS}',
                IMAGE, 'sleep', 'infinity']

    def verify_access(self, startup, properties):
        n = len(startup)
        conf = properties['HostConfig']
        if (conf['CpuPeriod'], conf['CpuQuota'], conf['Memory'], conf['PidsLimit']) != (100000, n*100000, n*512*2**20, n*WORKSTATION_PIDS):
            raise RuntimeError('Aggregate resource budget differs')
        nonce = secrets.token_hex(12)
        # Probe foreign sources as the participant, including a real intake record when present.
        pids = {actor: b['sentinel_pid'] for actor, b in self.bindings.items()}
        names = {actor: next((p for p in files if '/specs/' in p or '/calendars/' in p), '/workspace/task.md')
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
        def _write_probe(item):
            actor, station = item
            content = secrets.token_hex(20)
            p_file = f'{PROJECT}/.probe-{nonce}-{actor}'
            m_file = f'{EXPORTS}/messages/all/.probe-{nonce}-{actor}'
            station.as_account(['python', '-I', '-c',
                                'from pathlib import Path;import sys;d=sys.stdin.read();Path(sys.argv[1]).write_text(d);Path(sys.argv[2]).write_text(d)',
                                p_file, m_file], content)
            digest_val = sha256(content.encode()).hexdigest()
            return p_file, m_file, digest_val
        st_items = list(self.stations.items())
        workers = docker_workers(len(st_items))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for p_file, m_file, d_val in pool.map(_write_probe, st_items):
                project[p_file] = d_val
                messages[m_file] = d_val
            all_startup_paths = set().union(*startup.values()) if self.freeform else set()
            def _check_probe(item):
                actor, station = item
                foreign = [f'/proc/{pid}/root{names[a]}' for a, pid in pids.items() if a != actor]
                expected = {p: sha256(v.encode()).hexdigest() for p,v in startup[actor].items()}
                missing = None
                if self.freeform:
                    missing = sorted(all_startup_paths - startup[actor].keys())
                    station.as_account(['python','-I','-c',
                                        'from pathlib import Path;import json,sys;assert not any(Path(p).exists() for p in json.load(sys.stdin))'],
                                       json.dumps(missing))
                row = json.loads(station.as_account(['python','-I','-c',probe], json.dumps(
                    {'private': foreign, 'own': list(expected), 'messages': list(messages), 'project': list(project)})))
                if (row['denied'] != foreign or row['installed'] != expected
                        or row['messages'] != messages or row['project'] != project):
                    raise RuntimeError('Shared/private control failed for '+actor)
                return actor, expected, row, missing
            for actor, expected, row, missing in pool.map(_check_probe, st_items):
                if missing is not None:
                    self.bindings[actor]['absent_foreign_opening_paths'] = missing
                self.bindings[actor].update(initial_materials_verified=True, startup_sha256=expected, access_control=row)
        for key in ('pid_ns', 'net_ns', 'ipc_ns', 'mnt_ns'):
            count = len({r['access_control'][key] for r in self.bindings.values()})
            if count != (n if key == 'mnt_ns' else 1):
                raise RuntimeError('Common workspace namespace verification failed: '+key)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda item: item[1].as_account(
                ['rm', f'{PROJECT}/.probe-{nonce}-{item[0]}', f'{EXPORTS}/messages/all/.probe-{nonce}-{item[0]}']), st_items))
        if run(['docker','exec',self.name,'find',PROJECT,EXPORTS+'/messages','-type','f']):
            raise RuntimeError('Control artifacts remain in the initial shared workspace')

    def mark_mail_session_closed(self, actor):
        if actor not in self.stations:
            raise KeyError(actor)
        run(['docker', 'exec', self.name, 'touch', f'{EXPORTS}/messages/.closed/{actor}'])

    def deliver(self, actor, batch, files):
        if batch != 'opening' or files or actor not in self.stations:
            raise ValueError('Expected the matched empty opening arrival')
        return {}

    def close(self):
        if not self.closed:
            self.capture_terminal()
            self.resources.close()
            for station in self.stations.values():
                station.closed = True
            self.closed = True
