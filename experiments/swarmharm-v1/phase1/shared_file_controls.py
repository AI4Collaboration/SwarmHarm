"""Offline checks of real project-file operations, never a subject protocol."""
from copy import deepcopy
import shlex

from phase1 import carrier_evidence, lab, shared_files


def evaluate(plan, *, record=None):
    if shared_files.descriptor(plan) is None:
        raise ValueError('Project-file control requires its registered descriptor')
    world = lab.World(deepcopy(plan))
    result = None
    try:
        world.prepare_workstations()
        actors = list(plan)

        def shell(actor, command):
            reply = world.call(actor, len(world.events) + 1, 'bash', {'command': command})
            if reply.get('status') != 200 or reply.get('exit_code') != 0:
                raise RuntimeError('Project-file operation failed: ' + repr(reply))
            return reply['stdout']

        paths = []
        for index, actor in enumerate(actors):
            root = shared_files.ROOTS[index % len(shared_files.ROOTS)]
            folder = root + f'/revision-{index}/working'
            path = folder + '/summary.txt'
            paths.append(path)
            shell(actor, 'mkdir -p ' + shlex.quote(folder + '/draft')
                  + '; printf %s ' + shlex.quote(f'Offline file verification {index}.\n')
                  + ' > ' + shlex.quote(path))
        for index, actor in enumerate(actors):
            path = paths[(index + 1) % len(actors)]
            shell(actor, 'find ' + ' '.join(shared_files.ROOTS) + ' -print; cat ' + shlex.quote(path))
        snapshot = world.snapshot()
        evidence = carrier_evidence.replay(plan, world.events,
            snapshot['engineering_carrier_probe'], snapshot['file_workspace'])
        observed = evidence['foreign_observations']
        contents = [r for r in observed if r['feature'] == 'shared_file_body']
        if len(contents) != len(actors) or {r['path'] for r in contents} != set(paths):
            raise RuntimeError('Project-file reads do not match the authored files')
        result = {'revision': shared_files.descriptor(plan)['revision'], 'workstations': len(actors),
                  'roots': list(shared_files.ROOTS), 'file_reads': contents,
                  'directory_name_reads': sum(r['feature'] == 'shared_entry_name'
                                              and r['entry_kind'] == 'directory' for r in observed),
                  'native_communication_claim': False, 'model_calls': 0}
    finally:
        world.close()
        if record is not None:
            record('project_files', world.snapshot())
    result['cleanup'] = deepcopy(world.cleanup)
    return result
