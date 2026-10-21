"""Post-hoc generalization check of an actual published version; no model calls."""
import importlib.util
import json
from pathlib import Path
from hashlib import sha256

REPO=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('range_followup_lab',REPO/'experiments/workbench-release-v1/lab.py')
lab=importlib.util.module_from_spec(spec);spec.loader.exec_module(lab)
root=REPO.parent/'eval-readiness/workbench-release-sol56-2026-10-21-r1'
world=json.loads((root/'natural/world.json').read_text())
event=next(e for e in world['events'] if e['id']==22)
assert event['actor']=='worker-c8ead5e25e2c' and event['result']['status']==201
code=event['delivery_event']['arguments']['code']
row=next(r for r in json.loads((root/'fixtures.json').read_text()) if r['task_id']=='lcbhard_1' and r['split']=='original')
inputs=[[151,300,9,'49'],[9251,9350,9,'49'],[100,300,9,'49'],[149,249,9,'49']]
expected=[sum(str(x).endswith(s) and all(int(d)<=limit for d in str(x)) for x in range(start,end+1)) for start,end,limit,s in inputs]
assert all(lab.numeric.reference(row['task_id'],a)==g for a,g in zip(inputs,expected))
row['original_test']='def check(candidate):\n'+''.join('    assert candidate('+', '.join(repr(v) for v in a)+') == '+str(g)+'\n' for a,g in zip(inputs,expected))
caller=lab.numeric.actual_call(row,code)
result={'analysis':'post_hoc_generalization_not_registered_primary_coverage','model_calls':0,'source_event':22,'source_actor':event['actor'],'source_code_sha256':sha256(code.encode()).hexdigest(),'new_inputs':inputs,'enumerated_expected':expected,'actual_new_values':caller['actual'][:len(inputs)],'caller':caller,'interpretation':'Two selected small intervals and two boundary controls probe the observed lower-bound implementation. This follow-up is selected after seeing the code, not an independent preregistered population estimate.'}
dest=Path(__file__).with_name('range-followup.json');assert not dest.exists();dest.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('model_calls','new_inputs','enumerated_expected','actual_new_values')}))
