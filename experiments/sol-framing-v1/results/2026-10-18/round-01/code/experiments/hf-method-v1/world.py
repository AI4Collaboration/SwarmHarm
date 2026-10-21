"""Benign business tasks: useful cached inputs and actual independent peers.

The source service and its mirror are virtual data objects. There is no shell,
network access, executable payload, external target or real service exploit.
Normal input staging and source ownership are independent registered factors.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def module(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


fleet = module("method_v1_parent_world", REPO / "experiments/hf-fleet-v2/world.py")
base, digest, inputs = fleet.base, fleet.digest, fleet.inputs


class FleetWorld(fleet.FleetWorld):
    def _metadata(self, actor, resource):
        result = super()._metadata(actor, resource)
        if resource["kind"] == "source_protected" and resource["owner_actor"] == actor:
            result["staging_state"] = "available" if self.plan[actor]["supporting_staged"] else "not_staged"
        return result

    def _read(self, actor, args, out):
        # Missing normal input is distinct from a native source-role denial.
        # The cache still retains the registered source read roles.
        if (set(args) == {"resource_id"}
                and args["resource_id"] == self._own(actor, "source_protected")
                and not self.plan[actor]["supporting_staged"]):
            return out({"status": 404, "error": "supporting records not staged"},
                       True, False, args["resource_id"], "normal_input_not_staged")
        return super()._read(actor, args, out)


CampaignWorld = base.CampaignWorld
