"""Create and validate the Harbor task package for every independent context."""
from hashlib import sha256
import json
from pathlib import Path
import tomllib
from harbor.models.task.config import TaskConfig
import lab

SCHEMA='1.4'

def digest(path):return sha256(Path(path).read_bytes()).hexdigest()

def config(actor):
    return f'''schema_version = "{SCHEMA}"

[task]
name = "swarmharm/procurement-reachout-{actor.lower()}"
version = "1.0"
description = "Synthetic procurement task in an isolated fleet context"
keywords = ["procurement", "synthetic", "multi-agent"]

[[task.authors]]
name = "SwarmHarm"

[metadata]
family = "procurement-reachout-v1"
actor = "{actor}"
request_id = "{lab.CASE['request_id']}"
execution_adapter = "experiments/procurement-reachout-v1/run.py"
generic_harbor_scheduler = false

[agent]
timeout_sec = 3600
user = "65534"

[verifier]
timeout_sec = 60
user = "root"

[environment]
docker_image = "{lab.IMAGE}"
network_mode = "no-network"
cpus = 1
memory_mb = 512
storage_mb = 1024
'''

def write(root,actors):
    root=Path(root);records={}
    for actor in actors:
        folder=root/actor;folder.mkdir(parents=True)
        (folder/'instruction.md').write_text(lab.task()+'\n')
        (folder/'task.toml').write_text(config(actor))
        (folder/'provenance.json').write_text(json.dumps({
            'source':'Original synthetic procurement records','family':'procurement-reachout-v1',
            'actor':actor,'request_id':lab.CASE['request_id'],
            'missing_document':'Clearwater-Medical-Supply-quote.json',
            'initial_registry':'Machine-generated document activity only',
            'campaign_runtime':'Registered SwarmHarm adapter; not generic Harbor scheduling.'},indent=2)+'\n')
        validate(folder,actor)
        records[actor]={str(p.relative_to(root)):digest(p) for p in sorted(folder.iterdir())}
    return records

def validate(folder,actor):
    folder=Path(folder);parsed=TaskConfig.model_validate(tomllib.loads((folder/'task.toml').read_text()))
    assert parsed.schema_version==SCHEMA and parsed.metadata['actor']==actor
    assert parsed.metadata['generic_harbor_scheduler'] is False
    assert parsed.environment.network_mode=='no-network'
    assert (folder/'instruction.md').read_text().strip()==lab.task()
    return lab.initial(actor,(folder/'instruction.md').read_text().strip())

def audit(root,actors):return {actor:validate(Path(root)/actor,actor) for actor in actors}
