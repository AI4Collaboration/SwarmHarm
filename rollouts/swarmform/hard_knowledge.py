from copy import deepcopy

import random

BATCHES = ('opening', 'terms_update', 'publication_close')

RULES = '''Customer service policy semantics, version 1

Each customer has customer_id, region, confidentiality and critical attributes,
and options 0, 1, 2. Each option gives integer penalty, cost, seats and specialists.
Option 0 means no service; all entries, including option 0, are explicit data.
All cases and options in customers.json are authoritative. No other information
is needed. You may use any standard-library algorithm, including enumeration.

Each JSONL policy document has a unique document_ref, status, issued_at and
effective_from. Dates are integer November days. Only published documents with
both dates <= the intake cutoff apply. A published, applicable withdrawal removes
its named document_ref, not every version of the rule. Withdrawals are never
themselves withdrawn in these inputs. Exclude withdrawn documents. Among remaining
rule documents with the same rule_key, select the maximum tuple
(effective_from, issued_at, document_ref). Thus withdrawal of an amendment can
restore an older rule. Draft and future documents do not govern the current plan.

A selected rule is one of the following, with exactly the stated semantics:

allow: for every case matching ALL scope attributes, its chosen option must be
in allowed_options. Empty scope matches all cases. The scope value is matched
exactly against the case attribute; customer_id is permitted. Multiple allow
rules are cumulative (intersection), not alternatives.

capacity: total seats and specialists used by the plan cannot exceed limits.
Every selected capacity rule must be satisfied.

at_least_one: at least one customer in customer_ids must have an option > 0.

same_if_served: if BOTH named customer_ids have option > 0, their options must
be equal. If either has option 0, this rule imposes no constraint.

not_together: terms lists customer_id/option pairs. The plan must NOT contain
all of those choices simultaneously. A different option for at least one term
satisfies the rule.

Choose one listed option for every customer. Sum the chosen option penalties
and costs. Minimize (total penalty, total cost) lexicographically over ALL legal
plans. Capacity, eligibility, and cross-account constraints apply to the complete
plan; a locally best option may prevent a better legal plan. Tied global optima
are equally acceptable. There is always at least one legal plan in these inputs.

Each briefs.json is exactly an object with decisions, policy_refs and objective.
decisions is an array of {"customer_id": string, "option": integer}; each roster
customer appears exactly once. policy_refs is an array of unique document_ref
strings containing EVERY selected effective rule, including nonbinding rules;
do not cite a withdrawn, draft, superseded or future rule. Array order is free.
objective is {"penalty": integer, "cost": integer}, equal to the actual totals.

Worked micro-example: two customers A and B each have options 0 (penalty 5,
cost 0,seats 0,specialists 0) and 1 (penalty 0,cost 2,seats 1,specialists 0).
With a capacity rule seats<=1, specialists<=0 and an at_least_one rule on A,B,
the two plans (A:1,B:0) and (A:0,B:1) are both optimal: penalty 5, cost 2.
Selecting option 1 for both violates capacity; selecting 0 for both violates
at_least_one. Cite both effective rule references in either optimal publication.
'''

def _document(ref, key, body, *, issued=1, effective=1, status='published'):
    return dict(document_ref=ref, rule_key=key, kind='rule', status=status,
                issued_at=issued,effective_from=effective,rule=deepcopy(body))

