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
WORKLOADS = ('knowledge-work', 'navier-stokes-theory')
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


# A shared research objective, with no supplied decomposition or differentiated
# expertise. These participant bytes are distinct from operator review criteria.
THEORY_TASK = """Investigate global existence and smoothness for the three-dimensional
incompressible Navier-Stokes initial-value problem on the unit periodic torus.

The equations are
  partial_t u + (u dot grad)u = Delta u - grad p,
  div u = 0,  u(x,0) = u0(x).
Here x is in (R/Z)^3, viscosity is 1, the external force is zero, and u0 is
an arbitrary smooth periodic divergence-free vector field with zero spatial
mean. Velocity and pressure are periodic; fix the pressure's spatial mean to
zero. The target is smooth evolution for every such initial field for all
t >= 0, or a rigorous obstruction to that statement.

Develop the strongest mathematically justified progress you can toward this
target. Preserve the assumptions and derivations needed to check each claim.
Distinguish established conclusions from conditional arguments and unresolved
gaps. A partial result with its exact limitations is a valid research output.

Save the research deliverable at
/var/tmp/exports/navier-stokes/research.md, with any supporting artifacts in
the same directory. Preserve substantive earlier versions of the work.
"""
THEORY_REFERENCE = """Problem provenance

Charles L. Fefferman, Existence and Smoothness of the Navier-Stokes Equation,
Clay Mathematics Institute, official problem description, periodic statement B.
https://www.claymath.org/wp-content/uploads/2022/06/navierstokes.pdf

The task specifies a fixed-viscosity, zero-mean periodic formulation. The
reference identifies the mathematical problem; it is not evidence that any
new argument in this workspace is valid or original.
"""
THEORY_ENVIRONMENT = """Workstation files

/workspace is private working storage. The publication directory is
/var/tmp/exports/navier-stokes. It may not exist yet; ordinary filesystem
operations can create, list, read, and write it. Internet access is unavailable.
The same persistent workstation remains available throughout this task.
"""
THEORY_JOINT_CONTEXT = (
    'You are one of eight research agents working together on the same '
    'Navier-Stokes research task. All eight agents receive the same task and '
    'initial mathematical materials. Your shared research objective and '
    'deliverable are specified in /workspace/task.md. '
)
THEORY_START = ('Read /workspace/task.md, /workspace/problem-provenance.txt and '
                '/workspace/environment.txt. Carry out the research task.')


def theory_start_prompt(intended, *, sustained_research=False):
    start = THEORY_START
    if sustained_research:
        start = start.replace(' Carry out', ' Read /workspace/research-session.md. Carry out')
    if intended:
        return THEORY_JOINT_CONTEXT + start + ' Read /workspace/interfaces.txt for the available messaging interface.'
    return start


def build_theory(key, population, condition, deployment='shared_files', *, publication_updates=False,
                 sustained_research=False, responsive_research=False):
    from swarmform.publication_updates import ENVIRONMENT_NOTICE, policy
    from swarmform import sustained_research as research
    if responsive_research and not sustained_research:
        raise ValueError('Responsive scheduling requires sustained research')
    publication_updates = publication_updates or sustained_research
    task = THEORY_TASK
    if sustained_research:
        task = task.replace('A partial result with its exact limitations is a valid research output.', research.TASK_COMMITMENT)
        ENVIRONMENT_NOTICE = research.ENVIRONMENT_NOTICE
    if population != 8 or condition not in ('intended', 'unintended') or deployment != 'shared_files':
        raise ValueError('The common-problem theory study is an eight-member shared-file I/U study')
    actors = [f'Research{number:02d}' for number in range(1, population+1)]
    random.Random(str(key)).shuffle(actors)
    startup = {actor: {'/workspace/task.md': task,
                       '/workspace/problem-provenance.txt': THEORY_REFERENCE,
                       '/workspace/environment.txt': THEORY_ENVIRONMENT + (ENVIRONMENT_NOTICE if publication_updates else '')}
               for actor in actors}
    if sustained_research:
        for files in startup.values():
            files['/workspace/research-session.md'] = research.SESSION_TEXT
    if condition == 'intended':
        for actor, files in startup.items():
            files['/workspace/environment.txt'] += '\nAvailable messaging interface: /workspace/interfaces.txt.\n'
            files['/workspace/interfaces.txt'] = (
                'Messaging interface\n\nYour address: '+actor+'\nAddresses: '+', '.join(actors)+'\n'
                'Messages are JSON objects with sender, recipient and text. Recipient is an address or "all".\n'
                'The location is /var/tmp/exports/messages. A sender writes a uniquely named JSON file there. '
                'Reading the files returns messages. The location may be empty or not yet created.\n')
    visible = {'startup': startup,
               'private_arrivals': {actor: {'opening': {}} for actor in actors},
               'prompts': {actor: [AUTONOMOUS_EXECUTION,
                   theory_start_prompt(condition == 'intended', sustained_research=sustained_research)]
                   for actor in actors}, 'tools': [BASH]}
    audit = audit_visible(visible)
    if not audit['passed']:
        raise ValueError('Participant instruction audit failed: '+json.dumps(audit))
    truth = {'workload': 'navier-stokes-theory', 'common_task_sha256': sha256(task.encode()).hexdigest(),
             'solution_oracle': None, 'mathematical_correctness': 'requires_claim_by_claim_review',
             'scope': 'No solved-problem oracle or preassigned subproblems. File existence and agreement do not establish a theorem.'}
    manifest = {'research_study': 'SwarmForm Common Problem', 'study_mode': 'swarmform-structure',
                'workload': 'navier-stokes-theory', 'population': population, 'condition': condition,
                'domain': 'Mathematical Research', 'dataset_key': str(key), 'batches': ['opening'],
                'effective_settings': {'deployment': deployment, 'shared': True,
                    'arrival_offsets': {'opening': 0}, 'native_workstation_permissions': deepcopy(WORKSTATION_PERMISSIONS),
                    'goal_mode': 'off', 'source_schedule': 'identical-at-start',
                    'initial_peer_messages': 0, 'communication_wakes_models': False,
                    'differentiated_tasks': False, 'differentiated_initial_materials': False,
                    'intended_framing_version': 'explicit-joint-task-v2',
                    'explicit_joint_task_context': condition == 'intended',
                    'scheduled_research_hints': False, 'analysis_window_seconds': 300},
                'worker_visible_sha256': digest(visible), 'instruction_audit': audit}
    if publication_updates:
        manifest['effective_settings'].update(communication_wakes_models=True,
            publication_updates=policy(sustained=sustained_research, responsive=responsive_research))
    if sustained_research:
        manifest['effective_settings']['sustained_research'] = research.policy(responsive=responsive_research)
    return visible, truth, manifest


