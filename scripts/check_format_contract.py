#!/usr/bin/env python3
"""Fail closed when an experiment blurs input, execution or output formats."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

def check(folder):
    folder=Path(folder).resolve();contract=folder/'format-contract.json'
    assert contract.exists(),f'Missing {contract}'
    value=json.loads(contract.read_text())
    assert value['input']['format']=='Harbor task package'
    assert value['input']['schema']=='1.4'
    assert value['input']['one_package_per_agent_context'] is True
    assert value['input']['instruction_is_runtime_input'] is True
    assert value['output']['trajectory']=='ATIF-v1.8'
    assert value['output']['native_records_retained'] is True
    independent_outcome_reviews=(
        value['output'].get('business_effect_reviewed_independently'),
        value['output'].get('side_channel_chain_reviewed_independently'),
    )
    assert any(review is True for review in independent_outcome_reviews)
    assert isinstance(value['execution']['generic_harbor_job_scheduler'],bool)
    assert (folder/'tests/format_checks.py').exists(),'Missing executable format controls'
    assert (folder/'export_atif.py').exists(),'Missing ATIF exporter'
    assert (folder/'review.py').exists(),'Missing independent reviewer'
    run=subprocess.run(
        [sys.executable,'-B','-m','unittest','tests.format_checks','-v'],cwd=folder,text=True,
        capture_output=True,check=False,
    )
    if run.returncode:
        raise RuntimeError(
            f'Executable format controls failed for {folder}\n{run.stdout}{run.stderr}'
        )
    return {
        'experiment':str(folder),
        'input':'Harbor task schema 1.4',
        'execution':value['execution'],
        'output':'ATIF-v1.8',
        'format_controls_passed':True,
        'passed':True,
    }

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('experiment',type=Path,nargs='*')
    a=p.parse_args()
    folders=a.experiment
    if not folders:
        repo=Path(__file__).resolve().parent.parent
        folders=sorted(p.parent for p in (repo/'experiments').glob('*/format-contract.json'))
        if not folders:
            raise SystemExit('No experiment format contracts found')
    results=[check(folder) for folder in folders]
    print(json.dumps(results[0] if len(results)==1 else results,indent=2))
