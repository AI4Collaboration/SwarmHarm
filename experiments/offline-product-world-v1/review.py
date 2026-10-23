"""Independently summarize a completed product-world trial."""
import argparse,json,shutil
from collections import Counter
from pathlib import Path
def read(path):return json.loads(path.read_text())
def rows(values):return Counter(json.dumps(v,sort_keys=True) for v in values)
def review(root):
 assert read(root/'completion.json')['status']=='completed';trial=root/'trials/model-release-v1';agent=trial/'agent';before=read(agent/'initial-state.json');after=read(agent/'final-state.json');changes={}
 for table in before['tables'].keys()|after['tables'].keys():
  old,new=rows(before['tables'].get(table,[])),rows(after['tables'].get(table,[]))
  if old!=new:changes[table]={'removed_rows':sum((old-new).values()),'added_rows':sum((new-old).values())}
 native=sorted((agent/'trace').glob('*.response.json'));events=read(agent/'events.json') if (agent/'events.json').exists() else [];classifiers=[read(p) for p in agent.glob('classifier-*.json')];outcome=read(trial/'verifier/business-outcome.json');final=read(agent/'final.json')
 result={'model':read(root/'started.json')['model'],'preflight':read(root/'preflight/passed.json'),'subject_requests':len(native),'tool_calls':len(events),'elapsed_seconds':final['elapsed_seconds'],'native_models':sorted({read(p)['model'] for p in native}),'provider_error_files':[str(p.relative_to(root)) for p in root.rglob('*.error.json')],'classification_statuses':dict(Counter(v['status'] for v in classifiers)),'shell_events':events,'business_outcome':outcome,'database_changes':changes,'modified_or_removed_workspace_files':[p for p,h in before['files'].items() if after['files'].get(p)!=h],'new_workspace_files':sorted(set(after['files'])-set(before['files'])),'final_answer':final['text'],'scope':'One contained product-release task; no peer-propagation claim.'}
 (root/'independent-review.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');shutil.copy2(trial/'verifier/business-outcome.json',trial/'verifier/business-evidence.json');return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();r=review(a.root);print(json.dumps({k:v for k,v in r.items() if k not in ('shell_events','final_answer')},indent=2))
