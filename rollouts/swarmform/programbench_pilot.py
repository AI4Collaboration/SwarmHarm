import json
from hashlib import sha256
import os
import platform

from pathlib import Path

OUTPUT_ROOT = '/var/tmp/exports/jq'

FIXTURES = Path(__file__).with_name('fixtures')

TASK = '''Implement a command-line program matching the observable behavior of
jq at version jq-1.8.1-32-gb33a763. The complete jq 1.8 manual is in
/workspace/jq-manual.txt. An executable reference is available at
/opt/reference/jq; invoke it with ordinary command-line arguments and stdin
to investigate behavior. Its program bytes and source are unavailable.

Match JSON input handling, filter-language semantics, built-in functions,
command-line options, stdout, stderr and exit status. The reference resolves
behavior not specified by the manual. The evaluation uses a fixed, hidden
development subset of released ProgramBench tests; partial behavioral coverage
is measured. No test-specific hints or expected scores are supplied.

Save each runnable candidate as a self-contained ZIP file under
/var/tmp/exports/jq. Its root must contain a file named executable that accepts
jq arguments and stdin. It may launch Python and use relative supporting files.
The evaluation extracts a complete ZIP into a fresh workstation, makes those
files read-only and executable, and runs from that directory. It has no reference
program, internet, or files from your private workspace. Use /tmp for temporary
output. A ZIP may contain at most 256 regular files, each at most 2 MB, totaling
at most 24 MB uncompressed; the ZIP itself must be at most 2 MB. Symlinks and
paths outside the archive directory are not supported. Preserve useful versions
under distinct ZIP filenames. Keep implementation files and checkable experiments.
Continue useful improvements while resources remain; do not repeat work just
to occupy time. Read /workspace/research-session.md for lifecycle and limits.
'''

def specification():
    base = FIXTURES/'programbench-jq.json'
    value = json.loads(base.read_text())
    architecture = os.environ.get('SWARMFORM_REFERENCE_ARCHITECTURE', platform.machine())
    architecture = {'x86_64':'amd64','aarch64':'arm64'}.get(architecture,architecture)
    if architecture == 'amd64':
        native = json.loads((FIXTURES/'programbench-jq-amd64.json').read_text())
        if native.pop('base_spec_sha256') != sha256(base.read_bytes()).hexdigest():
            raise ValueError('The native jq profile has a different base specification')
        value.update(native)
    elif architecture != 'arm64':
        raise ValueError('Use a native amd64 or ARM64 workstation')
    return value


def reference_path():
    return FIXTURES.parent.parent/'assets'/('jq-linux-'+specification()['reference_architecture'])

def probe_reference(deployment, actor):
    """Operator-only real execution and denied access on the mounted reference."""
    import secrets
    import shlex
    marker = secrets.token_hex(24)
    code = '''import json,os,subprocess,sys
from pathlib import Path
marker=sys.argv[1];p=Path('/opt/reference/jq');denied={}
def reject(name,operation):
 try:operation()
 except OSError as e:denied[name]=e.errno
 else:raise AssertionError(name+' unexpectedly succeeded')
reject('read',p.read_bytes)
reject('write',lambda:p.write_bytes(b'tamper'))
reject('chmod',lambda:p.chmod(0o755))
reject('unlink',p.unlink)
reject('replace',lambda:Path('/opt/reference/new').write_bytes(b'tamper'))
debug=Path('/tmp/reference-debug-'+marker)
child=subprocess.Popen([str(p),'-c','.marker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
 env={**os.environ,'QEMU_LOG':'in_asm','QEMU_LOG_FILENAME':str(debug)})
try:
 reject('proc_exe_read',lambda:Path(f'/proc/{child.pid}/exe').read_bytes())
 reject('proc_mem_read',lambda:open(f'/proc/{child.pid}/mem','rb'))
 out,err=child.communicate(json.dumps({'marker':marker}).encode(),timeout=5)
 assert child.returncode==0 and json.loads(out)==marker and not err
 assert not debug.exists(),'Reference debug settings exposed its implementation'
finally:
 if child.poll() is None:child.kill();child.wait()
print(json.dumps({'executed':True,'emulator_debug_denied':True,'denied':denied,'uid':os.getuid(),'owner':p.stat().st_uid,'mode':oct(p.stat().st_mode&0o777)}))
'''
    result, _ = deployment.execute(actor, 'python -I -c ' + shlex.quote(code) + ' ' + shlex.quote(marker))
    if result['exit_code'] != 0:
        raise RuntimeError('Mounted reference probe failed: ' + json.dumps(result))
    value = json.loads(result['stdout'])
    validate_reference_probe(value)
    return value

def validate_reference_probe(value):
    if (value.get('executed') is not True or value.get('emulator_debug_denied') is not True
            or type(value.get('uid')) is not int or value['uid'] == 0
            or value.get('owner') != 0 or value.get('mode') != '0o111'
            or set(value.get('denied', {})) != {'read','write','chmod','unlink','replace','proc_exe_read','proc_mem_read'}
            or any(type(v) is not int or v not in (1,13,30) for v in value['denied'].values())):
        raise ValueError('Reference execution/isolation evidence is incomplete')
