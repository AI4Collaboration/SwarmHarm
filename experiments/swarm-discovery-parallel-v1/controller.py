"""One-shot bounded queue. Never kills, pauses, restarts or resends a worker."""
import argparse,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
from run import base,gate
import allowance
from report import write as write_report


def control(root,backup):
    gate();fd=os.open(root/'controller-started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump({'started_at':time.time()},f)
    suite=json.loads((root/'suite.json').read_text());queue=list(suite['queue']);active={};finished=[];admission='open'
    def checkpoint():
        write_report(root,finished,admission,active,queue)
        base.save(root/'controller-status.json',{'at':time.time(),'admission':admission,'active':list(active),'queued':[c['id'] for c in queue],'finished':finished})
        # Do not copy live journals; workers export those at their own stable checkpoints.
        for name in ('suite.json','controller-status.json','allowance.json','controller-started.json','recovery-index.json','report.json','REPORT.md'):
            if (root/name).exists():base.atomic_bytes(backup/name,(root/name).read_bytes())
    while active or queue:
        with allowance.locked(root) as state:
            if time.time()-state['checked_at']>15:
                try:state.update(remaining=str(allowance.key_remaining()),checked_at=time.time(),spent_at_snapshot=state['spent'])
                except Exception as error:state['hold']='Allowance lookup failed: '+type(error).__name__
            available=allowance.available(state);hold=state.get('hold');deadline=state['admission_deadline']
        if hold:admission='held_unresolved_or_allowance'
        if shutil.disk_usage(root).free<20*1024**3:admission='held_disk_capacity'
        mem=subprocess.run(['memory_pressure','-Q'],capture_output=True,text=True).stdout
        m=re.search(r'System-wide memory free percentage:\s*(\d+)%',mem)
        if m and int(m.group(1))<10:admission='held_memory_capacity'
        if admission=='open':
            while queue and len(active)<suite['max_parallel_trials']:
                cell=queue[0];minimum=10 if cell['model_name']=='glm' else 1
                if time.time()+cell['seconds']+300>=deadline:admission='closed_eod';break
                if available<minimum:admission='closed_insufficient_allowance';break
                queue.pop(0);native=root/'runs'/cell['id'];log=(root/'logs'/cell['id']);log.parent.mkdir(exist_ok=True)
                handle=log.open('xb')
                proc=subprocess.Popen([sys.executable,str(Path(__file__).parent/'run.py'),'collect','--root',str(root),'--out',str(native)],stdout=handle,stderr=subprocess.STDOUT)
                active[cell['id']]={'process':proc,'log':handle,'cell':cell};available-=minimum
                checkpoint()
        for name,item in list(active.items()):
            code=item['process'].poll()
            if code is None:continue
            item['log'].close();native=root/'runs'/name;row={'id':name,'cell':item['cell'],'collector_exit':code}
            if (native/'trial/result.json').exists():
                derivative=root/'audits'/name;derivative.parent.mkdir(exist_ok=True)
                log=root/'logs'/(name+'-audit.log')
                with log.open('xb') as stream:
                    analyzed=subprocess.run([sys.executable,str(Path(__file__).parent/'analyze.py'),str(native),str(derivative)],stdout=stream,stderr=subprocess.STDOUT)
                row['audit_exit']=analyzed.returncode
                if analyzed.returncode==0:
                    row['summary']=json.loads((derivative/'summary.json').read_text());base.export(derivative,backup/'audits'/name)
                else:row['grading_status']='grading_error'
            else:row['grading_status']='collector_error_unscored'
            if code or row.get('audit_exit',0):
                with allowance.locked(root) as s:s['hold']='Collector or grader failure; preserve artifacts and reservations for audit.'
            finished.append(row);del active[name];checkpoint()
        if admission!='open' and not active:break
        checkpoint();time.sleep(10)
    base.save(root/'completion.json',{'status':'bounded_suite_finished','admission':admission,'finished_trials':len(finished),'not_started':[c['id'] for c in queue],'unknown_reservations_preserved':True,'processes_stopped':False})
    checkpoint();base.export(root,backup)
    return finished

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--backup',type=Path,required=True);a=p.parse_args();print(json.dumps({'finished_trials':len(control(a.root,a.backup))}))
