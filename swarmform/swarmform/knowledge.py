"""Versioned customer briefs with dated terms, amendments and withdrawals."""
from copy import deepcopy
import json
import random

SITES=('Cedar','Juniper','Willow')
BATCHES=('opening','terms_update','publication_close')
CUTOFFS=('2026-11-03','2026-11-17','2026-11-27')
FIELDS=('support_hours','contact_route','retention_period','billing_cycle')
VALUES={
 'support_hours':('Monday-Friday 08:00-18:00 UTC','Monday-Saturday 09:00-17:00 UTC','Every day 07:00-23:00 UTC','Every day, 24 hours'),
 'contact_route':('Account service desk','Regional support desk','Dedicated account contact','Customer portal case queue'),
 'retention_period':('30 days','90 days','180 days','365 days'),
 'billing_cycle':('Monthly in advance','Monthly in arrears','Quarterly in advance','Quarterly in arrears')}
WORK_ORDER='''November customer brief publication

Prepare the customer briefs for the accounts listed in customers.json. The intake
contains dated service documents and later amendments. Publish a brief for each
intake using the cutoff in that intake's delivery.json.

Use published terms effective by the cutoff. Drafts and future terms do not change
the current brief. A published withdrawal removes its named amendment from the
applicable terms. For each customer and field use the remaining published term
with the latest effective date, then the latest issue date. Retain its document
reference and effective date so the account team can check the brief's source.

Write releases/<batch>/briefs.json as an array with one entry per customer. Each
entry has customer_id and facts. The facts object contains support_hours,
contact_route, retention_period and billing_cycle; each contains value,
document_ref and effective_from. The intake names are opening, terms_update and
publication_close. Keep all three publication versions.
'''


TABLE_WORK_ORDER = WORK_ORDER[:WORK_ORDER.index('Write releases/')] + '''Write releases/<batch>/briefs.json as an array of rows, one for each customer
and each term: support_hours, contact_route, retention_period and billing_cycle.
Each row has customer_id, term, value, document_ref and effective_from. The intake
names are opening, terms_update and publication_close. Keep all three versions.
'''


def encode(records):
    return ''.join(json.dumps(r,sort_keys=True)+'\n' for r in records)


def resolve(customers, documents, cutoff):
    records={}
    for document in documents:
        ref=document['document_ref']
        if ref in records and records[ref]!=document:
            raise ValueError('Document reference has conflicting content')
        records[ref]=document
    applicable=[r for r in records.values() if r['status']=='published' and r['effective_from']<=cutoff and r['issued_at']<=cutoff]
    withdrawn={r['withdraws'] for r in applicable if r['kind']=='withdrawal'}
    result={}
    for customer in customers:
        facts={}
        for field in FIELDS:
            choices=[r for r in applicable if r['kind']=='term' and r['customer_id']==customer and r['field']==field and r['document_ref'] not in withdrawn]
            if not choices:
                continue
            chosen=max(choices,key=lambda r:(r['effective_from'],r['issued_at'],r['document_ref']))
            facts[field]={k:chosen[k] for k in ('value','document_ref','effective_from')}
        result[customer]=facts
    return result


def source_material(key):
    rng=random.Random(key)
    catalogs={site:[f'CUS-{index+1}{n:03d}' for n in range(80)] for index,site in enumerate(SITES)}
    private={site:{} for site in SITES}
    documents={site:{batch:[] for batch in BATCHES} for site in SITES}
    expected={site:[] for site in SITES}
    base_values={}
    for owner_index,owner in enumerate(SITES):
        for index,(customer,field) in enumerate((c,f) for c in catalogs[owner] for f in FIELDS):
            # Twenty-five percent of each account office's required facts are local.
            writer=SITES[(owner_index+(0 if index%4==0 else 1+index%2))%3]
            value=rng.choice(VALUES[field]); base_values[customer,field]=value
            ref=f'TERMS-{customer}-{field}-01'
            base={'document_ref':ref,'kind':'term','customer_id':customer,'field':field,'value':value,
                  'status':'published','effective_from':'2026-11-01','issued_at':'2026-10-29'}
            documents[writer]['opening'].append(base)
            if index%8==0:
                draft={**base,'document_ref':ref+'-DRAFT','status':'draft','issued_at':'2026-11-02',
                       'value':rng.choice([v for v in VALUES[field] if v!=value])}
                future={**base,'document_ref':ref+'-DECEMBER','effective_from':'2026-12-01',
                        'value':rng.choice([v for v in VALUES[field] if v!=value])}
                documents[writer]['opening'] += [draft,future]
            if index<96:
                amendment={**base,'document_ref':ref[:-2]+'02','effective_from':'2026-11-12','issued_at':'2026-11-10',
                           'value':rng.choice([v for v in VALUES[field] if v!=value])}
                documents[writer]['terms_update'].append(amendment)
                if 32<=index<64:
                    documents[writer]['publication_close'].append({
                      'document_ref':ref[:-2]+'03-W','kind':'withdrawal','customer_id':customer,
                      'status':'published','effective_from':'2026-11-23','issued_at':'2026-11-22',
                      'withdraws':amendment['document_ref']})
            elif index<160:
                documents[writer]['publication_close'].append({**base,'document_ref':ref[:-2]+'03',
                  'effective_from':'2026-11-24','issued_at':'2026-11-23',
                  'value':rng.choice([v for v in VALUES[field] if v!=value])})
    for site in SITES:
        for stage,batch in enumerate(BATCHES):
            rows=documents[site][batch];rng.shuffle(rows)
            files={f'intake/{batch}/documents.jsonl':encode(rows),
                   f'intake/{batch}/delivery.json':json.dumps({'cutoff':CUTOFFS[stage]})+'\n'}
            if stage==0:
                files['intake/opening/customers.json']=json.dumps(catalogs[site])+'\n'
            private[site][batch]=files
    for owner in SITES:
        for stage,cutoff in enumerate(CUTOFFS):
            all_records=[r for batch in BATCHES[:stage+1] for site in SITES for r in documents[site][batch]]
            expected[owner].append(resolve(catalogs[owner],all_records,cutoff))
    return private,expected,catalogs,documents


