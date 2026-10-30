"""Create and validate one Harbor 1.4 package for each continuous-rollout context."""

from hashlib import sha256
import json
from pathlib import Path
import tomllib

from harbor.models.task.config import TaskConfig

from phase1 import lab
SCHEMA = "1.4"
IMAGE = "swarmharm-harbor-base:20261021"
ACTOR_TIMEOUT_SECONDS = 3600


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def toml(item, phase, actor):
    domain = item["domain"]
    return f'''schema_version = "{SCHEMA}"

[task]
name = "swarmharm/rollout-{item['batch_id'].lower()}"
version = "2.0"
description = "Concurrent {domain} rollout in a persistent business system"
keywords = ["{domain.lower().replace(' ', '-')}", "synthetic", "business-process", "swarm"]

[[task.authors]]
name = "SwarmHarm"

[metadata]
family = "swarmharm-v1"
phase = "{phase}"
actor = "{actor}"
batch_id = "{item['batch_id']}"
start_group = {item['start_group']}
execution_adapter = "experiments/swarmharm-v1/run.py"
generic_harbor_scheduler = false

[agent]
timeout_sec = {ACTOR_TIMEOUT_SECONDS}
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
    assert config.metadata["family"] == "swarmharm-v1"
    assert config.metadata["phase"] == phase and config.metadata["actor"] == actor
    assert config.metadata["batch_id"] == item["batch_id"]
    assert config.metadata["start_group"] == item["start_group"]
    assert config.environment.network_mode == "no-network"
    assert (folder / "instruction.md").read_text().strip() == (item.get("component_task") or lab.task(item))
    return True


def write(root, plan):
    root = Path(root)
    records = {}
    for phase, actors in plan.items():
        records[phase] = {}
        for actor, item in actors.items():
            folder = root / phase / actor
            folder.mkdir(parents=True)
            (folder / "instruction.md").write_text((item.get("component_task") or lab.task(item)) + "\n")
            (folder / "task.toml").write_text(toml(item, phase, actor))
            (folder / "provenance.json").write_text(json.dumps({
                "source": f"Maintained synthetic {item['domain']} records",
                "family": "swarmharm-v1",
                "scenario": item["scenario"],
                "domain": item["domain"],
                "phase": phase,
                "actor": actor,
                "batch_id": item["batch_id"],
                "review_ids": item["review_ids"],
                "start_group": item["start_group"],
                "rollout_runtime": "Registered SwarmHarm adapter; not generic Harbor scheduling.",
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
