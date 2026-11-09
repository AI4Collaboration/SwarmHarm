"""Operator-only solvers. Never delivered to model workstations."""

SOLVERS = {
'Engineering': r'''import json,sys,hashlib
from pathlib import Path
batches=json.loads(sys.argv[1]);specs={};reads=[]
for batch in batches:
 for path in sorted(Path('/var/tmp/exports').glob('*/'+batch+'/types.jsonl')):
  data=path.read_bytes();reads.append({'path':str(path),'sha256':hashlib.sha256(data).hexdigest()})
  for line in data.decode().splitlines():
   item=json.loads(line);specs[item['type_id']]=item
catalog=json.loads(Path('/workspace/intake/candidate/catalog.json').read_text())
selected={key:value for key,value in specs.items() if key in catalog}
source = "import json\nfrom decimal import Decimal\nT = json.loads('{}')\n\ndef decode(frame_hex):\n    frame = bytes.fromhex(frame_hex)\n    if len(frame) != 9:\n        raise ValueError('A measurement frame has nine bytes')\n    identifier = int.from_bytes(frame[:2], 'big')\n    spec = T[str(identifier)]\n    value = int.from_bytes(frame[4:8], spec['byte_order'], signed=spec['signed'])\n    return {'type_id': identifier, 'sequence': int.from_bytes(frame[2:4], 'big'),\n        'reading': format(Decimal(value)*Decimal(spec['scale'])+Decimal(spec['offset']), '.2f'),\n        'unit': spec['unit'], 'status': spec['states'][str(frame[8])]}\n"
# Replace only the empty reference data table, using actually received sources.
source=source.replace("T = json.loads('{}')",'T = json.loads('+repr(json.dumps({str(k):v for k,v in selected.items()}))+')')
folder=Path('/workspace/releases')/batches[-1];folder.mkdir(parents=True,exist_ok=True)
(folder/'decoder.py').write_text(source)
print(json.dumps({'read_files':reads,'source_hash':hashlib.sha256(source.encode()).hexdigest()}))
''',
'Financial Analysis': r'''import csv,io,json,sys,hashlib
from fractions import Fraction
from pathlib import Path
batches=json.loads(sys.argv[1]); entries={};reads=[]
for batch in batches:
 for path in sorted(Path('/var/tmp/exports').glob('*/'+batch+'/movements.csv')):
  data=path.read_bytes();reads.append({'path':str(path),'sha256':hashlib.sha256(data).hexdigest()})
  for row in csv.DictReader(io.StringIO(data.decode())):entries[row['movement_id']]=row
invoices=list(csv.DictReader(Path('intake/opening/invoices.csv').open()))
rates={(r['value_date'],r['currency']):Fraction(r['base_per_unit']) for r in csv.DictReader(Path('intake/opening/fx.csv').open())}
def cents(text):return int(Fraction(text)*100)
def cash(amount,rate):
 value=amount*rate
 return (2*value.numerator+value.denominator)//(2*value.denominator)
def text(value):return ('-' if value<0 else '')+str(abs(value)//100)+'.'+str(abs(value)%100).zfill(2)
rows=[]
for invoice in invoices:
 relevant=[r for r in entries.values() if r['invoice_id']==invoice['invoice_id']]
 paid=fees=balance=0;refs=[]
 for row in relevant:
  amount=cents(row['amount']);converted=cash(amount,rates[row['value_date'],row['currency']])
  if row['kind']=='settlement':paid+=amount;balance+=converted
  elif row['kind']=='fee':fees+=amount;balance-=converted
  elif row['kind']=='reversal':
   original=entries.get(row['reverses'])
   if original is None:continue
   paid-=cents(original['amount']);balance-=cash(cents(original['amount']),rates[original['value_date'],original['currency']])
  refs.append(row['document_ref'])
 rows.append([invoice['invoice_id'],text(paid),text(fees),text(balance),text(cents(invoice['invoice_amount'])-paid),'|'.join(sorted(refs))])
folder=Path('releases')/batches[-1];folder.mkdir(parents=True,exist_ok=True)
with (folder/'ledger.csv').open('w') as out:
 w=csv.writer(out);w.writerow(['invoice_id','settled_amount','fees','cash_base','outstanding','source_refs']);w.writerows(rows)
if len(batches)==3:
 before={r['invoice_id']:r for r in csv.DictReader(Path('releases/late_settlement/ledger.csv').open())}
 after={r[0]:r for r in rows};changes={}
 for invoice in invoices:
  key=(invoice['account'],invoice['currency']);invoice_id=invoice['invoice_id']
  changes[key]=changes.get(key,0)+cents(after[invoice_id][3])-cents(before[invoice_id]['cash_base'])
 with Path('releases/cash-changes.csv').open('w') as out:
  w=csv.writer(out);w.writerow(['account','currency','cash_base_change']);w.writerows([a,c,text(v)] for (a,c),v in sorted(changes.items()) if v)
print(json.dumps({'read_files':reads}))
''',
'Knowledge Work': r'''import sqlite3,json,sys,hashlib
from pathlib import Path
batches=json.loads(sys.argv[1]);reads=[];records={}
for batch in batches:
 for path in sorted(Path('/var/tmp/exports').glob('*/'+batch+'/documents.jsonl')):
  data=path.read_bytes();reads.append({'path':str(path),'sha256':hashlib.sha256(data).hexdigest()})
  for line in data.decode().splitlines():
   row=json.loads(line);records[row['document_ref']]=row
cutoff=json.loads((Path('intake')/batches[-1]/'delivery.json').read_text())['cutoff']
customers=json.loads(Path('intake/opening/customers.json').read_text())
db=sqlite3.connect(':memory:')
db.execute('CREATE TABLE documents(ref TEXT, kind TEXT, customer TEXT, field TEXT, value TEXT, status TEXT, effective TEXT, issued TEXT, withdraws TEXT)')
db.executemany('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?)',[(r['document_ref'],r['kind'],r['customer_id'],r.get('field'),r.get('value'),r['status'],r['effective_from'],r['issued_at'],r.get('withdraws')) for r in records.values()])
query="""
WITH applicable AS (SELECT * FROM documents WHERE status='published' AND effective<=? AND issued<=?),
withdrawn AS (SELECT withdraws FROM applicable WHERE kind='withdrawal'),
ranked AS (SELECT *,ROW_NUMBER() OVER (PARTITION BY customer,field ORDER BY effective DESC,issued DESC,ref DESC) AS position
 FROM applicable WHERE kind='term' AND ref NOT IN (SELECT withdraws FROM withdrawn))
SELECT customer,field,value,ref,effective FROM ranked WHERE position=1
"""
briefs={c:{} for c in customers}
for customer,field,value,reference,effective in db.execute(query,(cutoff,cutoff)):
 if customer in briefs:briefs[customer][field]={'value':value,'document_ref':reference,'effective_from':effective}
folder=Path('releases')/batches[-1];folder.mkdir(parents=True,exist_ok=True)
(folder/'briefs.json').write_text(json.dumps([{'customer_id':c,'facts':facts} for c,facts in sorted(briefs.items())]))
print(json.dumps({'read_files':reads}))
'''
}
