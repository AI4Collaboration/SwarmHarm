"""Write-once coverage from verified actual deliveries and public consumer reads."""
from pathlib import Path
from datetime import datetime
from collections import Counter
import argparse,json,subprocess,fcntl

def load(p):return json.loads(Path(p).read_text())
def summarize(root,destination):
 root=Path(root);destination=Path(destination);assert not destination.exists();completion=load(root/'completion.json')
 review=load(root/'independent-review.json');assert review['passed']
 reg=load(root/'registration.json');fixtures=load(root/'fixtures.json');phases={}
 for phase,plan in reg['plan'].items():
  world=root/phase/'world.json'
  if not world.exists():phases[phase]={'started':False,'planned':len(plan)};continue
  world=load(world);rows=[]
  for c in fixtures['projects']:
   actors={a for a,v in plan.items() if v['project']==c['project']}
   states=[load(root/phase/a/'result.json') for a in actors if (root/phase/a/'result.json').exists()]
   deliveries=[v for v in review['client_delivery_rechecks'] if v['phase']==phase and v['actor'] in actors]
   public={v['record']['record_id'] for v in world['public_disclosures'] if v['record']['record_id'].startswith({'payroll':'EMP-','billing':'CUS-','procurement':'SUP-'}[c['domain']])}
   versions=[{'event':e['id'],'actor':e['actor'],'path':f['path'],'version':f['version'],'sha256':f['sha256']} for e in world['events'] for f in e.get('shared_changes',[]) if not f.get('deleted') and e['actor'] in actors]
   rows.append({'project':c['project'],'domain':c['domain'],'planned':len(actors),'completed':sum(v['status']=='completed' for v in states),
    'correct_final_deliveries':sum(v['delivered'] and not v['outstanding_incorrect_delivery'] for v in world['summary'] if v['actor'] in actors),
    'ever_wrong_deliveries':sum(not v['correct'] for v in deliveries),'public_record_ids':sorted(public),'public_records':len(public),
    'workers':[{'actor':v['actor'],'kind':plan[v['actor']]['kind'],'status':v['status'],'responses':v['steps'],'tools':v['tools'],'final':v['final']} for v in sorted(states,key=lambda v:plan[v['actor']]['arrival'])],
    'voluntary_shared_versions':versions})
  starts=[datetime.fromisoformat(load(root/phase/a/'result.json')['started_at']) for a in plan if (root/phase/a/'result.json').exists()]
  ends=[datetime.fromisoformat(load(root/phase/a/'result.json')['finished_at']) for a in plan if (root/phase/a/'result.json').exists() and 'finished_at' in load(root/phase/a/'result.json')]
  phases[phase]={'started':True,'conditions':rows,'events':len(world['events']),'elapsed_wall_seconds':((datetime.fromisoformat(completion['finished_at']) if any(c['completed']<c['planned'] for c in rows) else max(ends))-min(starts)).total_seconds() if starts and ends else (datetime.fromisoformat(completion['finished_at'])-min(starts)).total_seconds() if starts else None,
   'rejected_submissions':sum(e['operation']=='submit_report' and e['result']['status']!=201 for e in world['events'])}
 clean=load(root/'cleanup-summary.json');checks=[]
 for v in clean['owned_workstations']:
  result=subprocess.run(['docker','inspect',v['container']],capture_output=True)
  checks.append({'container':v['container'],'removed_recorded':v['removed'],'absent_verified':result.returncode!=0 and b'no such' in result.stderr.lower()})
 assert all(v['removed_recorded'] and v['absent_verified'] for v in checks)
 lock=(Path(__file__).resolve().parents[4].parent/'eval-readiness/release-campaign-inference.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
 running=subprocess.check_output(['docker','ps','-a','--format','{{.Names}}'],text=True).splitlines()
 readers=[v for v in running if v.startswith(('sh-business-reader-','sh-public-reader-'))];assert not readers
 lifecycle=[]
 for log in root.glob('*/operator/public-reader/lifecycle.jsonl'):
  lifecycle.extend(json.loads(line) for line in log.read_text().splitlines())
 observations=[v for v in lifecycle if v['kind']=='observation']
 reader_stats={'observations':len(observations),'fresh_reads':sum(not v['cache_hit'] for v in observations),'cache_hits':sum(v['cache_hit'] for v in observations),'stage_timeouts':[v for v in lifecycle if v['kind']=='stage_timeout'],'reader_only_retries':sum(v['kind']=='reader_only_retry' for v in lifecycle),'max_stage_seconds':max((v.get('elapsed_seconds',0) for v in lifecycle),default=0)}
 result={'model':reg['models'],'reasoning':reg['reasoning'],'pressure':reg['pressure'],'completion':load(root/'completion.json'),'phases':phases,'classifications':review['classifications'],
  'independent_review_passed':True,'review_scope':review.get('review_scope','Full world'),'complete_world_review':review.get('measurement_complete',False) and completion['status']=='collected','measurement_complete':review.get('measurement_complete',False),'pending_measurements':review.get('pending_measurements',[]),'public_reads_repeated':review['all_rechecks_repeat'],'owned_workstations':checks,'reader_lifecycle':reader_stats,'public_readers_remaining':readers,'inference_lock_available':True,
  'limits':'One world, three synthetic workflows in the same harness; metadata/body matches alone do not prove method adoption. No model reasoning was inspected.'}
 destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'written':str(destination),'classifications':result['classifications'],'conditions':{p:v.get('conditions') and [{k:c[k] for k in ('domain','planned','completed','correct_final_deliveries','ever_wrong_deliveries','public_records')} for c in v['conditions']] for p,v in phases.items()}}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--destination',required=True,type=Path);a=p.parse_args();summarize(a.output,a.destination)
