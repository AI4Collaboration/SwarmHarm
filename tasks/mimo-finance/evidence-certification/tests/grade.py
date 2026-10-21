"""Unchanged upstream scoring, with host-only judge transport via private log files."""
import importlib.util,json,time,subprocess
from pathlib import Path
LOG=Path('/logs/verifier');LOG.mkdir(exist_ok=True);LOG.chmod(0o700)
spec=importlib.util.spec_from_file_location('mimo_verify','/tests/verify.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
count=0
def judge(prompt,*args,**kwargs):
 global count
 count+=1;assert count<=4
 req=LOG/f'judge-{count:02d}.request.json';resp=LOG/f'judge-{count:02d}.reply.json'
 tmp=req.with_suffix('.tmp');tmp.write_text(json.dumps({'prompt':prompt}));tmp.replace(req)
 deadline=time.monotonic()+900
 while not resp.exists():
  if time.monotonic()>deadline:raise RuntimeError('Host judge timeout')
  time.sleep(.2)
 r=json.loads(resp.read_text())
 if 'error' in r:raise RuntimeError(r['error'])
 return r['text']
v._chat_judge_sc=judge;v._grade=v._grade_sc
if Path('/var/lib/mimo/control').exists():
 meta=v._meta();scope={};exec(meta['check_code'],scope)
 results={i['id']:scope[i['fn']](Path('/work/workspace')) for i in meta['items'] if i['method']=='rule'}
 (LOG/'offline-rules.json').write_text(json.dumps(results,indent=2));(LOG/'reward.json').write_text(json.dumps({'reward':0,'offline_control':1}))
else:
 r=v.verify(env_path='/work',agent_output=Path('/var/lib/mimo/final.txt').read_text())
 (LOG/'upstream-grade.json').write_text(json.dumps(r,indent=2))
 if r.get('reward_error'):raise RuntimeError('Source judge unavailable: '+r['reward_error'])
 (LOG/'reward.json').write_text(json.dumps({'reward':r['reward']}))
(LOG/'post-verifier-state.json').write_text(subprocess.check_output(['python3','/opt/mimo/snapshot.py'],text=True))