def align_roster_sources(private, rosters):
    """Place each assigned account's term history with an office serving it.

    Overlapping portfolios split the four terms between their account offices.
    Documents outside these portfolios retain their existing location.
    Only document placement changes; source records and arrival dates do not.
    """
    documents = {(site, batch): [json.loads(line) for line in
        private[site][batch][f'intake/{batch}/documents.jsonl'].splitlines()]
        for site in SITES for batch in BATCHES}
    records = {row['document_ref']: row for rows in documents.values() for row in rows}
    custody = {}
    for customer in sorted({customer for roster in rosters.values() for customer in roster}):
        offices = [site for site in SITES if customer in rosters[site]]
        if len(offices) < 2:
            raise ValueError('Overlapping portfolios need multiple offices per account')
        for index, field in enumerate(FIELDS):
            custody[customer, field] = offices[index % len(offices)]
    placed = {key: [] for key in documents}
    for (site, batch), rows in documents.items():
        for row in rows:
            term = records[row['withdraws']] if row['kind'] == 'withdrawal' else row
            office = custody.get((term['customer_id'], term['field']), site)
            placed[office, batch].append(row)
    for (site, batch), rows in placed.items():
        private[site][batch][f'intake/{batch}/documents.jsonl'] = encode(rows)


def verify(text,expected,*,flat=False):
    try:
        rows=json.loads(text)
        if flat:
            columns={'customer_id','term','value','document_ref','effective_from'}
            if not isinstance(rows,list) or any(not isinstance(r,dict) or set(r)!=columns for r in rows):
                raise ValueError('Invalid cited-term layout')
            observed={}
            keys=[]
            for row in rows:
                keys.append((row['customer_id'],row['term']))
                observed.setdefault(row['customer_id'],{})[row['term']]={k:row[k] for k in ('value','document_ref','effective_from')}
            unique=len(keys)==len(set(keys))
        else:
            if not isinstance(rows,list) or any(set(r)!= {'customer_id','facts'} for r in rows):
                raise ValueError('Invalid brief layout')
            observed={r['customer_id']:r['facts'] for r in rows}
            unique=len(rows)==len(observed)
        correct=sum(observed.get(customer,{}).get(field)==value for customer,facts in expected.items() for field,value in facts.items())
        return {'complete':unique and observed==expected,'correct_cited_facts':correct,
                'required_cited_facts':sum(len(f) for f in expected.values())}
    except (ValueError,TypeError,KeyError,AttributeError):
        return {'complete':False,'correct_cited_facts':0,'required_cited_facts':sum(len(f) for f in expected.values())}


def brief(rows,*,flat=False):
    if flat:
        return json.dumps([{'customer_id':customer,'term':field,**value}
                           for customer,facts in sorted(rows.items()) for field,value in sorted(facts.items())])
    return json.dumps([{'customer_id':customer,'facts':facts} for customer,facts in sorted(rows.items())])


def check():
    private,expected,catalogs,documents=source_material('november')
    passed,private_incomplete,wrong_citations,withdrawals=0,0,0,0
    for owner in SITES:
        for stage,batch in enumerate(BATCHES):
            assert verify(brief(expected[owner][stage]),expected[owner][stage])['complete']
            passed+=1
            own=[r for b in BATCHES[:stage+1] for r in documents[owner][b]]
            own_result=verify(brief(resolve(catalogs[owner],own,CUTOFFS[stage])),expected[owner][stage])
            assert not own_result['complete'] and own_result['correct_cited_facts']==80
            private_incomplete+=1
        # Each withdrawn amendment falls back to the original published term.
        reverted=sum(expected[owner][2][c][f]==expected[owner][0][c][f] and expected[owner][1][c][f]!=expected[owner][0][c][f]
                     for c in catalogs[owner] for f in FIELDS)
        assert reverted==32,reverted
        withdrawals+=reverted
        stale=verify(brief(expected[owner][1]),expected[owner][2]);assert not stale['complete']
        wrong=deepcopy(expected[owner][2]); wrong[catalogs[owner][0]][FIELDS[0]]['document_ref']='UNRELATED-REFERENCE'
        assert not verify(brief(wrong),expected[owner][2])['complete'];wrong_citations+=1
    pairs=0
    for owner in SITES:
        own_bytes=deepcopy(private[owner])
        for foreign in set(SITES)-{owner}:
            versions=deepcopy(documents)
            row=next(r for r in versions[foreign]['opening'] if r['kind']=='term' and r['status']=='published'
                     and r['effective_from']=='2026-11-01' and r['customer_id'] in catalogs[owner])
            row['value']=next(v for v in VALUES[row['field']] if v!=row['value'])
            revised=resolve(catalogs[owner],[r for s in SITES for r in versions[s]['opening']],CUTOFFS[0])
            assert revised!=expected[owner][0] and own_bytes==private[owner];pairs+=1
    return {'status':'offline_workload_checked','model_calls':0,'combined_complete_publications':passed,
            'private_incomplete_publications':private_incomplete,'withdrawn_amendments_restored':withdrawals,
            'wrong_citations_rejected':wrong_citations,'directed_foreign_dependencies':pairs,
            'source_bytes':sum(len(text.encode()) for batches in private.values() for files in batches.values() for text in files.values())}


if __name__=='__main__':
    print(json.dumps(check(),indent=2))
