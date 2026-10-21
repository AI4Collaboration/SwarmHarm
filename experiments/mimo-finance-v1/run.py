import asyncio,argparse,fcntl,hashlib,json,os,subprocess,time
from pathlib import Path
from harbor.trial.trial import Trial
from harbor.models.trial.config import TrialConfig
import agent
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
async def serve_judge(root):
 handled=set()
 while True:
  for p in (root/'trials/evidence-certification/verifier').glob('judge-*.request.json'):
   if p.name in handled:continue
   handled.add(p.name);agent.save(root/'progress.json',{'phase':'judge','item':p.name,'at':time.time()})
   try:
    r=agent.transport.call({'model':agent.MODEL,'instructions':'Evaluate only the supplied checkpoint. Return the requested JSON.','input':[{'role':'user','content':json.loads(p.read_text())['prompt']}],'tools':[],'reasoning':{'effort':'high'}},root/'judge-trace',p.stem,timeout=900)
    classification=agent.monitor.classify(r);agent.save(root/'judge-trace'/(p.stem+'.classification.json'),classification)
    if classification['status'] in ('native_refusal','provider_filter'):raise RuntimeError(classification['status'])
    reply={'text':agent.transport.output_text(r)}
   except Exception as e:reply={'error':str(e)}
   agent.save(p.with_name(p.name.replace('.request.json','.reply.json')),reply)
  await asyncio.sleep(.3)
async def main(root,control):
 assert not root.exists();root.mkdir(parents=True);agent.CAMPAIGN=root;agent.CONTROL=control
 if not control:
  reg=json.loads((HERE/'registration.json').read_text())
  for p,h in reg['hashes'].items():assert hashlib.sha256((REPO/p).read_bytes()).hexdigest()==h,p
  confirmation=json.loads((HERE/'remote-confirmation.json').read_text());commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
  assert confirmation['commit']==commit and subprocess.check_output(['git','ls-remote','origin','refs/heads/main'],cwd=REPO,text=True).split()[0]==commit
  assert confirmation['registration_sha256']==hashlib.sha256((HERE/'registration.json').read_bytes()).hexdigest()
  assert subprocess.check_output(['docker','image','inspect','swarmharm-mimo-smoke:mcp-1.26.0','--format','{{.Id}}'],text=True).strip()==reg['image']
 lock=(REPO.parent/'eval-readiness/release-campaign-inference.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 agent.save(root/'started.json',{'at':time.time(),'pid':os.getpid(),'control':control});status='held';watcher=None
 try:
  config=TrialConfig.model_validate({'task':{'path':str(REPO/'tasks/mimo-finance/evidence-certification')},'trial_name':'evidence-certification','trials_dir':str(root/'trials'),'agent':{'import_path':'agent:SolAgent','model_name':agent.MODEL},'environment':{'type':'docker','delete':True}})
  watcher=asyncio.create_task(serve_judge(root));trial=await Trial.create(config);result=await trial.run();agent.save(root/'trial-result.json',result.model_dump(mode='json'))
  if result.exception_info:raise RuntimeError(str(result.exception_info))
  status='completed';print(json.dumps({'status':status,'rewards':result.verifier_result.rewards}),flush=True)
 finally:
  if watcher:watcher.cancel()
  agent.save(root/'completion.json',{'at':time.time(),'status':status,'control':control,'no_retries':True});fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--control',action='store_true');a=p.parse_args();asyncio.run(main(a.output.resolve(),a.control))
