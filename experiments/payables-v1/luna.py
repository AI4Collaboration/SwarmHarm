"""Same frozen business inputs, fresh state, one separately registered Luna pilot."""
import argparse
from copy import deepcopy
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run


def configure():
    run.MODEL=run.transport.MODEL='gpt-6-luna'


def prepare(root,reference):
    assert run.load(reference/'completion.json')['status']=='collected'
    assert run.load(reference/'independent-review.json')['passed']
    source=run.load(reference/'registration.json')
    assert source['model']=='gpt-6.1-sol'
    if source.get('input_revision') != run.INPUT_REVISION:
        raise ValueError('Matched Luna comparison requires a completed Sol run with the current input revision.')
    configure();run.prepare(root)
    reg=run.load(root/'registration.json')
    assert run.sha(root/'fixtures.json')==run.sha(reference/'fixtures.json')
    assert run.sha(root/'tools.json')==run.sha(reference/'tools.json')
    reg['worlds']=deepcopy(source['worlds'])
    shutil.copyfile(reference/'initial-input-audit.json',root/'initial-input-audit.json')
    reg['input_hashes']['initial-input-audit.json']=run.sha(root/'initial-input-audit.json')
    reg['comparison']={'reference_registration_sha256':run.sha(reference/'registration.json'),
        'reference':'Completed Sol pilot, preserved unchanged',
        'identical_business_inputs_plan_and_budgets':True,'fresh_world_state':True,
        'only_model_changes':'gpt-6.1-sol to gpt-6-luna; both xhigh on the existing route',
        'limits':'One world per model; no general model-rate or causal capability claim.'}
    for path in (Path(__file__),HERE/'LUNA.md'):
        relative=path.relative_to(run.REPO)
        target=root/'code'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(path.read_bytes());reg['code_hashes'][str(relative)]=run.sha(path)
    run.save(root/'registration.json',reg)
    run.save(root/'registration-seal.json',{'sha256':run.sha(root/'registration.json'),'model_calls':0})
    assert run.sha(root/'initial-input-audit.json')==run.sha(reference/'initial-input-audit.json')
    print('Luna registered with byte-identical initial business inputs and fresh state; zero model calls.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference',type=Path)
    p.add_argument('--phase',choices=['prepare','collect'],required=True)
    a=p.parse_args();root=a.output.resolve()
    if a.phase=='prepare':
        if a.reference is None:p.error('prepare requires the completed Sol reference')
        prepare(root,a.reference.resolve())
    else:
        configure();assert run.load(root/'registration.json')['model']==run.MODEL
        run.collect(root)
