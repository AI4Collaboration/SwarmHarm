"""Replay the expansion's release records against the pinned ProgramBench executables."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from swarmform.programbench_workloads import WORKLOADS, workload

REGISTRY = Path(__file__).with_name("swarmform") / "programbench-instances.json"

# One offline workstation process checks every edition under the deployment's private account.
REPLAY = """
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
def replay(item):
    instance, job = item['instance'], item['workload']
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for path, text in job['files'].items():
            (root / path).write_text(text)
        args = ['/opt/programbench/invoke',instance,*job['argv']]
        environment = dict(os.environ, HOME=folder, TZ='UTC', LC_ALL='C', TERM='xterm-256color', OMP_NUM_THREADS='1')
        stdin = (root/job['stdin']).read_bytes() if job['stdin'] else b''
        result = subprocess.run(args, input=stdin, cwd=folder, env=environment, capture_output=True, timeout=40)
        if result.returncode:
            raise ValueError(f"{instance} exited {result.returncode}: {result.stderr[-600:]!r} {result.stdout[-140:]!r}")
        if job['product'] in ('stdout', 'stderr'):
            body = getattr(result, job['product'])
        else:
            body = (root / job['product']).read_bytes()
        if not body.strip():
            raise ValueError(f"{instance} produced an empty {job['product']}: {result.stderr[-500:]!r}")
        return {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
out = []
for item in json.load(sys.stdin):
    try: out.append(replay(item))
    except Exception as e: out.append({'error':str(e)})
print(json.dumps(out))
"""


def check(image, families, register=False):
    catalog = json.loads(REGISTRY.read_text())
    labels = [(f, i, j) for f in families for i in range(3) for j in range(2)]
    inputs = [dict(instance=catalog[f]["instance"], workload=workload(f,i,j)) for f,i,j in labels]
    proc = subprocess.run(["docker","run","--rm","-i","--network=none","--user","65534:65534",image,
                           "python","-I","-c",REPLAY],input=json.dumps(inputs).encode(),capture_output=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode())
    results = dict(zip(labels,json.loads(proc.stdout),strict=True))
    failures = {}
    for family in families:
        editions = [results[family,i,j] for i in range(3) for j in range(2)]
        failed = [e['error'] for e in editions if 'error' in e]
        if failed:
            failures[family] = failed[0]
            continue
        hashes = [[results[family,i,j]["sha256"] for j in range(2)] for i in range(3)]
        if any(a==b for a,b in hashes):
            failures[family] = "Both editions yielded the same registered output"
        elif register:
            catalog[family]["target_hashes"] = hashes
        elif catalog[family].get("target_hashes") != hashes:
            failures[family] = "Reference outputs differ from the registered hashes"
    if register and not failures:
        REGISTRY.write_text(json.dumps(catalog,indent=2)+"\n")
    print(json.dumps(dict(cases=len(labels), failures=failures),indent=2))
    return bool(failures)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",default=os.getenv("SWARMHARM_DOCKER_IMAGE","swarmform-programbench:ten"))
    parser.add_argument("--families",nargs="+",choices=WORKLOADS,default=list(WORKLOADS))
    parser.add_argument("--register",action="store_true",help="Record measured hashes when authoring new fixtures.")
    args = parser.parse_args()
    sys.exit(check(args.image,args.families,args.register))
