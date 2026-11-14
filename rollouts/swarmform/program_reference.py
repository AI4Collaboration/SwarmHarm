"""Install a hash-bound execute-only reference, outside observed/public files."""
import base64
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
    # This implementation deliberately supports the verified native ARM ELF,
    # not arbitrary host executables or a download at deployment time.
    if (len(raw) < 64 or raw[:6] != b'\x7fELF\x02\x01'
            or int.from_bytes(raw[18:20], 'little') != 183 or len(raw) > 16_000_000):
        raise ValueError('Reference must be a bounded ARM64 little-endian ELF')
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError('Reference program differs from its sealed hash')
    return {'path': str(path), 'sha256': digest, 'bytes': len(raw),
            'architecture': 'arm64', 'installed_path': PATH, 'mode': '0111'}


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
        ['docker', 'image', 'inspect', IMAGE, '--format', '{{.Architecture}}'],
        text=True, timeout=15).strip()
    if architecture != value['architecture']:
        raise ValueError('Reference and workstation architecture differ')
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
