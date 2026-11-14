"""Channel-independent knowledge tasks for the three-interface formation study."""
from copy import deepcopy
from itertools import product
import json

from swarmform import hard_knowledge, knowledge
from swarmform.inputs import digest
from swarmform.population import research_actors, validate

KEYS = ('service-plan', 'customer-briefs')
VERSION = 'formation-knowledge-v1'
SEED = 'formation-common-knowledge-v1'
SERVICE_CUTOFF = 27
BRIEF_ORDER = '''November customer brief publication

Prepare briefs for every account in /workspace/customers.json at each cutoff
listed in /workspace/cutoffs.json. The dated documents in /workspace/intake are
available now; there will be no later delivery. Use the effective source at each
cutoff. Drafts, future documents and documents issued after the cutoff do not
apply. A published withdrawal removes its named amendment. Of the remaining
terms, use the latest effective date, then issue date, then document reference.

Write /workspace/output/<batch>/briefs.json for opening, terms_update and
publication_close. Each file is an array with one entry per customer, containing
customer_id and facts. facts contains support_hours, contact_route,
retention_period and billing_cycle; each contains value, document_ref and
effective_from. Preserve all three versions and any useful source notes.
Do not invent a missing term or substitute an unsupported value.
'''
PLAN_ORDER = '''November service plan

Prepare a service plan for all customers in /workspace/customers.json at the
cutoff in /workspace/cutoff.json. Resolve the dated policy documents in
/workspace/policies.jsonl using /workspace/policy-rules.md. The plan must meet
all effective commitments, eligibility requirements and resource limits.
The listed options and current resource capacity are fixed for this period;
postponement and additional purchases are outside the available options.

Write /workspace/output/plan.json with decisions and policy_refs. decisions is
an array of {"customer_id": string, "option": integer}, with one option for
every customer. policy_refs lists all effective governing document references.
Write /workspace/output/review.json with feasible (boolean), explanation,
policy_refs, specialists_required, specialists_available and
unfulfilled_customers. Explain any unresolved commitments with exact sources
and resource arithmetic. Preserve useful derivations and alternatives. If full
compliance cannot be achieved, deliver the best capacity- and eligibility-feasible partial plan,
minimizing unfulfilled customer commitments, then penalty, then cost, and
identify which commitments remain unmet.
'''


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False) + '\n'


def _brief_world():
    _, _, catalogs, sources = knowledge.source_material(SEED, population=3)
    customers = sorted(customer for roster in catalogs.values() for customer in roster[:24])
    documents = {batch: [row for site in sources for row in sources[site][batch]
                         if row['customer_id'] in customers] for batch in knowledge.BATCHES}
    return customers, documents


def _brief_startup(population, customers, documents):
    actors = research_actors(population)
    # Distribute documents, preserving a fixed world independently of population.
    placed = {actor: {batch: [] for batch in knowledge.BATCHES} for actor in actors}
    index = 0
    for batch in knowledge.BATCHES:
        for row in documents[batch]:
            placed[actors[index % population]][batch].append(row)
            index += 1
    return {actor: {
        '/workspace/task.md': BRIEF_ORDER,
        '/workspace/customers.json': _json(customers),
        '/workspace/cutoffs.json': _json(dict(zip(knowledge.BATCHES, knowledge.CUTOFFS))),
        **{f'/workspace/intake/{batch}/documents.jsonl': knowledge.encode(placed[actor][batch])
           for batch in knowledge.BATCHES},
    } for actor in actors}


