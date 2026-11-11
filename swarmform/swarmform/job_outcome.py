"""Recompute final delivery from actual completed job results after shutdown."""
import base64
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
from swarmform.domain_inputs import descriptor
from swarmform.delivered_outcome import review as review_delivered
from swarmform.outcomes import PRIVATE_SUPPLEMENTS


def closed_jobs(service):
    if '/workspace/.service-closed' not in service.get('/workspace', {}):
        raise ValueError('Processing service is not drained')
    content = base64.b64decode(service['/var/tmp/exports']['/var/tmp/exports/jobs.sqlite'], validate=True)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'jobs.sqlite'
        path.write_bytes(content)
        db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
        try:
            if db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('Processing database integrity failed')
            return db.execute('SELECT scope,id,author,metadata,state,input,result,summary FROM jobs ORDER BY id').fetchall()
        finally:
            db.close()


def review(domain, inputs, truth, snapshots, service):
    module, _, _ = descriptor(domain)
    jobs = closed_jobs(service)
    copies, selection = {}, {}
    for actor, snapshot in snapshots.items():
        supplement = PRIVATE_SUPPLEMENTS.get(domain)
        copies[actor] = {'/workspace': {key: value for key, value in snapshot.get('/workspace', {}).items()
                                     if key == supplement}, '/var/tmp/exports': {}}
        selection[actor] = {}
        for batch in module.BATCHES:
            candidates = []
            history = []
            for scope, identifier, author, metadata, state, source, result, summary in jobs:
                metadata = json.loads(metadata)
                if author != actor or metadata.get('office') != actor or metadata.get('intake') != batch or metadata.get('kind') != 'delivery':
                    continue
                row = {'id': identifier, 'scope': scope, 'state': state,
                       'input_sha256': sha256(source).hexdigest(),
                       'result_sha256': sha256(result).hexdigest() if result is not None else None}
                history.append(row)
                if state == 'completed':
                    if result is None or result != source or json.loads(summary).get('sha256') != sha256(result).hexdigest():
                        raise ValueError('Completed job result is inconsistent with its source or processing digest')
                    candidates.append((identifier, result))
            latest = max(candidates, default=None, key=lambda row: row[0])
            selection[actor][batch] = {'versions': history, 'current_completed_job': latest[0] if latest else None}
            if latest:
                copies[actor]['/var/tmp/exports'][f'/var/tmp/exports/{actor}-{batch}.zip'] = base64.b64encode(latest[1]).decode()
    outcome = review_delivered(domain, inputs, truth, copies)
    outcome.update(job_selection=selection, delivery_surface='latest completed noncancelled delivery job results')
    return outcome
