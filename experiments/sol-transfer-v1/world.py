"""Conditional transfer of genuine archived posts, never a fake live peer.

The only manipulated source is a read-only historical reference. It grants no
new role, does not contain the new task's private answer, and is not a grader.
"""
from copy import deepcopy
from pathlib import Path
import importlib.util

REPO = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


parent = module("transfer_parent", REPO / "experiments/sol-handoff-v1/world.py")
base, digest, inputs = parent.base, parent.digest, parent.inputs


class FleetWorld(parent.FleetWorld):
    def add_actor(self, actor, task_id=None, wave=None):
        super().add_actor(actor, task_id, wave)
        condition = self.plan[actor].get("archive_condition")
        if condition is not None:
            rid = self._id(actor, "archive_reference")
            self.resources[rid] = {"resource_id": rid, "kind": "archive_reference",
                "owner_actor": actor, "owner_role": "archive-service", "version": 1,
                "name": "Archived operations thread", "scope": "task",
                "content": {"type": "historical_reference", "live_peer": False,
                    "messages": deepcopy(self.fixtures["archive_threads"][condition])},
                "author_actor_id": None, "author_event_id": None}
        return self.describe_task(actor)

    def describe_task(self, actor):
        native = super().describe_task(actor)
        note = self.resources.get(self._id(actor, "archive_reference"))
        if note is not None:
            native["reference_material"] = [self._metadata(actor, note)]
        return native

    def _metadata(self, actor, resource):
        result = super()._metadata(actor, resource)
        if resource["kind"] == "archive_reference":
            result.update(read_roles=["assigned-analyst"], write_roles=[],
                          origin="historical_operations_thread", live_peer=False)
        return result

    def audit_snapshot(self):
        result = super().audit_snapshot()
        result["containment"]["archived_reference_is_readonly_not_live_peer"] = True
        return result


CampaignWorld = base.CampaignWorld
