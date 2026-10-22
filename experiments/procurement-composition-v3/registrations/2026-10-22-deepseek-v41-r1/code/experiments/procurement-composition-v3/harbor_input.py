"""Create and validate the exact Harbor task package used by each agent context."""
from hashlib import sha256
import json
from pathlib import Path
import tomllib

from harbor.models.task.config import TaskConfig

import lab

SCHEMA='1.4'
IMAGE='swarmharm-harbor-base:20261021'

def digest(path):return sha256(Path(path).read_bytes()).hexdigest()

def toml(item,phase,actor):
    request=item['request_id'].lower().replace('_','-')
    return f'''schema_version = "{SCHEMA}"

[task]
name = "swarmharm/procurement-composition-{request}"
version = "2.0"
description = "Synthetic procurement requisition in a registered multi-agent campaign"
keywords = ["procurement", "synthetic", "business-process"]

[[task.authors]]
name = "SwarmHarm"

[metadata]
family = "procurement-composition-v3"
phase = "{phase}"
actor = "{actor}"
request_id = "{item['request_id']}"
execution_adapter = "experiments/procurement-composition-v3/run.py"
generic_harbor_scheduler = false

[agent]
timeout_sec = 43200
user = "65534"

[verifier]
timeout_sec = 60
user = "root"

[environment]
docker_image = "{IMAGE}"
network_mode = "no-network"
cpus = 1
memory_mb = 512
storage_mb = 1024
'''

def write(root,plan):
    root=Path(root);records={}
    for phase,actors in plan.items():
        records[phase]={}
        for actor,item in actors.items():
            folder=root/phase/actor;folder.mkdir(parents=True)
            instruction=lab.task(item)
            (folder/'instruction.md').write_text(instruction+'\n')
            (folder/'task.toml').write_text(toml(item,phase,actor))
            (folder/'provenance.json').write_text(json.dumps({
                'source':'Original synthetic procurement records',
                'family':'procurement-composition-v3','phase':phase,'actor':actor,
                'request_id':item['request_id'],'provided_documents':item['provided'],
                'campaign_runtime':'Registered SwarmHarm adapter; not generic Harbor job scheduling.'
            },indent=2)+'\n')
            validate(folder,item,phase,actor)
            records[phase][actor]={str(p.relative_to(root)):digest(p) for p in sorted(folder.iterdir())}
    return records

def validate(folder,item,phase,actor):
    folder=Path(folder)
    config=TaskConfig.model_validate(tomllib.loads((folder/'task.toml').read_text()))
    assert config.schema_version==SCHEMA
    assert config.metadata['phase']==phase and config.metadata['actor']==actor
    assert config.metadata['request_id']==item['request_id']
    assert config.metadata['generic_harbor_scheduler'] is False
    assert config.environment.network_mode=='no-network'
    instruction=(folder/'instruction.md').read_text().strip()
    assert instruction==lab.task(item)
    provenance=json.loads((folder/'provenance.json').read_text())
    assert provenance['provided_documents']==item['provided']
    return instruction

def initial_audit(root,plan):
    root=Path(root);result={}
    for phase,actors in plan.items():
        result[phase]={}
        for actor,item in actors.items():
            instruction=validate(root/phase/actor,item,phase,actor)
            result[phase][actor]=lab.initial(actors,actor,instruction)
    return result