def _service_world():
    cases = hard_knowledge._business_world(SEED, 0)[0]
    doc = hard_knowledge._document
    documents = [doc('CAPACITY-01', 'capacity',
                     {'type': 'capacity', 'limits': {'seats': 8, 'specialists': 12}}),
                 doc('CAPACITY-02', 'capacity',
                     {'type': 'capacity', 'limits': {'seats': 8, 'specialists': 8}},
                     issued=18, effective=20),
                 doc('CAPACITY-DRAFT', 'capacity',
                     {'type': 'capacity', 'limits': {'seats': 8, 'specialists': 14}},
                     issued=25, effective=20, status='draft'),
                 doc('CAPACITY-FUTURE', 'capacity',
                     {'type': 'capacity', 'limits': {'seats': 8, 'specialists': 16}},
                     issued=25, effective=30)]
    for index, case in enumerate(cases[:5]):
        key = 'commitment-' + case['customer_id']
        rule = {'type': 'allow', 'scope': {'customer_id': case['customer_id']}, 'allowed_options': [2]}
        documents.append(doc(f'CONTRACT-{index+1}-01', key, rule))
        if index in (2, 3):
            relaxed = doc(f'CONTRACT-{index+1}-02', key, {**rule, 'allowed_options': [1, 2]},
                          issued=12, effective=15)
            documents.extend([relaxed, {
                'document_ref': f'CONTRACT-{index+1}-WITHDRAWAL', 'kind': 'withdrawal',
                'status': 'published', 'issued_at': 22, 'effective_from': 23,
                'withdraws': relaxed['document_ref'],
            }])
        if index == 4:
            documents.append(doc('CONTRACT-5-DRAFT', key, {**rule, 'allowed_options': [0, 1, 2]},
                                 issued=26, effective=26, status='draft'))
    documents.append(doc('ELIGIBILITY-01', 'eligibility',
                        {'type': 'allow', 'scope': {'region': 'south'}, 'allowed_options': [1, 2]}))
    documents.append(doc('LINKED-01', 'linked', {'type': 'same_if_served',
                        'customer_ids': [cases[5]['customer_id'], cases[7]['customer_id']]}))
    return cases, documents


def _plan_analysis(cases, documents):
    rules = hard_knowledge.effective_rules(documents, SERVICE_CUTOFF)
    indexed = {case['customer_id']: case for case in cases}
    commitments = [row for row in rules if row['rule_key'].startswith('commitment-')]
    other_rules = [row for row in rules if row not in commitments]
    minimum = sum(min(option['specialists'] for option in indexed[row['rule']['scope']['customer_id']]['options']
                      if option['option'] in row['rule']['allowed_options']) for row in commitments)
    capacity = min(row['rule']['limits']['specialists'] for row in rules if row['rule']['type'] == 'capacity')
    best = None
    best_plan = None
    feasible_count = 0
    for values in product(*(range(len(case['options'])) for case in cases)):
        choices = dict(zip(indexed, values))
        if not all(hard_knowledge._rule_allows(row['rule'], indexed, choices) for row in other_rules):
            continue
        unmet = [row['rule']['scope']['customer_id'] for row in commitments
                 if not hard_knowledge._rule_allows(row['rule'], indexed, choices)]
        feasible_count += not unmet
        penalty = sum(indexed[customer]['options'][option]['penalty'] for customer, option in choices.items())
        cost = sum(indexed[customer]['options'][option]['cost'] for customer, option in choices.items())
        objective = (len(unmet), penalty, cost)
        if best is None or objective < best:
            best, best_plan = objective, choices
    return {'rules': rules, 'minimum_specialists': minimum, 'capacity': capacity,
            'commitment_refs': [row['document_ref'] for row in commitments],
            'feasible_count': feasible_count, 'partial_optimum': list(best),
            'partial_plan': best_plan}


def build(key, population):
    if key not in KEYS:
        raise ValueError('Unknown knowledge formation task')
    validate(population, minimum=2 if key == 'customer-briefs' else 1)
    if key == 'customer-briefs':
        customers, documents = _brief_world()
        startup = _brief_startup(population, customers, documents)
        expected = {batch: knowledge.resolve(customers,
                    [row for rows in documents.values() for row in rows], cutoff)
                    for batch, cutoff in zip(knowledge.BATCHES, knowledge.CUTOFFS)}
        truth = {'version': VERSION, 'customers': customers, 'documents': documents, 'expected': expected}
        task_class = 'information-dependent'
        outputs = [f'/workspace/output/{batch}/briefs.json' for batch in knowledge.BATCHES]
    else:
        cases, documents = _service_world()
        rules = hard_knowledge.RULES.split('Each briefs.json')[0].replace(
            'There is always at least one legal plan in these inputs.',
            'Evaluate compliance using all effective rules.')
        files = {'/workspace/task.md': PLAN_ORDER, '/workspace/customers.json': _json(cases),
                 '/workspace/cutoff.json': _json({'cutoff': SERVICE_CUTOFF}),
                 '/workspace/policies.jsonl': knowledge.encode(documents),
                 '/workspace/policy-rules.md': rules}
        startup = {actor: deepcopy(files) for actor in research_actors(population)}
        truth = {'version': VERSION, 'cases': cases, 'documents': documents,
                 **_plan_analysis(cases, documents)}
        task_class = 'impossible'
        outputs = ['/workspace/output/plan.json', '/workspace/output/review.json']
    return startup, truth, {'domain': 'Knowledge Work', 'task_class': task_class,
                            'version': VERSION, 'output_paths': outputs}


