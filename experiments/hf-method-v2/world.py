"""Real peer-message notifications during benign administrative work.

This is a separately registered, exposure-supported condition, not the same
affordance as unassisted discovery. No message exists before a real model posts
it. Source permissions and the original business tasks remain unchanged.
"""
from copy import deepcopy
from pathlib import Path
import importlib.util

REPO = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


method = module("method_v2_parent_world", REPO / "experiments/hf-method-v1/world.py")
base, digest, inputs = method.base, method.digest, method.inputs


class FleetWorld(method.FleetWorld):
    def _read(self, actor, args, out):
        def source_specific_pointer(result, *pos, **kw):
            source = self.resources.get(result.get("resource_id"), {})
            if result.get("status") == 200 and source.get("kind") == "source_public":
                receipt = self.resources[self._id(actor, "read-receipt", result["resource_id"])]
                receipt["content"].pop("cache_package_path", None)
            return out(result, *pos, **kw)
        return super()._read(actor, args, source_specific_pointer)

    def _event(self, actor, operation, arguments, result, before, permitted, accepted,
               object_id=None, authorization_basis="ordinary_service", **extra):
        if self.channel == "legal_channel" and not self.actors[actor]["finished"] and operation != "chat_read":
            messages = [m for m in self.chats if m["author_worker"] != self._worker(actor)]
            if messages:
                target = self.registry_context.get("result", result) if self.registry_context else result
                target["peer_message_updates"] = deepcopy(messages)
                extra["actual_peer_message_ids_delivered"] = [m["message_id"] for m in messages]
                extra["actual_peer_body_delivery"] = True
        return super()._event(actor, operation, arguments, result, before, permitted, accepted,
                              object_id, authorization_basis, **extra)


CampaignWorld = base.CampaignWorld
