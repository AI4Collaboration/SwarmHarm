"""Harbor 1.4 packages for the registered concurrent native adapter."""
import json
from pathlib import Path
import tomllib
from design import IMAGE,TASK,initial_files


def emit(root,fixture):
    root=Path(root)
    for actor in fixture['actors']:
        folder=root/actor;folder.mkdir(parents=True,exist_ok=False)
        (folder/'instruction.md').write_text(TASK+'\n')
        (folder/'task.toml').write_text(f'''schema_version = "1.4"
[task]
name = "swarmharm/discovery-{actor}"
version = "1.0"
description = "Purchase quotation review"
keywords = ["procurement", "synthetic"]
[[task.authors]]
name = "SwarmHarm"
[metadata]
family = "swarm-discovery-v2"
execution_adapter = "experiments/swarm-discovery-v2/run.py"
generic_harbor_scheduler = false
[agent]
timeout_sec = 1200
user = "65534"
[verifier]
timeout_sec = 60
user = "root"
[environment]
docker_image = "{IMAGE}"
network_mode = "no-network"
cpus = 1
memory_mb = 256
storage_mb = 128
''')
        workspace=folder/'environment'/'workspace';workspace.mkdir(parents=True)
        for path,text in initial_files(fixture,actor).items():(workspace/Path(path).name).write_text(text)
        (folder/'provenance.json').write_text(json.dumps({'source':'Synthetic purchase requests and quotations',
            'business_rule_reference':'https://docs.peppol.eu/poacc/billing/3.0/2024-Q2/syntax/ubl-invoice/cac-InvoiceLine/cbc-LineExtensionAmount/',
            'adaptation':'Integer-cent line amounts, base quantity one, no charges, allowances or VAT; quotation confirmation is a synthetic source identifier. This is not an original Peppol task.',
            'execution':'Concurrent native Docker adapter with host document/review tools; not generic Harbor model execution.',
            'subject_files':['request.json','WORKFLOW.md']},indent=2)+'\n')


def validate(root):
    from harbor.models.task.config import TaskConfig
    rows=[]
    for path in sorted(Path(root).glob('*/task.toml')):
        config=TaskConfig.model_validate(tomllib.loads(path.read_text()))
        assert config.schema_version=='1.4'
        assert config.metadata['generic_harbor_scheduler'] is False
        assert config.environment.network_mode=='no-network'
        assert (path.parent/'instruction.md').read_text().strip()==TASK
        rows.append(str(path.parent.name))
    assert rows,'no tasks'
    return rows

if __name__=='__main__':
    import sys
    print(json.dumps({'validated_harbor_inputs':validate(sys.argv[1]),'harbor_version':'0.24.0','generic_harbor_execution':False}))
