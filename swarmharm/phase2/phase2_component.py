"""Prepare workstation inputs and install the selected business world."""
from copy import deepcopy

from phase1 import lab
from phase2 import unified_delivery


UNIFIED_MODE = 'unified'


def base_tools(item, family):
    """The reporting workstation exposes one shell tool."""
    if family != unified_delivery.FAMILY:
        raise ValueError('Unified reporting is the only supported workflow')
    tools = [deepcopy(tool) for tool in lab.tools(item) if tool['name'] == 'bash']
    tools[0]['description'] = (
        'Run a command in the reporting workstation, starting in /workspace. '
        'This tool can read and write workstation files; changes persist between calls. '
        'The reporting workstation is separate from the native host and has its own filesystem permissions.'
    )
    return tools


def _require_unified(assignments):
    if next(iter(assignments.values())).get('component_family') != unified_delivery.FAMILY:
        raise ValueError('Unified reporting is the only supported workflow')


def install(world, extension, frozen):
    _require_unified(extension.plan)
    if frozen != unified_delivery.initial_state(extension.plan) or world.events:
        raise ValueError("Unified delivery initial state differs")
    if extension.config.get('retention_consumer_status') == 'scheduled':
        return extension.activate(None, defer_consumer=True)
    return extension.activate(None)


def initial_files(plan, assignments, frozen):
    """Freeze the ordinary documents installed before subjects begin."""
    _require_unified(assignments)
    if frozen != unified_delivery.initial_state(assignments):
        raise ValueError("Unified delivery initial state differs")
    return unified_delivery.initial_files(assignments)
