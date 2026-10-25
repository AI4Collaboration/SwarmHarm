"""Launch one prepared collector independently of the chat-tool process group."""
import argparse
import fcntl
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
spec=importlib.util.spec_from_file_location('launch_atomic_reader',REPO/'experiments/runtime/atomic.py');infra=importlib.util.module_from_spec(spec);spec.loader.exec_module(infra)

def collector_python():
    candidate=REPO.parent/'eval-readiness/harbor-0.24.0/bin/python'
    executable=str(candidate if candidate.is_file() else Path(sys.executable))
    check=subprocess.run([executable,'-c','import tomllib; from harbor.models.task.config import TaskConfig'],
        capture_output=True,text=True,timeout=20)
    if check.returncode!=0:raise RuntimeError('Collector runtime must provide Python 3.11+ and Harbor 0.24.0')
    return executable

def collector_command(root,registration_dir,key_file=None):
    argv=[collector_python(),str(HERE/'run.py'),'--phase','collect','--output',str(Path(root).resolve()),
          '--registration-dir',str(Path(registration_dir).resolve())]
    if key_file is not None:argv+=['--key-file',str(Path(key_file).resolve())]
    return argv

def launch(output, registration_dir, *, key_file=None, command=None):
    root=Path(output).resolve()
    reg=json.loads((root/'registration.json').read_text())
    seal=json.loads((root/'registration-seal.json').read_text())
    assert sha256((root/'registration.json').read_bytes()).hexdigest()==seal['sha256'],'Registration differs.'
    for path,digest in reg['code_hashes'].items():
        assert sha256((REPO/path).read_bytes()).hexdigest()==digest,path
        assert sha256((root/'code'/path).read_bytes()).hexdigest()==digest,path
    with (root/'.launch.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not (root/'started.json').exists() and not (root/'launcher.json').exists(),'Use a new prepared world; never replace trajectories.'
        argv=command or collector_command(root,registration_dir,key_file)
        with (root/'controller.log').open('xb') as log:
            child=subprocess.Popen(argv,cwd=REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        infra.atomic_json(root/'launcher.json',{'at':infra.utc(),'pid':child.pid,'new_session':True,'scheduled_task':False,
                                             'same_prepared_collector':command is None,'registration_sha256':seal['sha256']})
    return child.pid

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--registration-dir',type=Path,required=True)
    parser.add_argument('--key-file',type=Path,help='Existing host-only AxonHub key file; never copied into the study.')
    a=parser.parse_args();print(json.dumps({'pid':launch(a.output,a.registration_dir,key_file=a.key_file),'scheduled_task':False}),flush=True)
