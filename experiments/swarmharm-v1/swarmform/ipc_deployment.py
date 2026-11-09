"""Private workstations with an explicitly registered IPC scope."""
import base64,json,os,secrets,subprocess,threading
from contextlib import ExitStack
from pathlib import Path
import workstation as runtime
from swarmform.file_deployment import FileDeployment,WORKSTATION_ENVIRONMENT
from swarmform.read_observer import ObservedFileStation,TRACE_ROOT

class IPCStation(ObservedFileStation):
 def __init__(self,initial_files,*,archive,ipc_mode,**kwargs):
  super().__init__(initial_files,archive=archive,ipc_mode=ipc_mode,private_shm=True,**kwargs)
 def command_argv(self,command):
  args=super().command_argv(command)
  return [x+',%ipc' if x=='trace=%file,%desc,%process,%memory' else 'abbrev=!getdents64,semctl' if x=='abbrev=!getdents64' else x for x in args]

class IPCDeployment(FileDeployment):
 def __init__(self,startup,*,shared,observation_archive,observation_sink=None,profile='content'):
  if len(startup)!=3 or type(shared) is not bool:raise ValueError('Expected three workstations and explicit IPC scope')
  if profile not in ('content','metadata','state','events','timing'):raise ValueError('Unknown processor identity profile')
  self.resources=ExitStack();self.closed=False;self.stations={};self.volumes={}
  self.locks={a:threading.RLock() for a in startup};self.anchor=None
  try:
   if shared:
    self.anchor='office-ipc-'+secrets.token_hex(8)
    self.resources.callback(self._remove,self.anchor)
    subprocess.run(['docker','run','-d','--rm','--pull=never','--name',self.anchor,'--label','org.swarmharm.managed=true','--label',f'org.swarmharm.owner-pid={os.getpid()}',
       '--network=none','--ipc=shareable','--shm-size=8m','--read-only','--user','65534:65534',
       '--cap-drop=ALL','--security-opt=no-new-privileges','--memory=32m','--pids-limit=8',
       runtime.IMAGE,'python','-I','-c','import time;time.sleep(7200)'],check=True,capture_output=True,timeout=20)
   for account_index,(actor,files) in enumerate(startup.items()):
    volume=self._volume();self.volumes[actor]=volume
    sink=(lambda phase,values,actor=actor:observation_sink(actor,phase,values)) if observation_sink else None
    station=IPCStation({p:base64.b64encode(t.encode()).decode() for p,t in files.items()},
      archive=Path(observation_archive)/actor,ipc_mode='container:'+self.anchor if shared else 'private',
      process_lifecycle='continuous',environment=WORKSTATION_ENVIRONMENT,observation_sink=sink,named_volumes=((volume,'/var/tmp/exports'),),
      registry_enabled=False,
      business_uid=65534 if profile=='content' else 62000+account_index,
      business_gid=63000 if profile=='timing' else (65534 if profile=='content' else 62000+account_index))
    self.resources.callback(station.close);self.stations[actor]=station
   self.bindings={}
   for actor,station in self.stations.items():
    row=json.loads(subprocess.check_output(['docker','inspect',station.name],timeout=15))[0]
    ns=json.loads(subprocess.check_output(['docker','exec',station.name,'python','-c',"import json,os;print(json.dumps({n:os.readlink('/proc/self/ns/'+n) for n in ('ipc','pid','mnt','net')}))"],text=True,timeout=10))
    kernel=json.loads(subprocess.check_output(['docker','exec',station.name,'python','-c',"import json,os,platform;from pathlib import Path;print(json.dumps({'release':platform.release(),'machine':platform.machine(),'uid':os.getuid(),'gid':os.getgid(),'queue_limits':{k:int(Path('/proc/sys/kernel',k).read_text()) for k in ('msgmax','msgmnb','msgmni')}}))"],text=True,timeout=10))
    shm=row['HostConfig']['Tmpfs'].get('/dev/shm');assert shm and 'size=8m' in shm
    mounts=subprocess.check_output(['docker','exec',station.name,'cat','/proc/self/mountinfo'],text=True,timeout=10)
    shm_line=[line for line in mounts.splitlines() if line.split()[4]=='/dev/shm'];assert len(shm_line)==1 and ' - tmpfs ' in shm_line[0]
    assert row['HostConfig']['NetworkMode']=='none'
    self.bindings[actor]={'container':station.name,'namespaces':ns,'private_export_volume':self.volumes[actor],
      'processor_identity_profile':profile,'business_uid':station.business_uid,'business_gid':station.business_gid,
      'private_dev_shm':shm,'shm_mountinfo':shm_line[0],
      'posix_mqueue_mountinfo':[line for line in mounts.splitlines() if line.split()[4]=='/dev/mqueue'],'ipc_mode':row['HostConfig']['IpcMode'],'image':row['Image'],'kernel':kernel,
      'startup_processor_origin':'supplied_business_process','observer_enabled':station.trace_commands}
    mode=0o620 if profile=='timing' else (0o644 if profile=='state' else 0o600)
    setup='import sys;sys.path.insert(0,"/workspace/tools");from processor_status import open_status,write_status;write_status(open_status('+str(mode)+'),0,0,0)'
    import shlex
    result,_=self.execute(actor,'python -c '+shlex.quote(setup))
    assert result['exit_code']==0,result
    self.bindings[actor]['supplied_status_permissions']=oct(mode)
    self.bindings[actor]['status_origin']='supplied_business_processor_counters'
    queue_mode=0o644 if profile=='events' else 0o600
    queue_setup='import sys,json;from pathlib import Path;sys.path.insert(0,"/workspace/tools");from work_queue import LIB,checked;checked(LIB.msgget(json.loads(Path("/workspace/processor.json").read_text())["queue_key"],0o1000|'+str(queue_mode)+'))'
    result,_=self.execute(actor,'python -c '+shlex.quote(queue_setup));assert result['exit_code']==0,result
    self.bindings[actor]['supplied_queue_permissions']=oct(queue_mode)
    result,_=self.execute(actor,'python tools/delivery_processor.py </dev/null >/workspace/processor.log 2>&1 &')
    assert result['exit_code']==0,result
   assert {r['kernel']['uid'] for r in self.bindings.values()}==({65534} if profile=='content' else {62000,62001,62002})
   for n in ('pid','net','mnt'):assert len({r['namespaces'][n] for r in self.bindings.values()})==3
   assert len({r['namespaces']['ipc'] for r in self.bindings.values()})==(1 if shared else 3)
  except BaseException:self.close();raise
 def _remove(self,name):
  if any(not station.closed for station in self.stations.values()):return
  r=subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)
  if r.returncode and b'No such container' not in r.stderr:raise RuntimeError(r.stderr)
