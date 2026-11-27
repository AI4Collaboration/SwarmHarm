"""Resolve a specified booking edition from station originals and version-pinned project inputs."""
import hashlib
from pathlib import Path


def booking_input(booking, edition, reference_program):
    kit = Path('/workspace/bookings') / booking / edition
    filename = 'survey.rst' if booking == 'crossing' else 'survey.md'
    names = ('job.json', filename, 'calibration.svg')
    available = {name: (kit / name).read_bytes() for name in names if (kit / name).is_file()}
    missing = [name for name in names if name not in available]
    if missing:
        from field_reader import catalog_versions, selected_inputs
        workspace = Path('/workspace')
        catalog = catalog_versions(workspace)
        paths = {name: (kit / name).relative_to(workspace).as_posix() for name in missing}
        for path in paths.values():
            if path not in catalog:
                raise ValueError(f'Incomplete booking kit: {path} is unavailable at this station or in the project')
        pins = {path: catalog[path] for path in paths.values()}
        with selected_inputs(paths.values(), pins) as root:
            available.update({name: (root / path).read_bytes() for name, path in paths.items()})
    files = {name: available[name].decode('utf-8') for name in names}
    hashes = {name: hashlib.sha256(available[name]).hexdigest() for name in names}
    return {'booking': booking, 'edition': edition, 'files': files, 'sha256': hashes,
            'reference_program': reference_program}
