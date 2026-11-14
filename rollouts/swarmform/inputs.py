from hashlib import sha256

import json

WORKSTATION_PERMISSIONS = {'type': 'workspaceWrite', 'networkAccess': False,
    'writableRoots': ['/workspace', '/var/tmp/exports', '/tmp', '/private/tmp']}

def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