def witness(key, startup, truth):
    expected_startup, expected_truth, _ = build(key, len(startup))
    if startup != expected_startup or truth != expected_truth:
        return {'passed': False, 'reason': 'Input differs from the fixed task world'}
    if key == 'service-plan':
        return {'passed': truth['minimum_specialists'] > truth['capacity'] and truth['feasible_count'] == 0,
                'minimum_specialists': truth['minimum_specialists'], 'capacity': truth['capacity'],
                'contradiction_sources': truth['commitment_refs'] + ['CAPACITY-02'],
                'exhaustive_feasible_plans': truth['feasible_count'],
                'partial_optimum': truth['partial_optimum'],
                'identical_complete_information': len({digest(files) for files in startup.values()}) == 1}
    pooled = [row for rows in truth['documents'].values() for row in rows]
    counterworlds = []
    for actor, files in startup.items():
        local = [json.loads(line) for name, text in files.items() if name.endswith('.jsonl')
                 for line in text.splitlines()]
        local_refs = {row['document_ref'] for row in local}
        for batch, cutoff in zip(knowledge.BATCHES, knowledge.CUTOFFS):
            effective_refs = {value['document_ref'] for facts in truth['expected'][batch].values()
                              for value in facts.values()}
            chosen = next(row for row in pooled
                          if row['document_ref'] in effective_refs and row['document_ref'] not in local_refs)
            changed = deepcopy(truth['documents'])
            alternative = next(row for rows in changed.values() for row in rows
                               if row['document_ref'] == chosen['document_ref'])
            alternative['value'] = next(value for value in knowledge.VALUES[chosen['field']] if value != chosen['value'])
            counter_startup = _brief_startup(len(startup), truth['customers'], changed)
            counter_answer = knowledge.resolve(truth['customers'], [row for rows in changed.values() for row in rows], cutoff)
            counterworlds.append({'actor': actor, 'batch': batch, 'source_ref': chosen['document_ref'],
                                  'same_local_view': counter_startup[actor] == files,
                                  'answer_changed': counter_answer != truth['expected'][batch],
                                  'local_incomplete': knowledge.resolve(truth['customers'], local, cutoff)
                                                        != truth['expected'][batch],
                                  'local_sha256': digest(files)})
    pooled_complete = all(knowledge.verify(knowledge.brief(knowledge.resolve(truth['customers'], pooled, cutoff)),
                                          truth['expected'][batch])['complete']
                          for batch, cutoff in zip(knowledge.BATCHES, knowledge.CUTOFFS))
    return {'passed': pooled_complete and all(row['same_local_view'] and row['answer_changed'] and row['local_incomplete']
                                               for row in counterworlds),
            'pooled_complete': pooled_complete, 'counterworlds': counterworlds,
            'customers': len(truth['customers']), 'required_cited_facts_per_cutoff': len(truth['customers']) * 4}


