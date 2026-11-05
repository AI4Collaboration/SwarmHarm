"""Public conformance runner with resumable selection for bounded shell commands.

The pinned tests and upstream checks are unchanged. Offset/count select work;
all results are printed immediately, including failures and remaining cases.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,'/app')
from run_tests import RUNNERS, SUITE_ORDER
from utils import run_suites

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('compiler');p.add_argument('--offset',type=int,default=0)
    p.add_argument('--count',type=int,default=25)
    a=p.parse_args()
    if a.offset<0 or a.count<1:p.error('offset must be nonnegative and count positive')
    suites=json.loads(Path('/app/filter.json').read_text())
    all_cases=[(suite,name) for suite in SUITE_ORDER for name in suites[suite]]
    selected=all_cases[a.offset:a.offset+a.count]
    subset={suite:[name for group,name in selected if group==suite] for suite in SUITE_ORDER}
    passed,total=run_suites(SUITE_ORDER,RUNNERS,subset,a.compiler)
    print(json.dumps({'passed':passed,'tested':total,'offset':a.offset,
                      'next_offset':a.offset+len(selected),'available_tests':len(all_cases)}),flush=True)
    sys.exit(0 if passed==total and total else 1)
