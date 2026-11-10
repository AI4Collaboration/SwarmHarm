"""Validate the named primary delivery and optional authored attachments."""
from hashlib import sha256
import json
from pathlib import PurePosixPath


def validate_archive_layout(archive, filename, *, allow_attachments=False):
    names = archive.namelist()
    required = {filename, 'manifest.json'}
    if len(names) != len(set(names)) or not required.issubset(names):
        raise ValueError('Invalid archive layout')
    extra = set(names) - required
    if not allow_attachments and extra:
        raise ValueError('Invalid archive layout')
    if any(entry.file_size > 1_000_000 for entry in archive.infolist()):
        raise ValueError('Archive entry is too large')
    if not allow_attachments:
        return
    manifest = json.loads(archive.read('manifest.json'))
    attachments = manifest.get('attachments', {})
    if not isinstance(attachments, dict) or set(attachments) != extra:
        raise ValueError('Attachment list differs from archive')
    for name in sorted(extra):
        path = PurePosixPath(name)
        if (len(path.parts) < 2 or path.parts[0] != 'attachments'
                or '..' in path.parts or path.as_posix() != name or '\\' in name
                or name.endswith('/')):
            raise ValueError('Invalid attachment name')
        if sha256(archive.read(name)).hexdigest() != attachments[name]:
            raise ValueError('Attachment bytes differ from manifest digest')
