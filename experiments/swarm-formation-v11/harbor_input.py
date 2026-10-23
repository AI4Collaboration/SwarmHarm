"""Create and validate one Harbor 1.4 package for each independent context."""

from hashlib import sha256
import json
from pathlib import Path
import tomllib

from harbor.models.task.config import TaskConfig

import lab


SCHEMA = "1.4"
IMAGE = "swarmharm-harbor-base:20261021"


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def toml(item, phase, actor):
    return f'''schema_version = "{SCHEMA}"

[task]
name = "swarmharm/formation-{item['review_id'].lower()}"
version = "2.0"
description = "Synthetic supplier review in a persistent business cache"
keywords = ["procurement", "synthetic", "business-process", "multi-agent"]

[[task.authors]]
name = "SwarmHarm"

[metadata]
family = "swarm-formation-v11"
phase = "{phase}"
actor = "{actor}"
review_id = "{item['review_id']}"
arrival_index = {item['arrival']}
execution_adapter = "experiments/swarm-formation-v11/run.py"
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


def validate(folder, item, phase, actor):
    folder = Path(folder)
    config = TaskConfig.model_validate(tomllib.loads((folder / "task.toml").read_text()))
    assert config.schema_version == SCHEMA
    assert config.metadata["family"] == "swarm-formation-v11"
    assert config.metadata["phase"] == phase and config.metadata["actor"] == actor
    assert config.metadata["review_id"] == item["review_id"]
    assert config.metadata["arrival_index"] == item["arrival"]
    assert config.environment.network_mode == "no-network"
    assert (folder / "instruction.md").read_text().strip() == lab.task(item)
    return True


def write(root, plan):
    root = Path(root)
    records = {}
    for phase, actors in plan.items():
        records[phase] = {}
        for actor, item in actors.items():
            folder = root / phase / actor
            folder.mkdir(parents=True)
            (folder / "instruction.md").write_text(lab.task(item) + "\n")
            (folder / "task.toml").write_text(toml(item, phase, actor))
            (folder / "provenance.json").write_text(json.dumps({
                "source": "Maintained synthetic supplier-review records",
                "family": "swarm-formation-v11",
                "phase": phase,
                "actor": actor,
                "review_id": item["review_id"],
                "arrival_index": item["arrival"],
                "campaign_runtime": "Registered SwarmHarm adapter; not generic Harbor scheduling.",
            }, indent=2) + "\n")
            validate(folder, item, phase, actor)
            records[phase][actor] = {
                str(path.relative_to(root)): digest(path) for path in sorted(folder.iterdir())
            }
    return records


def initial_audit(root, plan):
    root = Path(root)
    result = {}
    for phase, actors in plan.items():
        result[phase] = {}
        for actor, item in actors.items():
            validate(root / phase / actor, item, phase, actor)
            instruction = (root / phase / actor / "instruction.md").read_text().strip()
            result[phase][actor] = lab.initial(actors, actor, instruction)
    return result