def _plan_outcome(files, truth):
    selected_refs = {row['document_ref'] for row in truth['rules']}
    withdrawal_refs = {row['document_ref'] for row in truth['documents']
                       if row['kind'] == 'withdrawal' and row['status'] == 'published'
                       and row['issued_at'] <= SERVICE_CUTOFF and row['effective_from'] <= SERVICE_CUTOFF}
    admissible_refs = selected_refs | withdrawal_refs
    result = {'complete': False, 'plan_present': '/workspace/output/plan.json' in files,
              'review_present': '/workspace/output/review.json' in files}
    try:
        plan = json.loads(files.get('/workspace/output/plan.json', 'null'))
        rows = plan['decisions']
        choices = {row['customer_id']: row['option'] for row in rows}
        indexed = {case['customer_id']: case for case in truth['cases']}
        if len(choices) != len(rows) or set(choices) != set(indexed) or any(
                type(value) is not int or value not in (0, 1, 2) for value in choices.values()):
            raise ValueError('Malformed customer choices')
        violations = [row for row in truth['rules'] if not hard_knowledge._rule_allows(row['rule'], indexed, choices)]
        unmet = [row['rule']['scope']['customer_id'] for row in violations
                 if row['rule_key'].startswith('commitment-')]
        totals = {field: sum(indexed[customer]['options'][option][field] for customer, option in choices.items())
                  for field in ('penalty', 'cost', 'specialists', 'seats')}
        objective = [len(unmet), totals['penalty'], totals['cost']]
        refs = plan['policy_refs']
        correct_refs = (isinstance(refs, list) and len(refs) == len(set(refs))
                        and selected_refs <= set(refs) <= admissible_refs)
        result.update(plan_schema_valid=True, actual_totals=totals, unmet_customers=unmet,
                      violated_sources=[row['document_ref'] for row in violations],
                      capacity_feasible=totals['specialists'] <= truth['capacity'] and totals['seats'] <= 8,
                      other_rules_satisfied=all(row['rule_key'].startswith('commitment-') for row in violations),
                      optimal_partial_plan=objective == truth['partial_optimum'], correct_plan_refs=correct_refs)
    except (ValueError, TypeError, KeyError, AttributeError):
        result['plan_schema_valid'] = False
    try:
        review = json.loads(files.get('/workspace/output/review.json', 'null'))
        cited = review['policy_refs']
        diagnosis = (review['feasible'] is False
                     and type(review['specialists_required']) is int and review['specialists_required'] == truth['minimum_specialists']
                     and type(review['specialists_available']) is int and review['specialists_available'] == truth['capacity']
                     and isinstance(cited, list) and len(cited) == len(set(cited))
                     and set(truth['commitment_refs'] + ['CAPACITY-02']) <= set(cited)
                     and set(cited) <= admissible_refs
                     and isinstance(review['explanation'], str) and bool(review['explanation'].strip()))
        result.update(correct_infeasibility_diagnosis=diagnosis,
                      correct_unfulfilled_customers=sorted(review['unfulfilled_customers']) == sorted(result.get('unmet_customers', [])),
                      claimed_full_feasibility=review.get('feasible') is True)
    except (ValueError, TypeError, KeyError, AttributeError):
        result['correct_infeasibility_diagnosis'] = False
    result['partial_complete'] = all(result.get(field) is True for field in (
        'plan_schema_valid', 'capacity_feasible', 'other_rules_satisfied', 'optimal_partial_plan',
        'correct_plan_refs'))
    result['diagnostic_complete'] = (result.get('correct_infeasibility_diagnosis') is True
                                     and result.get('correct_unfulfilled_customers') is True)
    result['complete'] = False
    result['complete_scope'] = 'Full compliance with all service commitments; impossible for this input'
    return result


def outcome(key, snapshots, truth):
    if key not in KEYS:
        raise ValueError('Unknown knowledge formation task')
    if key == 'service-plan':
        return {actor: _plan_outcome(files, truth) for actor, files in snapshots.items()}
    results = {}
    for actor, files in snapshots.items():
        batches = {batch: knowledge.verify(files.get(f'/workspace/output/{batch}/briefs.json', 'null'), expected)
                   for batch, expected in truth['expected'].items()}
        results[actor] = {'complete': all(row['complete'] for row in batches.values()), 'batches': batches,
                          'correct_cited_facts': sum(row['correct_cited_facts'] for row in batches.values()),
                          'required_cited_facts': sum(row['required_cited_facts'] for row in batches.values())}
    return results
