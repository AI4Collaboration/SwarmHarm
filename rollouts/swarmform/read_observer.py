"""Protected command observations for the actual file-volume fixture."""

import base64
from hashlib import sha256
import json
from pathlib import Path
import re
import os
import secrets
import shutil
import ctypes
import platform
import subprocess
import time
from tempfile import TemporaryFile,NamedTemporaryFile
from collections.abc import Mapping

from atomic import atomic_json
from swarmform.file_deployment import FileStation
from workstation import IMAGE
from swarmform.strace_timing import FORMAT, HOST_CLOCK, current_command, legacy_line

TRACE_ROOT = '/var/log/workstation'
MAX_TRACE_BYTES=1024*1024*1024
MAX_ACTIVE_BYTES=2*1024*1024*1024


class ObservationStorageAllowanceExceeded(RuntimeError):
    """The complete captured bytes and receipt were retained before validation failed."""

    def __init__(self, receipt):
        super().__init__('Command observation reached its registered storage allowance')
        self.retained_receipt = receipt


READ_LOGS = r'''
import json,os,sys,time
from pathlib import Path
root=Path('/var/log/workstation')
opened=set()
for process in Path('/proc').iterdir():
    if not process.name.isdigit():continue
    try:
        for fd in (process/'fd').iterdir():
            try:opened.add(os.readlink(fd))
            except OSError:pass
    except OSError:pass
files=[]
for p in sorted(root.iterdir()):
    if p.is_file():
        stat=p.stat()
        files.append({'name':p.name,'bytes':stat.st_size,'device':stat.st_dev,'inode':stat.st_ino})
try:time_namespace=os.readlink('/proc/self/ns/time')
except OSError:time_namespace=None
clock={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
       'time_namespace':time_namespace,'implementation':time.get_clock_info('monotonic').implementation,
       'resolution_seconds':repr(time.get_clock_info('monotonic').resolution)}
header={'files':files,'closed':[item['name'] for item in files if str(root/item['name']) not in opened],
        'guest_clock':clock}
output=sys.stdout.buffer
output.write(json.dumps(header).encode()+b'\n')
for item in files:
    with (root/item['name']).open('rb') as stream:
        remaining=item['bytes']
        while remaining:
            data=stream.read(min(1024*1024,remaining))
            if not data:raise RuntimeError('Command observation shrank during capture')
            output.write(data);remaining-=len(data)
output.flush()
'''
PRUNE_LOGS = r'''
import hashlib,json
from pathlib import Path
for name,digest in json.load(__import__('sys').stdin).items():
    if Path(name).name!=name:raise ValueError('Invalid observation filename')
    p=Path('/var/log/workstation')/name
    with p.open('rb') as stream:
        actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=digest:raise ValueError('Closed observation changed')
    p.unlink()
'''


def clone_prefix(source,destination):
    """Use filesystem copy-on-write when available; preserve prior immutable blobs."""
    if platform.system()=='Darwin':
        library=ctypes.CDLL(None,use_errno=True)
        clone=library.clonefile;clone.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int];clone.restype=ctypes.c_int
        if clone(os.fsencode(source),os.fsencode(destination),0)==0:return True
    elif platform.system()=='Linux':
        import fcntl
        try:
            with source.open('rb') as original,destination.open('xb') as copy:
                fcntl.ioctl(copy.fileno(),0x40049409,original.fileno())
            return True
        except OSError:destination.unlink(missing_ok=True)
    return False


def observed_reads(log):
    """Extract complete scalar reads only; path presence alone never earns a read."""
    pattern = re.compile(r'^(\d+)\s+(\d+\.\d+)\s+(read|pread64)\(\d+<([^>]+)>, "((?:\\x[0-9a-f]{2})*)", (\d+)(?:, (\d+))?\) = (\d+)$')
    reads = []
    for number, line in enumerate(log.splitlines(), 1):
        match = pattern.fullmatch(legacy_line(line))
        if not match:
            continue
        pid, timestamp, operation, raw_path, raw_bytes, requested, offset, returned = match.groups()
        path = re.sub(r'\\x([0-9a-f]{2})', lambda m: chr(int(m[1], 16)), raw_path)
        data = bytes.fromhex(raw_bytes.replace('\\x', ''))
        if not path.startswith(('/workspace/', '/var/tmp/exports/', '/tmp/')) or len(data) != int(returned):
            continue
        reads.append({'line': number, 'pid': int(pid), 'at_unix': timestamp, 'operation': operation,
                      'path': path, 'requested_bytes': int(requested), 'returned_bytes': len(data),
                      'explicit_offset': int(offset) if offset is not None else None,
                      'data_base64': base64.b64encode(data).decode(), 'sha256': sha256(data).hexdigest()})
    return reads


