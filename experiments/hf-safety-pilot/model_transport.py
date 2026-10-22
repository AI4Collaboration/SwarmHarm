"""Compatibility name for the single live inference route.

All new and current experiments use AxonHub. Historical job directories keep
their original transport snapshots and are not rewritten.
"""
import importlib.util
from pathlib import Path

_path = Path(__file__).with_name("axonhub_transport.py")
_spec = importlib.util.spec_from_file_location("swarmharm_axonhub_transport", _path)
_impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impl)

MODEL = _impl.MODEL


def configure(model, base_url="https://lmportal.iefbr14.xyz/v1", key_env="AXONHUB_API_KEY",
              key_file=None, max_output_tokens=None):
    global MODEL
    _impl.configure(model, base_url, key_env=key_env, key_file=key_file,
                    max_output_tokens=max_output_tokens)
    MODEL = _impl.MODEL


def call(body, directory, label, timeout=150):
    _impl.MODEL = MODEL
    return _impl.call(body, directory, label, timeout)


def output_text(response):
    return _impl.output_text(response)


def save(path, value):
    """Preserve the legacy transport helper used by frozen pilot entry points."""
    return _impl.save(path, value)
