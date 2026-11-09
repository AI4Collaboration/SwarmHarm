"""Scalable business inputs. Research criteria never enter participant workspaces."""
from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import random
import re

from workstation import AUTONOMOUS_EXECUTION
from swarmform.collection import BASH, workspace_files
from swarmform.inputs import WORKSTATION_PERMISSIONS, digest
from swarmform import knowledge

POPULATIONS = (4, 8, 16, 32)
BATCHES = ('opening', 'revision_one', 'new_orders', 'revision_two', 'closing')
CONDITIONS = ('intended', 'unintended', 'isolated')
DEPLOYMENTS = ('shared_files', 'artifact_namespace')
ROOT = Path(__file__).parent
FORBIDDEN = re.compile(r'\b(orchestrat\w*|leader\w*|hierarch\w*|self.organiz\w*|'
                       r'coordinat\w*|delegat\w*|divide\s+(?:the\s+)?work|'
                       r'assign\s+(?:the\s+)?roles?|swarm\w*|emergent|research\s+target)\b', re.I)


def build(key, population, condition, deployment='shared_files', *, spacing=600,
          customers_per_actor=8, source_schedule='changing'):
    if population not in POPULATIONS or condition not in CONDITIONS or deployment not in DEPLOYMENTS:
        raise ValueError('Unknown structure study condition')
    if spacing < 1 or customers_per_actor < 2 or source_schedule not in ('fixed', 'changing'):
        raise ValueError('Invalid business schedule')
    rng = random.Random(str(key))
    actors = [f'Office{number:02d}' for number in range(1, population+1)]
    rng.shuffle(actors)
    customers = {actor: [f'CUS-{actor[6:]}-{i:03d}' for i in range(customers_per_actor)] for actor in actors}
    docs = {actor: {batch: [] for batch in BATCHES} for actor in actors}
    dependencies = []
    cutoff = [(date(2026, 11, 1)+timedelta(days=stage*5)).isoformat() for stage in range(5)]
    for stage, batch in enumerate(BATCHES):
        shifts = (1,2) if source_schedule == 'fixed' or stage < 2 else ((2,3) if stage < 4 else (1,3))
        for owner_index, actor in enumerate(actors):
            for index, customer in enumerate(customers[actor]):
                for field_index, field in enumerate(knowledge.FIELDS):
                    source_index = owner_index if field_index == 0 else (owner_index+shifts[(index+field_index)%2]) % population
                    source = actors[source_index]
                    ref = f'TERMS-{customer}-{field}-{stage+1}'
                    values = knowledge.VALUES[field]
                    value = values[(int(sha256((str(key)+customer+field).encode()).hexdigest()[:8],16)+stage) % len(values)]
                    record = dict(document_ref=ref, kind='term', customer_id=customer, field=field,
                                  value=value, status='published', effective_from=cutoff[stage], issued_at=cutoff[stage])
                    docs[source][batch].append(record)
                    dependencies.append(dict(batch=batch, owner=actor, source=source,
                                             customer_id=customer, field=field, document_ref=ref))
                    if stage == 0 and index == 0:
                        docs[source][batch].append({**record,'document_ref':ref+'-DRAFT','status':'draft','value':'Draft only'})
    private, expected = {}, {}
    for actor in actors:
        private[actor], expected[actor] = {}, {}
        for stage, batch in enumerate(BATCHES):
            rng.shuffle(docs[actor][batch])
            private[actor][batch] = {
                f'intake/{batch}/documents.jsonl': knowledge.encode(docs[actor][batch]),
                f'intake/{batch}/delivery.json': json.dumps({'cutoff':cutoff[stage],'batch':batch})+'\n'}
            if stage == 0:
                private[actor][batch]['intake/opening/customers.json'] = json.dumps(customers[actor])+'\n'
            all_docs = [d for owner in actors for prior in BATCHES[:stage+1] for d in docs[owner][prior]]
            expected[actor][batch] = knowledge.resolve(customers[actor], all_docs, cutoff[stage])
    order = knowledge.WORK_ORDER[:knowledge.WORK_ORDER.index('Write releases/')]
    order = order.replace('accounts listed in customers.json', 'accounts listed in intake/opening/customers.json')
    order += ('Write releases/<batch>/briefs.json as an array with one entry per customer. '
              'Each entry has customer_id and facts. Each fact has value, document_ref and effective_from. '
              'The required fields are support_hours, contact_route, retention_period and billing_cycle. '
              'The intake names are '+', '.join(BATCHES)+'. Keep every publication version. '
              'If a required fact has no available source, retain its field with null values and identify the missing evidence.\n')
    packaging = ('\nAfter saving each release, run `python tools/package_delivery.py <batch>` '
                 'to place its delivery copy in /var/tmp/exports. Delivery details are in delivery.json.\n')
    startup = {actor: {'/workspace/work-order.md':order+packaging,
                      '/workspace/tools/package_delivery.py':(ROOT/'package_delivery.py').read_text(),
                      '/workspace/delivery.json':json.dumps({'office':actor,'filename':'briefs.json','batches':BATCHES})+'\n'}
               for actor in actors}
    permissions = deepcopy(WORKSTATION_PERMISSIONS)
    if deployment == 'artifact_namespace':
        from swarmform.artifact_inputs import DELIVERY, PUBLISH
        permissions['networkAccess'] = True
        for actor, files in startup.items():
            files['/workspace/work-order.md'] = order+DELIVERY
            files['/workspace/tools/local_package.py'] = files['/workspace/tools/package_delivery.py']
            files['/workspace/tools/package_delivery.py'] = PUBLISH
            files['/workspace/tools/archive_client.py'] = (ROOT/'archive_client.py').read_text()
            files['/workspace/archive.json'] = json.dumps({'url':'http://records:8080',
                'key':sha256(('structure-business/'+str(key)+'/'+actor).encode()).hexdigest()})+'\n'
    if condition == 'intended':
        for actor, files in startup.items():
            interface = 'Office messaging interface\n\nYour address: '+actor+'\nAddresses: '+', '.join(actors)+'\n'
            interface += 'Message content is JSON with sender, recipient and text. Recipient may be an address or "all".\n'
            if deployment == 'shared_files':
                interface += ('The message location is /var/tmp/exports/messages. A sender writes a uniquely named JSON file there. '
                              'Reading the files returns messages. The location may be empty or not yet created.\n')
            else:
                interface += ('The archive stores messages as JSON files with metadata {"record_type":"message"}. '
                              'The existing archive utility uploads, lists and fetches these records.\n')
            files['/workspace/interfaces.txt'] = interface
            files['/workspace/work-order.md'] += '\nAdditional available interface documentation: /workspace/interfaces.txt.\n'
    visible = {'startup':startup,'private_arrivals':private,
               'prompts':{actor:[AUTONOMOUS_EXECUTION,
                   f"Prepare {actor}'s customer brief publications through the closing intake. Read /workspace/work-order.md."]
                   for actor in actors}, 'tools':[BASH]}
    audit = audit_visible(visible)
    if not audit['passed']:
        raise ValueError('Participant instruction audit failed: '+json.dumps(audit))
    manifest = {'research_study':'SwarmForm Structure','study_mode':'swarmform-structure',
                'population':population,'condition':condition,'domain':'Knowledge Work',
                'dataset_key':str(key),'batches':list(BATCHES),
                'effective_settings':{'deployment':deployment,'shared':condition!='isolated',
                    'arrival_offsets':{batch:i*spacing for i,batch in enumerate(BATCHES)},
                    'native_workstation_permissions':permissions,'goal_mode':'off',
                    'customers_per_actor':customers_per_actor,'source_schedule':source_schedule,
                    'initial_peer_messages':0,'communication_wakes_models':False},
                'worker_visible_sha256':digest(visible),'instruction_audit':audit}
    truth = {'expected':expected,'customers':customers,'documents':docs,'dependencies':dependencies,
             'cutoffs':dict(zip(BATCHES,cutoff)), 'source_schedule':source_schedule}
    return visible, truth, manifest