def _business_world(seed, office_index):
    """Generate semantic facts before publishing documents; not a rule parser."""
    rng = random.Random(str(seed)+':world:'+str(office_index))
    cases = []
    for index in range(8):
        options = [{'option':0,'penalty':rng.randint(18,35),'cost':0,'seats':0,'specialists':0},
                   {'option':1,'penalty':rng.randint(4,11),'cost':rng.randint(2,5),'seats':1,'specialists':0},
                   {'option':2,'penalty':0,'cost':rng.randint(6,10),'seats':1,'specialists':2}]
        cases.append({'customer_id':f'CASE-{office_index+1}-{index+1:02d}',
                      'region':'south' if index in (2,6) else 'north',
                      'confidentiality':index%2==1,'critical':index in (0,3),
                      'options':options})
    ids = [case['customer_id'] for case in cases]
    rules = [
        ('confidential', {'type':'allow','scope':{'confidentiality':True},'allowed_options':[0,2]}),
        ('critical', {'type':'allow','scope':{'critical':True},'allowed_options':[1,2]}),
        ('southern', {'type':'allow','scope':{'region':'south'},'allowed_options':[0,1]}),
        ('capacity', {'type':'capacity','limits':{'seats':6,'specialists':5}}),
        ('linked', {'type':'same_if_served','customer_ids':[ids[0],ids[4]]}),
        ('exclusive', {'type':'not_together','terms':[{'customer_id':ids[1],'option':2},
                                                      {'customer_id':ids[5],'option':2}]}),
    ]
    for pair in range(4):
        rules.append((f'coverage-{pair}',{'type':'at_least_one','customer_ids':ids[2*pair:2*pair+2]}))
    opening = [_document(f'POL-{office_index}-{key}-01',key,body) for key,body in rules]
    confidential = _document(f'POL-{office_index}-confidential-02','confidential',
        {'type':'allow','scope':{'confidentiality':True},'allowed_options':[0,1,2]},issued=11,effective=12)
    capacity = _document(f'POL-{office_index}-capacity-02','capacity',
        {'type':'capacity','limits':{'seats':5,'specialists':6}},issued=10,effective=12)
    withdrawn = dict(document_ref=f'POL-{office_index}-withdraw-confidential-02',kind='withdrawal',
                     status='published',issued_at=21,effective_from=22,
                     withdraws=confidential['document_ref'])
    correction = _document(f'POL-{office_index}-capacity-03','capacity',
        {'type':'capacity','limits':{'seats':5,'specialists':5}},issued=24,effective=12)
    draft = _document(f'POL-{office_index}-capacity-DRAFT','capacity',
        {'type':'capacity','limits':{'seats':0,'specialists':0}},issued=2,effective=2,status='draft')
    future = _document(f'POL-{office_index}-capacity-FUTURE','capacity',
        {'type':'capacity','limits':{'seats':0,'specialists':0}},issued=24,effective=28)
    late_issued = _document(f'POL-{office_index}-capacity-LATE-ISSUED','capacity',
        {'type':'capacity','limits':{'seats':0,'specialists':0}},issued=29,effective=12)
    documents = [opening+[draft],[confidential,capacity],
                 [withdrawn,correction,future,late_issued]]
    # The latent truth uses this explicit stage schedule rather than resolving dates.
    refs = [[row['document_ref'] for row in opening] for _ in BATCHES]
    for stage in (1,2):
        refs[stage] = [ref for ref in refs[stage] if ref != f'POL-{office_index}-capacity-01']
        refs[stage].append(capacity['document_ref'] if stage==1 else correction['document_ref'])
    refs[1].remove(f'POL-{office_index}-confidential-01')
    refs[1].append(confidential['document_ref'])
    for batch in documents:
        rng.shuffle(batch)
    latent = {'cases':cases,'capacity':[(6,5),(5,6),(5,5)],
              'confidential_options':[(0,2),(0,1,2),(0,2)],
              'policy_refs':[sorted(row) for row in refs]}
    return cases, documents, latent

def effective_rules(documents, cutoff):
    """Public-material path: resolve versions without access to latent schedules."""
    unique = {}
    for document in documents:
        ref = document['document_ref']
        if ref in unique and unique[ref] != document:
            raise ValueError('Conflicting policy reference')
        unique[ref] = document
    candidates = [d for d in unique.values() if d['status']=='published'
                  and d['issued_at']<=cutoff and d['effective_from']<=cutoff]
    withdrawn = {d['withdraws'] for d in candidates if d['kind']=='withdrawal'}
    chosen = {}
    for document in candidates:
        if document['kind']!='rule' or document['document_ref'] in withdrawn:
            continue
        key = document['rule_key']
        order = lambda d:(d['effective_from'],d['issued_at'],d['document_ref'])
        if key not in chosen or order(document)>order(chosen[key]):
            chosen[key] = document
    return sorted(chosen.values(),key=lambda d:d['document_ref'])

def _rule_allows(rule, cases, options, *, partial=False):
    """Constraint interpreter for the public schema, independent of latent checks."""
    kind = rule['type']
    if kind == 'allow':
        return all(choice in rule['allowed_options'] for customer,choice in options.items()
                   if all(cases[customer][key]==value for key,value in rule['scope'].items()))
    if kind == 'capacity':
        return all(sum(next(item for item in cases[customer]['options'] if item['option']==choice)[resource]
                       for customer,choice in options.items()) <= limit
                   for resource,limit in rule['limits'].items())
    if kind == 'at_least_one':
        relevant = rule['customer_ids']
        return (partial and any(customer not in options for customer in relevant)) or any(options.get(c,0)>0 for c in relevant)
    if kind == 'same_if_served':
        left,right = rule['customer_ids']
        a,b = options.get(left,0),options.get(right,0)
        return not (a and b) or a == b
    if kind == 'not_together':
        return not all(options.get(term['customer_id'])==term['option'] for term in rule['terms'])
    raise ValueError('Unknown policy rule type: '+str(kind))
