"""Package approval-code-v1 Harbor trials for the viewer; retain campaign provenance.

This adapter records this pilot's registered sequence and resets, not arbitrary campaigns.
"""
import argparse,json,shutil,uuid,hashlib
from datetime import datetime,timezone
from pathlib import Path
from harbor.models.job.result import JobResult,JobStats
from harbor.models.job.config import JobConfig
from harbor.models.trial.result import TrialResult
from harbor.models.trajectories import Trajectory

def load(p):return json.loads(p.read_text())
def package(source,dest):
 assert not dest.exists(),'Never overwrite a job export'
 assert load(source/'completion.json')['status']=='completed'
 assert (source/'atif-validation.json').exists()
 dest.mkdir(parents=True);results=[];source_hashes={}
 for trial in sorted((source/'trials').iterdir()):
  if not (trial/'result.json').exists():continue
  Trajectory.model_validate_json((trial/'agent/trajectory.json').read_text())
  results.append(TrialResult.model_validate_json((trial/'result.json').read_text()))
  shutil.copytree(trial,dest/trial.name)
  for p in trial.rglob('*'):
   if p.is_file():source_hashes[str(p.relative_to(source))]=hashlib.sha256(p.read_bytes()).hexdigest()
 result=JobResult(id=uuid.uuid5(uuid.NAMESPACE_URL,str(source.resolve())),started_at=datetime.fromtimestamp(load(source/'started.json')['at'],timezone.utc),finished_at=datetime.fromtimestamp(load(source/'completion.json')['at'],timezone.utc),n_total_trials=len(results),stats=JobStats.from_trial_results(results,n_total_trials=len(results)),trial_results=results)
 (dest/'result.json').write_text(result.model_dump_json(indent=2)+'\n')
 config=JobConfig.model_validate({'job_name':dest.name,'jobs_dir':str(dest.parent),'n_concurrent_trials':1,'retry':{'max_retries':0},'agents':[dict(results[0].config.agent.model_dump(mode='json'),name=results[0].agent_info.name)],'tasks':[r.config.task.model_dump(mode='json') for r in results],'environment':results[0].config.environment.model_dump(mode='json')})
 (dest/'config.json').write_text(config.model_dump_json(indent=2,exclude_unset=True)+'\n')
 campaign=dest/'campaign';campaign.mkdir()
 for name in ('started.json','completion.json','shared.json','atif-validation.json','independent-review.json'):
  if (source/name).exists():shutil.copy2(source/name,campaign/name)
 (dest/'campaign.json').write_text(json.dumps({'format':'Harbor JobResult aggregation over actual Harbor Trial runs','orchestration':'Sequential SwarmHarm campaign adapter, not a native Harbor Job scheduler run','config_origin':'Derived viewer metadata from actual trial configurations; replay the registered campaign runner to preserve peer state and order','raw_source':str(source.resolve()),'source_sha256':source_hashes,'sequence':['funded','alder','birch','cedar'],'shared_registry_reset_before':['funded','alder'],'initial_seeded_methods':False},indent=2)+'\n')
 print(json.dumps({'job':str(dest),'trials':len(results),'ATIF':'ATIF-v1.8','schema_validation':True}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path);a=p.parse_args();package(a.source,a.destination)