def verify_theory_inputs(visible, truth, *, publication_updates=False, sustained_research=False):
    from swarmform.publication_updates import ENVIRONMENT_NOTICE
    from swarmform import sustained_research as research
    publication_updates = publication_updates or sustained_research
    task = THEORY_TASK
    if sustained_research:
        task = task.replace('A partial result with its exact limitations is a valid research output.', research.TASK_COMMITMENT)
        ENVIRONMENT_NOTICE = research.ENVIRONMENT_NOTICE
    actors = list(visible['startup'])
    tasks = [visible['startup'][a].get('/workspace/task.md') for a in actors]
    references = [visible['startup'][a].get('/workspace/problem-provenance.txt') for a in actors]
    interface_present=['/workspace/interfaces.txt' in visible['startup'][a] for a in actors]
    intended=bool(interface_present) and all(interface_present)
    allowed={'/workspace/task.md','/workspace/problem-provenance.txt','/workspace/environment.txt'}
    if intended:allowed.add('/workspace/interfaces.txt')
    if sustained_research:allowed.add('/workspace/research-session.md')
    environment=(THEORY_ENVIRONMENT + (ENVIRONMENT_NOTICE if publication_updates else '')
                 + ('\nAvailable messaging interface: /workspace/interfaces.txt.\n' if intended else ''))
    checks = {'exactly_eight_members': len(actors) == 8,
              'identical_task': all(t == task for t in tasks),
              'identical_initial_materials': all(t == THEORY_REFERENCE for t in references),
              'identical_prompts': len({json.dumps(visible['prompts'][a]) for a in actors}) == 1,
              'condition_prompt_exact': all(visible['prompts'][a] ==
                  [AUTONOMOUS_EXECUTION, theory_start_prompt(intended, sustained_research=sustained_research)] for a in actors),
              'matched_research_session': not sustained_research or all(
                  visible['startup'][a].get('/workspace/research-session.md') == research.SESSION_TEXT for a in actors),
              'only_registered_startup_resources': all(set(visible['startup'][a])==allowed for a in actors),
              'matched_environment': all(visible['startup'][a].get('/workspace/environment.txt')==environment for a in actors),
              'no_differentiated_arrivals': all(visible['private_arrivals'][a] == {'opening': {}} for a in actors),
              'no_organization_instruction': audit_visible(visible)['passed'],
              'task_hash_matches': truth['common_task_sha256'] == sha256(task.encode()).hexdigest()}
    return {'passed': all(checks.values()), 'checks': checks,
            'scope': 'Construct and input equality only; does not claim solvability, mathematical correctness, or behavioral formation.'}


def theory_output_inventory(snapshots):
    versions = {}
    for observer, snapshot in snapshots.items():
        for path, encoded in snapshot.get('/var/tmp/exports', {}).items():
            if path.startswith('/var/tmp/exports/navier-stokes/'):
                import base64
                raw = base64.b64decode(encoded)
                key = path, sha256(raw).hexdigest()
                row = versions.setdefault(key, {'path': path, 'sha256': key[1], 'bytes': len(raw), 'terminal_observers': []})
                row['terminal_observers'].append(observer)
    return {'versions': list(versions.values()), 'mathematical_review': 'pending', 'structural_review': 'pending',
            'scope': 'Retained shared deliverable bytes. Observer is not author; a present file is not a verified mathematical result.'}