class ObservedFileStation(FileStation):
    """The observer retains process reads; native traces still establish model exposure."""

    def __init__(self, initial_files, *, archive, **kwargs):
        self.configure_archive(archive)
        self.observation_volume='office-observation-'+secrets.token_hex(8)
        self.observation_volume_removed=False
        subprocess.run(['docker','volume','create','--label','org.swarmharm.managed=true',
                        '--label',f'org.swarmharm.owner-pid={os.getpid()}',self.observation_volume],
                       capture_output=True,check=True,timeout=20)
        try:
            subprocess.run(['docker','run','--rm','--pull=never','--network=none','--read-only',
                            '--cap-drop=ALL','--mount',f'type=volume,src={self.observation_volume},dst={TRACE_ROOT}',
                            IMAGE,'python','-I','-c',f'import os;os.chmod({TRACE_ROOT!r},0o700)'],
                           capture_output=True,check=True,timeout=20)
            super().__init__(initial_files,trace_commands=True,trace_volume=self.observation_volume,**kwargs)
        except BaseException:
            self.remove_observation_volume()
            raise
        try:
            self.observer_version = subprocess.check_output(
                ['docker', 'exec', self.name, 'strace', '--version'], text=True, timeout=10).splitlines()[0]
        except BaseException:
            self.close()
            raise

    def configure_archive(self, archive):
        self.archive = Path(archive).resolve()
        repo = Path(__file__).resolve().parents[2]
        if self.archive.is_relative_to(repo) or self.archive.exists():
            raise ValueError('Choose a new observation directory outside the repository')
        self.archive.mkdir(parents=True)
        self.command_count = self.capture_count = 0
        self.trace_files = {}
        self.trace_origins = {}
        self.observer_identity = secrets.token_hex(16)
        self.previous = ArchivedTraces(self.archive, self.trace_files)
        self.pruned = set()

    def command_argv(self, command):
        self.command_count += 1
        original_hash = sha256(command.encode()).hexdigest()
        if self.creation_mask:command='umask '+self.creation_mask+'\n'+command
        # This is before subprocess launch, in the collector's host process.
        # The immutable origin remains attached when a later command captures
        # this trace's still-running background descendants.
        if not hasattr(self, 'trace_origins'):
            self.trace_origins = {}
            self.observer_identity = secrets.token_hex(16)
        name = f'{self.command_count:06d}.log'
        self.trace_origins[name] = {
            'trace_id': self.observer_identity+':'+name,
            'command_ordinal': self.command_count, 'trace_file': name,
            'station': self.name, 'command_sha256': original_hash,
            'traced_shell_sha256': sha256(command.encode()).hexdigest(),
            'launch_before_ns': time.monotonic_ns(), 'host_clock_domain': HOST_CLOCK['domain'],
            'native_call': current_command() or None}
        return ['docker', 'exec', '--user', '0:0', '--workdir', '/workspace', self.name, *getattr(self, 'account_view', ()),
                'strace', '-DDD', '-f', '-ttt', '--relative-timestamps=ns', '-yy', '-s', '262144', '-xx',
                # Pathname Unix sockets can cross a shared volume even with
                # network=none. Keep their actual send/receive operations.
                '-e', 'trace=%file,%desc,%process,%memory,%network', '-e', 'abbrev=!getdents64',
                '-o', f'{TRACE_ROOT}/{self.command_count:06d}.log', '-u', f'{self.business_uid}:{self.business_gid}',
                'timeout', '--kill-after=1s', '30s', 'bash', '-lc', command]

    def remove_observation_volume(self):
        if not self.observation_volume_removed:
            subprocess.run(['docker','volume','rm',self.observation_volume],capture_output=True,check=True,timeout=20)
            self.observation_volume_removed=True

    def retain_traces(self):
        # Long-running services keep one trace open. Disk storage and bounded
        # host streaming preserve that history without using business RAM.
        blobs=self.archive/'blobs';blobs.mkdir(exist_ok=True)
        incomplete=[];seen=set();active_bytes=0;oversized=[]
        with TemporaryFile() as capture:
            capture_started_ns = time.monotonic_ns()
            subprocess.run(['docker','exec','--user','0:0',self.name,*getattr(self,'account_view',()),'python','-I','-c',READ_LOGS],
                           stdout=capture,stderr=subprocess.PIPE,check=True,timeout=60)
            capture_completed_ns = time.monotonic_ns()
            capture.seek(0);observed=json.loads(capture.readline(1024*1024))
            guest_clock = observed.get('guest_clock')
            guest_domain = sha256(json.dumps(guest_clock,sort_keys=True).encode()).hexdigest() if guest_clock else None
            for item in observed['files']:
                name,size=item['name'],item['bytes']
                if Path(name).name!=name or name in seen or not isinstance(size,int) or size<0:
                    raise RuntimeError('Invalid command observation header')
                seen.add(name)
                if name in self.pruned:raise RuntimeError('A closed command observation was reopened')
                prior=self.trace_files.get(name)
                if prior and size<prior['bytes']:raise RuntimeError('Command observation is no longer append-only')
                identity = {'device':item.get('device'),'inode':item.get('inode')}
                prior_identity = (prior or {}).get('timing',{}).get('file_identity')
                if prior_identity and prior_identity != identity:
                    raise RuntimeError('Command observation file identity changed')
                previous=(self.archive/prior['blob']).open('rb') if prior else None
                digest=sha256();last=b'';offset=0
                temporary=NamedTemporaryFile(dir=blobs,delete=False);temporary_name=Path(temporary.name);temporary.close();temporary_name.unlink()
                cloned=bool(prior and clone_prefix(self.archive/prior['blob'],temporary_name))
                try:
                    with temporary_name.open('r+b' if cloned else 'wb') as temporary:
                        while offset<size:
                            block=capture.read(min(1024*1024,size-offset))
                            if not block:raise RuntimeError('Command observation capture is incomplete')
                            if prior and offset<prior['bytes']:
                                count=min(len(block),prior['bytes']-offset)
                                if previous.read(count)!=block[:count]:raise RuntimeError('Command observation is no longer append-only')
                            digest.update(block)
                            skip=min(len(block),max(0,prior['bytes']-offset)) if cloned else 0
                            if skip<len(block):temporary.seek(offset+skip);temporary.write(block[skip:])
                            offset+=len(block);last=block[-1:]
                    if previous and previous.read(1):raise RuntimeError('Archived observation differs from its recorded length')
                    hexdigest=digest.hexdigest();destination=blobs/hexdigest
                    if destination.exists():temporary_name.unlink()
                    else:temporary_name.replace(destination)
                finally:
                    if previous:previous.close()
                    temporary_name.unlink(missing_ok=True)
                origin = getattr(self,'trace_origins',{}).get(name)
                timing = {'format':FORMAT, 'origin':origin, 'prefix_from_byte_zero':True,
                    'single_tracer':origin is not None, 'file_identity':identity,
                    'closed':name in observed['closed'],
                    'capture':{'sequence':self.capture_count+1,'started_ns':capture_started_ns,
                        'completed_ns':capture_completed_ns,'host_clock_domain':HOST_CLOCK['domain'],
                        'guest_clock_domain':guest_domain}}
                self.trace_files[name]={'bytes':size,'sha256':hexdigest,'blob':f'blobs/{hexdigest}',
                    'prefix_storage':'copy_on_write' if cloned else 'streamed','timing':timing}
                if name not in observed['closed']:active_bytes+=size
                elif size and last!=b'\n':incomplete.append(name)
                if size>MAX_TRACE_BYTES:oversized.append(name)
            if capture.read(1):raise RuntimeError('Unexpected bytes after command observation capture')
        if set(self.trace_files)-seen-self.pruned:raise RuntimeError('An unarchived command observation disappeared')
        self.capture_count+=1;files=dict(self.trace_files)
        exceeded=bool(oversized or active_bytes>MAX_ACTIVE_BYTES)
        record={'commands_started':self.command_count,'observer':getattr(self,'observer_version',None),
                'files':files,'claim_scope':'process_operations_not_model_comprehension','incomplete_closed_logs':incomplete,
                'timing_schema':1,'host_clock':HOST_CLOCK,'guest_clock':guest_clock,
                'storage':{'kind':'private_disk_volume','max_trace_bytes':MAX_TRACE_BYTES,'max_active_bytes':MAX_ACTIVE_BYTES,
                           'active_bytes':active_bytes,'oversized_logs':oversized,'allowance_exceeded':exceeded}}
        path=self.archive/f'{self.capture_count:06d}.json';atomic_json(path,record)
        if incomplete:raise RuntimeError('Closed command observation is truncated: '+','.join(incomplete))
        receipt={'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}
        if exceeded:raise ObservationStorageAllowanceExceeded(receipt)
        closed={name:files[name]['sha256'] for name in observed['closed']}
        if closed:
            subprocess.run(['docker','exec','-i','--user','0:0',self.name,*getattr(self,'account_view',()),'python','-I','-c',PRUNE_LOGS],
                           input=json.dumps(closed),text=True,capture_output=True,check=True,timeout=60)
            self.pruned.update(closed)
        return receipt

    def execute(self, command, shared):
        before = self.command_count
        result, snapshot = super().execute(command, shared)
        try:
            snapshot['command_observation'] = self.retain_traces()
        except ObservationStorageAllowanceExceeded as error:
            # Execution and complete capture succeeded. Keep the actual result
            # available to shutdown even when the controller closes admission
            # before handing it back to the native session.
            snapshot['command_observation'] = error.retained_receipt
            snapshot['observation_storage_limit'] = error.retained_receipt
            self.observation_allowance_reported = True
        snapshot['command_observation']['started_traces'] = [
            self.trace_origins[f'{n:06d}.log'] for n in range(before+1,self.command_count+1)]
        return result, snapshot

    def close(self):
        if self.closed and self.observation_volume_removed:
            return
        errors = []
        safe_to_remove = True
        # Preserve unarchived originals after an unknown capture failure.
        # A storage-limit verdict is different: retain_traces has already
        # verified and retained the complete capture before raising it.
        if not self.closed and self.initialized:
            try:
                self.capture_frozen('terminal')
            except BaseException as error:
                errors.append(error)
                safe_to_remove = False
            try:
                self.retain_traces()
            except ObservationStorageAllowanceExceeded as error:
                # A previously reported resource boundary is not a new cleanup
                # failure. Unknown capture and removal errors still propagate.
                if not getattr(self, 'observation_allowance_reported', False):
                    errors.append(error)
            except BaseException as error:
                errors.append(error)
                safe_to_remove = False
        if safe_to_remove and not self.closed:
            try:
                removed = subprocess.run(['docker', 'rm', '-f', self.name],
                                         capture_output=True, timeout=20)
                if removed.returncode and b'No such container' not in removed.stderr:
                    raise RuntimeError('Workstation removal unconfirmed')
                self.closed = True
            except BaseException as error:
                errors.append(error)
        if safe_to_remove:
            try:
                self.remove_observation_volume()
            except BaseException as error:
                errors.append(error)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise BaseExceptionGroup('Workstation capture and cleanup failures', errors)


class ArchivedTraces(Mapping):
    """Load an explicitly requested trace; closed logs need only their receipts in RAM."""
    def __init__(self, archive, files):
        self.archive, self.files = archive, files

    def __getitem__(self, name):
        record = self.files[name]
        data = (self.archive/record['blob']).read_bytes()
        if len(data) != record['bytes'] or sha256(data).hexdigest() != record['sha256']:
            raise RuntimeError('Archived command observation failed its integrity check')
        return data

    def __iter__(self):
        return iter(self.files)

    def __len__(self):
        return len(self.files)
