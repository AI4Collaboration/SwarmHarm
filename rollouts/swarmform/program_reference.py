"""Install a hash-bound execute-only reference, outside observed/public files."""
import base64
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

from workstation import IMAGE

PATH = '/opt/reference/jq'


def asset(path, *, expected_sha256=None):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    # Only registered native Linux ELF variants are supported. Their exact
    # hashes are bound by the task specification before collection.
    architectures = {62:'amd64', 183:'arm64'}
    if (len(raw) < 64 or raw[:6] != b'\x7fELF\x02\x01'
            or int.from_bytes(raw[18:20], 'little') not in architectures or len(raw) > 16_000_000):
        raise ValueError('Reference must be a bounded amd64 or ARM64 little-endian ELF')
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError('Reference program differs from its sealed hash')
    return {'path': str(path), 'sha256': digest, 'bytes': len(raw),
            'architecture': architectures[int.from_bytes(raw[18:20], 'little')], 'installed_path': PATH, 'mode': '0111'}


def validate(value):
    if not isinstance(value, dict) or set(value) != {
            'path', 'sha256', 'bytes', 'architecture', 'installed_path', 'mode'}:
        raise ValueError('Malformed reference-program registration')
    if (type(value['path']) is not str or not Path(value['path']).is_absolute()
            or type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['sha256'])
            or type(value['bytes']) is not int):
        raise ValueError('Malformed reference-program identity')
    if asset(value['path'], expected_sha256=value['sha256']) != value:
        raise ValueError('Reference program metadata differs')
    return True


def create_volume(value, resources):
    """The caller's ExitStack removes this volume after closing every station."""
    validate(value)
    raw = Path(value['path']).read_bytes()
    if sha256(raw).hexdigest() != value['sha256']:
        raise ValueError('Reference changed during installation')
    architecture = subprocess.check_output(
        ['docker','image','inspect',IMAGE,'--format','{{.Architecture}}'],text=True,timeout=15).strip()
    if architecture != value['architecture']:
        raise ValueError('Reference and workstation architecture differ; build the native reference')
    volume = 'office-reference-' + secrets.token_hex(8)
    subprocess.run(['docker', 'volume', 'create', '--label', 'org.swarmharm.managed=true',
                    '--label', f'org.swarmharm.owner-pid={os.getpid()}', volume],
                   check=True, capture_output=True, timeout=20)
    resources.callback(subprocess.run, ['docker', 'volume', 'rm', volume],
                       check=True, capture_output=True, timeout=20)
    code = '''import base64,hashlib,json,os,sys
from pathlib import Path
r=json.load(sys.stdin);raw=base64.b64decode(r['bytes'],validate=True)
assert hashlib.sha256(raw).hexdigest()==r['sha256']
p=Path('/opt/reference/jq')
with p.open('xb') as f:f.write(raw)
installed=hashlib.sha256(p.read_bytes()).hexdigest()
p.chmod(0o111);p.parent.chmod(0o555)
assert p.stat().st_uid==0 and p.parent.stat().st_uid==0
print(json.dumps({'sha256':installed,'mode':oct(p.stat().st_mode&0o777)}))
'''
    result = subprocess.run(['docker', 'run', '--rm', '-i', '--pull=never', '--network=none',
        '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
        '--memory=128m', '--pids-limit=32', '--user=0:0',
        '--mount', f'type=volume,src={volume},dst=/opt/reference',
        IMAGE, 'python', '-I', '-c', code],
        input=json.dumps({'bytes': base64.b64encode(raw).decode(), 'sha256': value['sha256']}),
        text=True, capture_output=True, check=True, timeout=30)
    if json.loads(result.stdout) != {'sha256': value['sha256'], 'mode': '0o111'}:
        raise RuntimeError('Reference installation differs from its contract')
    return volume


def verify_runtime(value):
    """Trace the exact reference in the selected workstation and identify its executor.

    The shell, Python, observer and reference must all be native. An emulator's
    debug options can expose an otherwise execute-only reference's instructions.
    This is an operator-only software check, before any participant starts.
    """
    code = r'''
from hashlib import sha256
from pathlib import Path
import json,os,platform,secrets,subprocess,time
reference=Path('/opt/reference/jq')
child=subprocess.Popen([str(reference),'.'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
try:
    executable=Path('/proc')/str(child.pid)/'exe'
    for _ in range(500):
        target=os.readlink(executable)
        if target==str(reference):break
        time.sleep(.01)
    else:raise RuntimeError('Reference executor did not become ready')
    executor_sha256=sha256(executable.read_bytes()).hexdigest()
    executor_version=subprocess.check_output([str(executable),'--version'],text=True,timeout=10).splitlines()[0]
    out,err=child.communicate(b'null\n',timeout=10)
    assert child.returncode==0 and out.strip()==b'null' and not err
finally:
    if child.poll() is None:child.kill();child.wait()
marker=secrets.token_hex(24)
source=Path('/tmp/swarmform-reference-probe.json')
source.write_text(json.dumps({'marker':marker}));source.chmod(0o644)
trace=Path('/tmp/swarmform-reference-probe.trace')
result=subprocess.run(['strace','-f','-yy','-s','4096','-e','trace=execve,openat,read',
    '-o',str(trace),'-u','65534:65534',str(reference),'-r','.marker',str(source)],
    capture_output=True,text=True,timeout=20)
if result.returncode or result.stdout.strip()!=marker or result.stderr:
    raise RuntimeError('Native reference tracing failed: '+result.stderr[-1500:])
raw=trace.read_bytes()
assert any('read(' in line and str(source) in line and marker in line
           for line in raw.decode().splitlines()),'Reference input read was not captured'
print(json.dumps({'workstation_architecture':platform.machine(),
    'executor_path':target,'executor_sha256':executor_sha256,'executor_version':executor_version,
    'strace_version':subprocess.check_output(['strace','--version'],text=True).splitlines()[0],
    'traced_reference_execution':True,'trace_sha256':sha256(raw).hexdigest()}))
'''
    with ExitStack() as resources:
        volume = create_volume(value, resources)
        result = subprocess.run(['docker','run','--rm','--pull=never','--network=none',
            '--read-only','--cap-drop=ALL','--cap-add=SYS_PTRACE','--cap-add=SETUID',
            '--cap-add=SETGID','--cap-add=DAC_READ_SEARCH','--security-opt=no-new-privileges',
            '--memory=512m','--cpus=1','--pids-limit=64',
            '--tmpfs','/tmp:rw,nosuid,nodev,size=32m,mode=1777',
            '--mount',f'type=volume,src={volume},dst=/opt/reference,readonly',
            IMAGE,'python','-I','-c',code],capture_output=True,text=True,timeout=45)
        if result.returncode:
            raise RuntimeError('SwarmForm needs a native workstation and matching native jq reference with working ptrace. '
                + result.stderr[-2000:])
        info = json.loads(result.stdout)
        info['reference_sha256'] = value['sha256']
        info['execution'] = 'native'
        if info['executor_sha256'] != value['sha256']:
            raise RuntimeError('The reference must execute natively; emulator execution is not admitted')
        return info
