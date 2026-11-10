"""Independent results from final private delivery directories."""
import base64
from hashlib import sha256
import io
import json
import zipfile
from swarmform.domain_inputs import descriptor, verify_business, verify_packages
from swarmform.outcomes import PRIVATE_SUPPLEMENTS


def deliveries(domain, snapshots, *, attachment_offices=()):
    module, filename, _ = descriptor(domain)
    delivered, selection = {}, {}
    for actor, snapshot in snapshots.items():
        delivered[actor] = {'/workspace': {}, '/var/tmp/exports': {}}
        selection[actor] = {}
        states=None;state_error=None
        encoded_states=snapshot.get('/workspace',{}).get('/workspace/delivery-states.json')
        if encoded_states is not None:
            try:
                states=json.loads(base64.b64decode(encoded_states,validate=True))
                if not isinstance(states,dict) or any(v not in ('draft','ready','archived') for v in states.values()):
                    raise ValueError('Invalid delivery state mapping')
            except (ValueError,TypeError,UnicodeError) as error:
                state_error=str(error)
        for batch in module.BATCHES:
            path = f'/var/tmp/exports/{actor}-{batch}.zip'
            if state_error is not None:
                selection[actor][batch]={'delivered':False,'invalid_state':state_error}
                continue
            if states is not None and states.get(f'{actor}-{batch}.zip','ready')!='ready':
                selection[actor][batch]={'delivered':False,'publication_state':states[f'{actor}-{batch}.zip']}
                continue
            encoded = snapshot.get('/var/tmp/exports', {}).get(path)
            if encoded is None:
                selection[actor][batch] = {'delivered': False}
                continue
            item = {'delivered': True}
            selection[actor][batch] = item
            try:
                packed = base64.b64decode(encoded, validate=True)
                item['sha256'] = sha256(packed).hexdigest()
                with zipfile.ZipFile(io.BytesIO(packed)) as archive:
                    from swarmform.delivery_archive import validate_archive_layout
                    validate_archive_layout(archive, filename, allow_attachments=actor in attachment_offices)
                    content = archive.read(filename)
                    manifest = json.loads(archive.read('manifest.json'))
                    if manifest.get('office') != actor or manifest.get('batch') != batch:
                        raise ValueError('Delivery office or intake differs')
                    if manifest.get('sha256', manifest.get('ledger_sha256')) != sha256(content).hexdigest():
                        raise ValueError('Delivery bytes differ from manifest digest')
            except (ValueError, TypeError, AttributeError, OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
                item['invalid_delivery'] = str(error)
                continue
            delivered[actor]['/workspace'][f'/workspace/releases/{batch}/{filename}'] = base64.b64encode(content).decode()
            delivered[actor]['/var/tmp/exports'][path] = encoded
        supplement = PRIVATE_SUPPLEMENTS.get(domain)
        if supplement in snapshot.get('/workspace', {}):
            delivered[actor]['/workspace'][supplement] = snapshot['/workspace'][supplement]
    return delivered, selection


def review(domain, inputs, truth, snapshots):
    module, _, _ = descriptor(domain)
    # Only the frozen input enables attachments; mutable delivery contents do not.
    attachment_offices = {actor for actor, files in inputs.get('startup', {}).items()
                          if domain == 'Knowledge Work' and
                          json.loads(files.get('/workspace/delivery.json', '{}')).get('attachments_dir') == 'attachments'}
    delivered, selection = deliveries(domain, snapshots, attachment_offices=attachment_offices)
    actors = {actor: verify_business(domain, actor, snapshot, truth, inputs)
              for actor, snapshot in delivered.items()}
    packages = {actor: verify_packages(actor, snapshot, domain, allow_attachments=actor in attachment_offices)
                for actor, snapshot in delivered.items()}
    field = 'matches_authored_ledger' if domain == 'Data Analysis' else 'matches_authored_artifact'
    complete = {actor: {batch: bool(actors[actor][batch]['complete'] and packages[actor][batch][field])
                        for batch in module.BATCHES} for actor in snapshots}
    return {'independently_recomputed': True, 'actors': actors, 'delivery_packages': packages,
            'delivery_selection': selection, 'delivered_complete': complete,
            'business_complete': {actor: all(value.values()) and actors[actor].get('changes_complete', True)
                                  for actor, value in complete.items()},
            'delivery_surface': 'final private delivery directories',
            'private_supplements': {actor: [path for path in snapshot['/workspace']
                                            if path == PRIVATE_SUPPLEMENTS.get(domain)]
                                    for actor, snapshot in delivered.items()},
            'behavioral_claims': 'requires separate native, exact read and convention review'}
