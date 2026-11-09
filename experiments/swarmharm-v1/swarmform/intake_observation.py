"""Arrival-awareness receipts from protected process reads; never completion evidence."""
import base64
from hashlib import sha256
import json
from pathlib import Path
from swarmform.read_observer import observed_reads


def intake_read_receipts(reference, expected, seen_blobs):
    """Find exact nonempty reads of delivered paths in an immutable observation.

    A receipt establishes that actor-authored code accessed this delivered file.
    It does not assert a full read, model comprehension, or completed business work.
    """
    path = Path(reference['path'])
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != reference['sha256']:
        raise ValueError('Command observation digest changed')
    manifest = json.loads(raw)
    receipts = {}
    for name, item in manifest['files'].items():
        digest = item['sha256']
        if digest in seen_blobs:
            continue
        blob = path.parent / item['blob']
        if blob.resolve().parent != (path.parent / 'blobs').resolve():
            raise ValueError('Command observation blob outside archive')
        data = blob.read_bytes()
        if sha256(data).hexdigest() != digest:
            raise ValueError('Command observation blob changed')
        seen_blobs.add(digest)
        for read in observed_reads(data.decode(errors='strict')):
            original = expected.get(read['path'])
            content = base64.b64decode(read['data_base64'], validate=True)
            if original is None or not content or content not in original:
                continue
            receipts.setdefault(read['path'], {
                'observation': str(path), 'observation_sha256': reference['sha256'],
                'blob': item['blob'], 'blob_sha256': digest, 'line': read['line'],
                'read_at_unix': read['at_unix'], 'bytes_read': len(content),
                'read_sha256': read['sha256'], 'delivered_file_sha256': sha256(original).hexdigest(),
                'scope': 'delivered_file_access_not_completion'})
    return receipts
