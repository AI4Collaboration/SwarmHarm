"""Run inherited positive and repaired controls under the new image, without APIs."""
import argparse,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'swarm-discovery-v3'))
import safe_runtime,run as base

def check(arm,out):
    images=json.loads((HERE/'images.json').read_text());safe_runtime.IMAGE=images[arm]['image'];base.IMAGE=safe_runtime.IMAGE
    spec=importlib.util.spec_from_file_location('scripted_collector',HERE.parent/'swarm-discovery-v3/validate_collector.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    result=m.check(out)
    assert result['completed_lines']==8 and len(result['grounded_request_reply_use_chains'])==4
    return {'status':'passed','arm':arm,'model_calls':0,'completed_lines':8,'grounded_chains':4,'image':safe_runtime.IMAGE}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('arm',choices=['stock','fixed']);p.add_argument('out',type=Path);a=p.parse_args();print(json.dumps(check(a.arm,a.out),indent=2))
