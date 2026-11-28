"""Opt-in participant cutoff for new bounded SwarmForm collections only.

The container, its original sentinel, and root-owned strace observers survive.
Co-located business processors are participants for this boundary; independent
archive/job services keep their existing drain. Terminal state is cleanup state,
not proof of an output having existed at the nominal research deadline.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import secrets
import subprocess
import threading
import time


from swarmform.workstation import docker_workers

SENTINEL_ARGV = ['python', '-I', '-c', 'import time;time.sleep(172900)']

# The protected directory is root-owned under a sticky tmpfs. A business process
# can read this gate but cannot remove its directory, lock, or stop marker. The
# lock descriptor closes atomically on exec: a launch that passed the check is
# already a visible business process before the stopper takes the exclusive lock.
LAUNCH_GUARD = r'''
import fcntl,os,sys
from pathlib import Path
try:Path('/proc/self/oom_score_adj').write_text('800')
except OSError:pass
control=Path(sys.argv[1])
with (control/'launch.lock').open('rb') as lock:
    fcntl.flock(lock,fcntl.LOCK_SH)
    if sys.argv[2]=='--closed' or (control/'stopped').exists():
        print('The session has closed.',file=sys.stderr)
        raise SystemExit(125)
    os.execvp(sys.argv[3],sys.argv[3:])
'''

# Executed as root inside exactly the registered station. It has no capability to
# alter another container. UID changes for signalling match workstation_observer;
# pidfds bind signals to identities even if a numeric PID is reused.
CONTROL = r'''
import fcntl,json,os,signal,sys,time
from pathlib import Path
args=json.load(sys.stdin)
uid=args['uid'];control=Path(args['control'])
mount_namespace=os.readlink('/proc/self/ns/mnt') if args.get('account_view') else None
def info(pid):
    path=Path('/proc')/str(pid)
    fields=(path/'stat').read_text().rsplit(') ',1)[1].split()
    real_uid=int(next(line for line in (path/'status').read_text().splitlines() if line.startswith('Uid:')).split()[1])
    return {'pid':int(pid),'start_ticks':fields[19],'state':fields[0],'real_uid':real_uid,
        'parent':int(fields[1]),'uid':path.stat().st_uid,
        'name':(path/'comm').read_text().strip(),
        'argv':(path/'cmdline').read_bytes().rstrip(b'\0').decode(errors='surrogateescape').split('\0')}
def processes():
    result=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            owner=path.stat().st_uid
            if owner!=uid:
                if owner!=0 or (path/'comm').read_text().strip()!='strace':continue
                if mount_namespace and os.readlink(path/'ns/mnt')!=mount_namespace:continue
            result.append(info(path.name))
        except (FileNotFoundError,ProcessLookupError):pass
    return result
def identity(row):return row['pid'],row['start_ticks']
def signal_exact(row,sig):
    try:
        fd=os.pidfd_open(row['pid'])
        try:
            if identity(info(row['pid']))!=identity(row):return False
            caller=os.geteuid()
            try:
                if row['uid']!=caller:os.seteuid(row['uid'])
                signal.pidfd_send_signal(fd,sig)
            finally:
                if os.geteuid()!=caller:os.seteuid(caller)
        finally:os.close(fd)
        return True
    except (FileNotFoundError,ProcessLookupError):return False
def sentinel_valid():
    current=info(args['sentinel']['pid'])
    if (identity(current)!=identity(args['sentinel']) or current['uid']!=uid
            or current['argv']!=args['sentinel_argv'] or current['state'] in ('Z','X')):
        raise RuntimeError('Original workstation sentinel identity changed')
    return current
def targets(rows):
    # The root snapshot observer temporarily takes the subject's effective UID to signal it.
    return [r for r in rows if r['uid']==uid and r['real_uid']==uid and r['pid'] not in (1,os.getpid())
        and identity(r)!=identity(args['sentinel']) and r['state'] not in ('Z','X')]
def tracer(row):
    if row['uid']!=0 or row['name']!='strace':return False
    if not args.get('account_view'):return True
    try:return os.readlink(f"/proc/{row['pid']}/ns/mnt")==os.readlink('/proc/self/ns/mnt')
    except (FileNotFoundError,ProcessLookupError):return False
def sweep(rows,killed,resumed):
    # Resume only observer tracers: a concurrent snapshot may have stopped them.
    # Participant SIGKILL remains pending until a stopped tracer can process it.
    for row in rows:
        if tracer(row) and row['state']=='T':
            if signal_exact(row,signal.SIGCONT):resumed[identity(row)]=row
    for row in targets(rows):
        if signal_exact(row,signal.SIGKILL):killed[identity(row)]=row
if args['operation']=='arm':
    candidates=[r for r in processes() if r['uid']==uid and r['pid']!=1
        and r['argv']==args['sentinel_argv'] and r['state'] not in ('Z','X')]
    if len(candidates)!=1:raise RuntimeError('Expected exactly one original workstation sentinel')
    control.mkdir(mode=0o755)
    with (control/'launch.lock').open('xb') as stream:pass
    (control/'launch.lock').chmod(0o644)
    print(json.dumps({'sentinel':candidates[0],'control':str(control),
        'container_at_unix_ns':time.time_ns(),'container_monotonic_ns':time.monotonic_ns()}))
elif args['operation']=='stop':
    sentinel_valid()
    killed={};resumed={};began=time.monotonic();limit=began+args['timeout_seconds']
    # Set the immutable gate first; even a lock holder cannot admit later work.
    (control/'stopped').touch(exist_ok=True)
    with (control/'launch.lock').open('rb') as lock:
        while True:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                sweep(processes(),killed,resumed)
                if time.monotonic()>=limit:raise TimeoutError('Participant launch gate did not close')
                time.sleep(.005)
        while True:
            sentinel=sentinel_valid();rows=processes();sweep(rows,killed,resumed)
            remaining=targets(processes())
            tracers=[r for r in processes() if tracer(r) and r['state'] not in ('Z','X')]
            if not remaining and not tracers:break
            if time.monotonic()>=limit:break
            time.sleep(.005)
    print(json.dumps({'participants_stopped':not remaining,'remaining':remaining,
        'tracers_drained_at_check':not tracers,'remaining_tracers':tracers,
        'signalled':list(killed.values()),'resumed_observer_tracers':list(resumed.values()),
        'sentinel':sentinel,'container_at_unix_ns':time.time_ns(),
        'container_monotonic_ns':time.monotonic_ns(),'stop_seconds':time.monotonic()-began,
        'launch_gate_closed':True}))
else:raise ValueError('Unknown participant cutoff operation')
'''


def utc():
    return datetime.now(timezone.utc).isoformat()


def guarded_argv(argv, control, *, closed=False):
    """Preserve the trace envelope and replace only its ordinary command tail."""
    if len(argv)<6 or argv[-6:-1] != ['timeout','--kill-after=1s','30s','bash','-lc']:
        raise ValueError('Unrecognized workstation command envelope')
    return argv[:-6]+['python','-I','-c',LAUNCH_GUARD,str(control),'--closed' if closed else '--']+argv[-6:]


class ParticipantStop:
    """Arm before model prompts; stop independently of occupied actor locks.

    `arm()` raises before research on any invalid sentinel or workstation.
    `stop()` returns a receipt even on failure. The caller must retain that receipt
    and censor/error unless `research_stop_verified` is true. It must still drain
    tool futures, late native usage, strace and service evidence before removal.
    """
    def __init__(self, deployment, *, timeout_seconds=5):
        if not 0<timeout_seconds<=15:
            raise ValueError('Participant stopping allowance must be in (0, 15] seconds')
        self.deployment=deployment
        self.stations=dict(deployment.stations)
        self.timeout_seconds=timeout_seconds
        self.armed={}
        self.arm_receipt=None
        self.stopping=threading.Event()
        self._stop_lock=threading.Lock()
        self.receipt=None
        self.actor_requests={}
        self.actor_receipts={}
        self._actor_request_lock=threading.Lock()
        self._actor_stop_locks={a:threading.Lock() for a in self.stations}
        self._actor_closed={a:threading.Event() for a in self.stations}

    def _run(self, actor, operation):
        station=self.stations[actor]
        payload={'operation':operation,'uid':station.business_uid,
            'sentinel_argv':SENTINEL_ARGV,'control':self.controls[actor],
            'timeout_seconds':self.timeout_seconds,'account_view':bool(getattr(station,'account_view',()))}
        if operation=='stop':payload['sentinel']=self.armed[actor]['sentinel']
        try:
            result=subprocess.run(['docker','exec','-i','--user','0:0',station.name, *getattr(station,'account_view',()),
                'python','-I','-c',CONTROL],input=json.dumps(payload),text=True,
                capture_output=True,timeout=max(self.timeout_seconds+15, 30))
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(f'Participant cutoff {operation} timed out for {actor}') from error
        if result.returncode:
            raise RuntimeError('Participant cutoff '+operation+' failed: '+result.stderr[-2000:])
        return json.loads(result.stdout)

    def arm(self):
        if self.arm_receipt is not None:
            raise RuntimeError('Participant cutoff has already been armed')
        for actor,station in self.stations.items():
            if (station.process_lifecycle!='continuous' or not station.trace_commands
                    or not station.initialized or station.closed):
                raise ValueError('Participant cutoff requires initialized, observed continuous Docker stations')
        if not self.stations:raise ValueError('Participant cutoff requires stations')
        self.controls={a:'/private/tmp/.session-gate-'+secrets.token_hex(16) for a in self.stations}
        with ThreadPoolExecutor(max_workers=docker_workers(len(self.stations))) as pool:
            futures={a:pool.submit(self._run,a,'arm') for a in self.stations}
            for actor,future in futures.items():self.armed[actor]=future.result()
        for actor,station in self.stations.items():
            original=station.command_argv
            control=self.controls[actor]
            # Only these opt-in instances change; legacy instances and the class
            # method are untouched. Closures pin each original bound method.
            closed=self._actor_closed[actor]
            station.command_argv=lambda command,original=original,control=control,closed=closed: guarded_argv(
                original(command),control,closed=closed.is_set())
        self.arm_receipt={'schema':1,'at':utc(),'actors':self.armed,
            'scope':'Prospective bounded participant command gate; no prompt or task change.'}
        return self.arm_receipt

    def snapshot_idle(self, actor, snapshot):
        """Exclude only the original armed sentinel from a settled process snapshot."""
        sentinel = self.armed.get(actor, {}).get('sentinel')
        rows = snapshot.get('processes')
        if (not sentinel or sentinel.get('argv') != SENTINEL_ARGV
                or not isinstance(rows, list)):
            return False
        found = False
        for row in rows:
            if not isinstance(row, dict):
                return False
            exact = (all(row.get(k) == sentinel.get(k) and k in row and k in sentinel
                         for k in ('pid', 'start_ticks', 'uid', 'parent', 'name'))
                     and row.get('command') == ' '.join(sentinel['argv']) + ' ')
            if exact:
                if found or row.get('state') in (None, 'Z', 'X'):
                    return False
                found = True
            elif row.get('state') not in ('Z', 'X'):
                return False
        return found

    def _stop_actor(self,actor,deadline):
        requested=time.monotonic()
        value={'requested_at':utc(),'requested_monotonic':requested,
            'container':self.stations[actor].name}
        try:
            value.update(self._run(actor,'stop'))
        except Exception as error:
            value.update(participants_stopped=False,launch_gate_closed=False,
                error={'type':type(error).__name__,'message':str(error)})
        completed=time.monotonic()
        value.update(completed_at=utc(),completed_monotonic=completed,
            stop_boundary_monotonic_interval=[requested,completed],
            verified=value.get('participants_stopped') is True and value.get('launch_gate_closed') is True
                and value.get('tracers_drained_at_check') is True)
        if deadline is not None:
            value['nominal_deadline_lateness_upper_bound_seconds']=max(0,completed-deadline)
        binding=getattr(self.deployment,'bindings',{}).get(actor,{})
        colocated=bool(binding.get('startup_service_origin') or binding.get('startup_processor_origin'))
        value.update(colocated_supplied_processor_present=colocated,
            colocated_supplied_processor_stopped=value.get('participants_stopped') is True if colocated else None,
            colocated_service_drain='not_available_in_this_carrier' if colocated else 'not_applicable',
            inflight_colocated_service_requests_censored=colocated)
        return value

    def request_actor_stop(self, actor, *, reason, deadline_monotonic=None):
        """Close host launch admission immediately; preserve the first boundary.

        Existing argv/commands may already be in flight. Their physical cutoff is
        separately bracketed by stop_actor; this is not an instantaneous kill claim.
        No Docker call or workstation execution lock is acquired by this method.
        """
        if self.arm_receipt is None:raise RuntimeError('Participant cutoff is not armed')
        if actor not in self.stations:raise ValueError('Unknown participant')
        with self._actor_request_lock:
            if actor not in self.actor_requests:
                self.actor_requests[actor]={'reason':reason,
                    'nominal_deadline_monotonic':deadline_monotonic,
                    'admission_closed_monotonic':time.monotonic(),'admission_closed_at':utc()}
                self._actor_closed[actor].set()
            return dict(self.actor_requests[actor])

    def stop_actor(self, actor, *, reason, deadline_monotonic=None):
        """Stop one actor without touching peers; concurrent/global calls reuse it."""
        request=self.request_actor_stop(actor,reason=reason,deadline_monotonic=deadline_monotonic)
        with self._actor_stop_locks[actor]:
            if actor not in self.actor_receipts:
                row=self._stop_actor(actor,request['nominal_deadline_monotonic'])
                row.update(actor=actor,reason=request['reason'],request=request,
                    nominal_deadline_monotonic=request['nominal_deadline_monotonic'],
                    research_stop_verified=row['verified'])
                self.actor_receipts[actor]=row
            return self.actor_receipts[actor]

    def stop(self, *, reason, deadline_monotonic=None):
        self.stopping.set()
        with self._stop_lock:
            if self.receipt is not None:return self.receipt
            if self.arm_receipt is None:raise RuntimeError('Participant cutoff is not armed')
            requested=time.monotonic();at=utc()
            with ThreadPoolExecutor(max_workers=docker_workers(len(self.stations))) as pool:
                futures={a:pool.submit(self.stop_actor,a,reason=reason,deadline_monotonic=deadline_monotonic) for a in self.stations}
                actors={a:f.result() for a,f in futures.items()}
            self.receipt={'schema':1,'reason':reason,'requested_at':at,'requested_monotonic':requested,
                'completed_at':utc(),'completed_monotonic':time.monotonic(),
                'nominal_deadline_monotonic':deadline_monotonic,'actors':actors,
                'research_stop_verified':all(row['verified'] for row in actors.values()),
                'exact_nominal_deadline_stop_proven':False,
                'independent_service_drain':'existing_deployment_close' if hasattr(self.deployment,'service') else 'not_applicable',
                'outcome_scope':'Terminal snapshots are post-stop cleanup state. Nominal-deadline task success requires separately timestamped evidence.',
                'clock_scope':'Host monotonic brackets compare to the host deadline. Container monotonic values have a separate clock domain.',
                'late_evidence':'Drain all submitted tool futures, native usage, and service evidence after this stop.'}
            return self.receipt
