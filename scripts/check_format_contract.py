#!/usr/bin/env python3
"""Fail closed when an experiment blurs input, execution or output formats."""
import argparse
import json
from pathlib import Path

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
    assert value['output']['business_effect_reviewed_independently'] is True
    assert isinstance(value['execution']['generic_harbor_job_scheduler'],bool)
    assert (folder/'format_checks.py').exists(),'Missing executable format controls'
    assert (folder/'export_atif.py').exists(),'Missing ATIF exporter'
    assert (folder/'review.py').exists(),'Missing independent reviewer'
    return {'experiment':str(folder),'input':'Harbor task schema 1.4','execution':value['execution'],'output':'ATIF-v1.8','passed':True}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('experiment',type=Path);a=p.parse_args()
    print(json.dumps(check(a.experiment),indent=2))
