"""A real waiting shell and a responding workstation; zero model calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('out',type=Path)
parser.add_argument('--baseline',action='store_true')
args=parser.parse_args()
if args.baseline:sys.path.insert(0,str(HERE.parent/'swarm-discovery-v1'))
from design import fixtures,CACHE
from world import World
args.out.mkdir(parents=True,exist_ok=False)
w=World(fixtures(20261024,population=2),args.out/'world');w.start()
a,b=w.fixture['actors'];question=CACHE+'/question.txt';reply=CACHE+'/reply.txt'
command=f"printf '%s' 'fresh-request-59187324' > {question}; for n in $(seq 1 60); do if test -f {reply}; then cat {reply}; exit 0; fi; sleep 0.05; done; exit 7"
with ThreadPoolExecutor(max_workers=2) as pool:
    started=time.monotonic();waiting=pool.submit(w.call,a,'bash',{'command':command})
    deadline=time.monotonic()+5
    while not (w.cache_roots[a]/'question.txt').exists():
        if time.monotonic()>deadline:raise RuntimeError('question never written')
        time.sleep(.02)
    responding=pool.submit(w.call,b,'bash',{'command':f"cat {question}; printf '%s' 'fresh-reply-59187324' > {reply}"})
    first=waiting.result();second=responding.result()
    elapsed=time.monotonic()-started
success=first['exit_code']==0 and first['stdout']=='fresh-reply-59187324' and 'fresh-request-59187324' in second['stdout']
assert success is not args.baseline,(success,args.baseline,first,second)
state=w.state()
if not args.baseline:
    assert any(e.get('execution_interval',{}).get('overlapped') for e in state['events'])
    assert state['observation_ambiguities'],'overlap must not silently invent an author'
    assert all(r['author'] is None for e in state['events'] for r in e['changes'])
(args.out/'state.json').write_text(json.dumps(state,indent=2)+'\n')
receipt={'status':'passed','baseline':args.baseline,'real_waiting_shell_received_live_reply':success,'elapsed_seconds':elapsed,
         'containers_retained':w.containers,'model_calls':0,'processes_stopped':False,
         'measurement_limit':'Concurrent filesystem diffs do not prove the writer; affected formation scores stay unknown.'}
(args.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