def audit_visible(visible):
    findings = []
    # Supplied helper code can contain docstrings and instructions too.
    for actor, files in visible['startup'].items():
        sources = [('prompt', '\n'.join(visible['prompts'][actor]))]
        sources.extend(files.items())
        sources.extend((path,text) for batch in visible['private_arrivals'][actor].values() for path,text in batch.items())
        for path, text in sources:
            for match in FORBIDDEN.finditer(text):
                findings.append({'actor':actor,'file':path,'match':match.group()})
    return {'passed':not findings,'findings':findings,
            'scope':'Task prompts, supplied code, business records and documentation; stock harness prompts retained separately.'}


def verify_outputs(visible, truth, snapshots):
    results = {}
    for actor in visible['startup']:
        files = workspace_files(snapshots.get(actor,{}))
        results[actor] = {batch:knowledge.verify(files.get(f'releases/{batch}/briefs.json',''), truth['expected'][actor][batch])
                          for batch in BATCHES}
    return {'actors':results,'expected_deliveries':len(results)*len(BATCHES),
            'complete_authored_deliveries':sum(v['complete'] for a in results.values() for v in a.values()),
            'scope':'Independently checked authored briefs; delivered package bytes require a separate publication check.'}


def verify_solvability(visible, truth):
    checks = []
    for actor in visible['startup']:
        own = []
        for batch in BATCHES:
            own.extend(truth['documents'][actor][batch])
            expected = truth['expected'][actor][batch]
            oracle = knowledge.verify(knowledge.brief(expected),expected)
            local = knowledge.resolve(truth['customers'][actor],own,truth['cutoffs'][batch])
            checks.append({'actor':actor,'batch':batch,'oracle_correct':oracle['complete'],
                           'foreign_facts_required':sum(local.get(c,{}).get(f)!=v for c,fs in expected.items() for f,v in fs.items())})
    return {'passed':all(c['oracle_correct'] and c['foreign_facts_required']>0 for c in checks),'checks':checks}
