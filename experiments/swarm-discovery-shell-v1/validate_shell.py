"""Finite Docker controls; no model calls, signals, command replay or cleanup."""
import argparse,json,subprocess,time,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent

CONTROL=r'''
import errno,json,os,subprocess,threading,time
from pathlib import Path
marker='control-'+__import__('uuid').uuid4().hex
for folder in ('/workspace/proc','/registry/sys','/tmp/dev'):
 p=Path(folder);p.mkdir(parents=True,exist_ok=True);(p/'sample.json').write_text(marker+'\n')
ordinary=subprocess.run(['grep','-Rl',marker,'/workspace','/registry','/tmp'],capture_output=True,text=True)
pipe=subprocess.run(['grep',marker],input=marker+'\n',capture_output=True,text=True)
assert pipe.returncode==0 and pipe.stdout==marker+'\n'
assert all(p in ordinary.stdout for p in ['/workspace/proc/sample.json','/registry/sys/sample.json','/tmp/dev/sample.json'])
Path('/workspace/fifo-probe').mkdir();fifo=Path('/workspace/fifo-probe/stream');os.mkfifo(fifo)
def writer():
 deadline=time.monotonic()+3
 while time.monotonic()<deadline:
  try:fd=os.open(fifo,os.O_WRONLY|os.O_NONBLOCK);break
  except OSError as e:
   if e.errno!=errno.ENXIO:raise
   time.sleep(.01)
 else:return
 time.sleep(1.0);os.write(fd,(marker+'\n').encode());os.close(fd)
thread=threading.Thread(target=writer);thread.start();started=time.monotonic()
probe=subprocess.run(['grep','-Rl',marker,'/workspace/fifo-probe'],capture_output=True,text=True)
elapsed=time.monotonic()-started;thread.join()
# Explicit proc access stays available; only recursive root enumeration changes.
assert subprocess.run(['grep','Name:','/proc/self/status'],capture_output=True).returncode==0
root=None
if __import__('sys').argv[1]=='fixed':
 started=time.monotonic();result=subprocess.run(['grep','-Rl','--include=*.json',marker,'/'],capture_output=True,text=True)
 root={'elapsed_seconds':time.monotonic()-started,'stdout':result.stdout,'exit_code':result.returncode}
 assert all(p in result.stdout for p in ['/workspace/proc/sample.json','/registry/sys/sample.json','/tmp/dev/sample.json'])
 assert root['elapsed_seconds']<30
 assert probe.returncode==1 and elapsed<.8
else:assert probe.returncode==0 and elapsed>=.8
print(json.dumps({'fifo_elapsed_seconds':elapsed,'fifo_exit_code':probe.returncode,'ordinary_stdout':ordinary.stdout,'stdin_preserved':True,'explicit_proc_read_preserved':True,'root_search':root}))
'''

def check(out):
    out.mkdir(parents=True,exist_ok=False);images=json.loads((HERE/'images.json').read_text());receipts={}
    for arm in ('stock','fixed'):
        name='sh-shell-control-'+arm+'-'+uuid.uuid4().hex[:10]
        args=['docker','run','--pull=never','--name',name,'--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--user','65534:65534','--memory=512m','--cpus=1','--pids-limit=64']
        for path,size in (('/workspace','32m'),('/registry','16m'),('/tmp','32m')):args+=['--tmpfs',f'{path}:rw,nosuid,nodev,size={size},mode=1777']
        command=args+[images[arm]['image'],'python3','-I','-c',CONTROL,arm]
        (out/(arm+'-command.json')).write_text(json.dumps(command,indent=2)+'\n')
        with (out/(arm+'-stdout')).open('wb') as stdout,(out/(arm+'-stderr')).open('wb') as stderr:
            # Controls have finite writer deadlines and exit naturally; no timeout/kill API.
            result=subprocess.run(command,stdout=stdout,stderr=stderr)
        assert result.returncode==0,(arm,(out/(arm+'-stderr')).read_text())
        receipts[arm]=json.loads((out/(arm+'-stdout')).read_text());receipts[arm]['container_retained']=name
    import sys
    sys.path.insert(0,str(HERE.parent/'back-office-v1'));from durability import save,export
    save(out/'receipt.json',{'status':'passed','controls':receipts,'model_calls':0,'old_unknown_commands_replayed':False,'processes_signalled':False})
    export(out,out.parent/(out.name+'-backup'));return receipts
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);args=p.parse_args();print(json.dumps(check(args.out),indent=2))
