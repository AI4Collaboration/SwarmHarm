"""Write the exact Harbor packages consumed by the conditional-trial adapter."""
from hashlib import sha256
import json
from pathlib import Path
import tomllib
from harbor.models.task.config import TaskConfig
import lab

SCHEMA='1.4';IMAGE='swarmharm-harbor-base:20261021'
def digest(path):return sha256(Path(path).read_bytes()).hexdigest()
def toml(value,actor):
    return f'''schema_version = "{SCHEMA}"

[task]
name = "swarmharm/lesswrong-business-{value['step']}-{value['ordinal']:03d}"
version = "1.0"
description = "Non-cyber procurement analogue of one conditional LessWrong behavior evaluation"
keywords = ["procurement", "multi-agent", "synthetic", "conditional-reproduction"]

[[task.authors]]
name = "SwarmHarm"

[metadata]
family = "lesswrong-business-four-step-v1"
step = "{value['step']}"
ordinal = {value['ordinal']}
actor = "{actor}"
execution_adapter = "experiments/lesswrong-business-four-step-v1/run.py"
generic_harbor_scheduler = false

[agent]
timeout_sec = 7200
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
    for actor,value in plan.items():
        folder=root/actor;folder.mkdir(parents=True)
        (folder/'instruction.md').write_text(lab.task(value)+'\n');(folder/'task.toml').write_text(toml(value,actor))
        (folder/'provenance.json').write_text(json.dumps({'source':'Original synthetic procurement analogue','upstream_method':'LessWrong OpenAI-HuggingFace four-step manual reproduction','step':value['step'],'ordinal':value['ordinal'],'condition':'simulated peers only where the upstream conditional evaluation supplied them','campaign_runtime':'Registered independent-trial adapter; not generic Harbor scheduling.'},indent=2)+'\n')
        validate(folder,value,actor);records[actor]={str(p.relative_to(root)):digest(p) for p in sorted(folder.iterdir())}
    return records
def validate(folder,value,actor):
    folder=Path(folder);config=TaskConfig.model_validate(tomllib.loads((folder/'task.toml').read_text()))
    assert config.schema_version==SCHEMA and config.metadata['actor']==actor and config.metadata['step']==value['step']
    assert config.environment.network_mode=='no-network' and config.metadata['generic_harbor_scheduler'] is False
    assert (folder/'instruction.md').read_text().strip()==lab.task(value)
    return True
