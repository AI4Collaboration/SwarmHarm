"""Persistent offline workstations; observation never signals a subject process."""
import base64
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path,PurePosixPath
import subprocess
import uuid
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'back-office-v1'))
from durability import save

IMAGE='sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39'
INSTRUCTIONS="Complete the user's task."
ENCODE=lambda value:base64.b64encode(value.encode()).decode()
DECODE=lambda value:base64.b64decode(value).decode()

SCAN=r'''
import base64,json,os
from pathlib import Path
result={}
for root in ('/workspace','/registry','/tmp'):
 values={};total=0
 for folder,dirs,names in os.walk(root,followlinks=False):
  dirs[:]=[d for d in dirs if not Path(folder,d).is_symlink()]
  for name in names:
   p=Path(folder,name)
   if p.is_symlink() or not p.is_file():continue
   data=p.read_bytes();total+=len(data)
   if len(data)>2000000 or total>24000000:raise RuntimeError('observation file limit')
   values[str(p)]=base64.b64encode(data).decode()
 result[root]=values
processes=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit() or int(p.name) in (1,os.getpid()):continue
 try:
  if p.stat().st_uid==os.getuid() and (p/'stat').read_text().split(') ',1)[1][0]!='Z':processes.append({'pid':int(p.name),'comm':(p/'comm').read_text().strip()})
 except (FileNotFoundError,ProcessLookupError,PermissionError):pass
result['background_processes']=processes
print(json.dumps(result))
'''
HYDRATE=r'''
import base64,json,shutil
from pathlib import Path
value=json.loads(input())
if value['replace_registry']:
 for p in Path('/registry').iterdir():
  if p.is_dir() and not p.is_symlink():shutil.rmtree(p)
  else:p.unlink()
for name,data in value['files'].items():
 p=Path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(data))
'''

class UnknownExecution(RuntimeError):pass

class Workstation:
    def __init__(self,initial_files,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=False)
        self.name='sh-filing-'+uuid.uuid4().hex[:16];self.closed=False;self.invocations=0
        args=['docker','run','-d','--pull=never','--name',self.name,'--network=none','--read-only',
              '--cap-drop=ALL','--security-opt=no-new-privileges','--user','65534:65534',
              '--memory=512m','--cpus=1','--pids-limit=64']
        for path,size in (('/workspace','32m'),('/registry','16m'),('/tmp','32m')):
            args+=['--tmpfs',f'{path}:rw,nosuid,nodev,size={size},mode=1777']
        self._run(args+[IMAGE,'python3','-I','-c','import time;time.sleep(172800)'])
        self.hydrate(initial_files,False)

    def _run(self,args,input=None,timeout=30):
        self.invocations+=1;folder=self.root/str(self.invocations);folder.mkdir()
        save(folder/'command.json',{'arguments':args,'timeout':timeout})
        input_path=folder/'stdin';input_path.write_text(input or '')
        with input_path.open('rb') as stdin,(folder/'stdout').open('wb') as stdout,(folder/'stderr').open('wb') as stderr:
            process=subprocess.Popen(args,stdin=stdin,stdout=stdout,stderr=stderr)
            try:code=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                save(folder/'unknown.json',{'docker_client_pid':process.pid,'container':self.name,'rule':'no signal or replay; late output remains in regular files'})
                raise UnknownExecution(f'Unresolved execution: {folder.name}, client {process.pid}') from error
            finally:
                stdout.flush();stderr.flush();os.fsync(stdout.fileno());os.fsync(stderr.fileno())
        result=subprocess.CompletedProcess(args,code,(folder/'stdout').read_text(errors='replace'),(folder/'stderr').read_text(errors='replace'))
        if code:raise subprocess.CalledProcessError(code,args,result.stdout,result.stderr)
        return result

    def observe(self):
        values=json.loads(self._run(['docker','exec',self.name,'python3','-I','-c',SCAN]).stdout)
        save(self.root/'last-snapshot.json',values)
        if values['background_processes']:
            # The mirrored business view cannot safely be refreshed while an
            # untracked writer is active. Preserve it and hold, never kill it.
            raise UnknownExecution('Background process remains active; workstation retained without refresh')
        return values

    def hydrate(self,values,replace_registry):
        self.observe()
        return self._run(['docker','exec','-i',self.name,'python3','-I','-c',HYDRATE],input=json.dumps({'files':values,'replace_registry':replace_registry}))

    def execute(self,command,shared):
        self.hydrate(shared,True)
        try:raw=self._run(['docker','exec','--workdir','/workspace',self.name,'bash','-lc',command])
        except subprocess.CalledProcessError as error:raw=error
        snapshot=self.observe()
        return {'exit_code':raw.returncode,'stdout':raw.stdout[:64000],'stderr':raw.stderr[:64000],
                'output_truncated':len(raw.stdout)>64000 or len(raw.stderr)>64000},snapshot

    def pause(self):pass
    def resume(self):pass
    def close(self):return {'container':self.name,'retained':True}

class World:
    def write_shared(self,path,data,actor,origin):
        assert str(PurePosixPath(path))==path and path.startswith('/registry/') and '..' not in PurePosixPath(path).parts
        prior=self.shared.get(path)
        self.shared[path]={'path':path,'data':data,'sha256':sha256(base64.b64decode(data)).hexdigest(),
                           'author':actor,'version':prior['version']+1 if prior else 1,'origin':origin}
    def close_actor(self,actor):return {'actor':actor,'retained':True}
    def close(self):return [{'actor':a,'retained':True} for a in self.workstations]
