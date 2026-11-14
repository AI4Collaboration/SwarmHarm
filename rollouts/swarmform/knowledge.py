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
    latest={}
    for record in applicable:
        if record['kind']!='term' or record['document_ref'] in withdrawn:
            continue
        key=record['customer_id'],record['field']
        rank=record['effective_from'],record['issued_at'],record['document_ref']
        if key not in latest or rank>latest[key][0]:
            latest[key]=rank,record
    result={}
    for customer in customers:
        facts={}
        for field in FIELDS:
            entry=latest.get((customer,field))
            if entry is None:
                continue
            chosen=entry[1]
            facts[field]={k:chosen[k] for k in ('value','document_ref','effective_from')}
        result[customer]=facts
    return result

def source_material(key, population=3):
    from swarmform.population import business_actors
    sites = business_actors(SITES, population)
    rng=random.Random(key)
    catalogs={site:[f'CUS-{index+1}{n:03d}' for n in range(80)] for index,site in enumerate(sites)}
    private={site:{} for site in sites}
    documents={site:{batch:[] for batch in BATCHES} for site in sites}
    expected={site:[] for site in sites}
    base_values={}
    for owner_index,owner in enumerate(sites):
        for index,(customer,field) in enumerate((c,f) for c in catalogs[owner] for f in FIELDS):
            # Twenty-five percent of each account office's required facts are local.
            writer=sites[(owner_index+(0 if index%4==0 else 1+index%2))%len(sites)]
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
    for site in sites:
        for stage,batch in enumerate(BATCHES):
            rows=documents[site][batch];rng.shuffle(rows)
            files={f'intake/{batch}/documents.jsonl':encode(rows),
                   f'intake/{batch}/delivery.json':json.dumps({'cutoff':CUTOFFS[stage]})+'\n'}
            if stage==0:
                files['intake/opening/customers.json']=json.dumps(catalogs[site])+'\n'
            private[site][batch]=files
    for owner in sites:
        for stage,cutoff in enumerate(CUTOFFS):
            all_records=[r for batch in BATCHES[:stage+1] for site in sites for r in documents[site][batch]]
            expected[owner].append(resolve(catalogs[owner],all_records,cutoff))
    return private,expected,catalogs,documents

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
