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
spec=importlib.util.spec_from_file_location('launch_atomic_reader',REPO/'experiments/infra-reader-v1/reader.py');infra=importlib.util.module_from_spec(spec);spec.loader.exec_module(infra)

def launch(output, *, command=None):
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
        argv=command or [sys.executable,str(HERE/'run.py'),'--phase','collect','--output',str(root)]
        with (root/'controller.log').open('xb') as log:
            child=subprocess.Popen(argv,cwd=REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        infra.atomic_json(root/'launcher.json',{'at':infra.utc(),'pid':child.pid,'new_session':True,'scheduled_task':False,
                                             'same_prepared_collector':command is None,'registration_sha256':seal['sha256']})
    return child.pid

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    print(json.dumps({'pid':launch(a.output),'scheduled_task':False}),flush=True)
