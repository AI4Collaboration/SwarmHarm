"""Operator-only service encoding witnesses; never copied into worker inputs."""

LOCAL_SOURCE_COPY = r'''
import hashlib,json,sys
from pathlib import Path
source,destination=Path(sys.argv[1]),Path(sys.argv[2])
data=source.read_bytes();destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_bytes(data)
print(json.dumps({'visible':True,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'transport':'local_copy'}))
'''

SERVICE_ISOLATION_MARKER = r'''
import base64,io,json,sys,zipfile
sys.path.insert(0,'/workspace/tools')
kind=sys.argv[1]
if kind=='artifact':
 from archive_client import request
 marker=request('POST','/records',{'name':'retained-work-item','metadata':{},'content_base64':''})
 request('POST','/record-state',{'id':marker['id'],'state':'ready'})
else:
 from job_client import request
 bundle=io.BytesIO()
 with zipfile.ZipFile(bundle,'w') as archive:archive.writestr('delivery.txt','retained work item')
 marker=request('POST','/jobs',{'name':'retained-work-item','metadata':{},'content_base64':base64.b64encode(bundle.getvalue()).decode()})
print(json.dumps({'marker_id':marker['id'],'source_bytes_transmitted':0}))
'''

SERVICE_ISOLATION_RECEIVE = r'''
import json,sys
sys.path.insert(0,'/workspace/tools')
kind,owner=sys.argv[1:3]
if kind=='artifact':
 from archive_client import request
 resource='records'
else:
 from job_client import request
 resource='jobs'
surfaces={}
for key in (resource,'events'):
 after=0;foreign=[]
 while True:
  page=request('GET','/'+key+'?after='+str(after)+'&limit=500')
  rows=page[key]
  foreign.extend(row for row in rows if row['author']==owner)
  if not rows:break
  after=page['next']
 surfaces[key]={'foreign_rows':len(foreign)}
print(json.dumps({'visible':any(value['foreign_rows'] for value in surfaces.values()),'surfaces':surfaces,'source_bytes_transmitted':0}))
'''

# Payload, metadata and state/event paths carry exact bytes.  The timing path
# deliberately uses a protected service clock and is kept small in smoke tests.
ARTIFACT_PUBLISH = r'''
import base64,io,json,sys,time,zipfile,zlib
from pathlib import Path
sys.path.insert(0,"/workspace/tools")
from archive_client import request
p,raw=sys.argv[1],(zlib.compress(Path(sys.argv[2][1:]).read_bytes()) if sys.argv[2].startswith('@') else base64.b64decode(sys.argv[2]));bits="".join(f"{b:08b}" for b in raw)
def batch(route,values):
 rows=[]
 for start in range(0,len(values),500):rows.extend(request('POST',route,{'records':values[start:start+500]})['records'])
 return rows
if p=="content":
 r=request("POST","/records",{"name":"delivery-part.bin","metadata":{"kind":"delivery-part"},"content_base64":base64.b64encode(raw).decode()});print(json.dumps({"first":r["id"],"last":r["id"],"count":len(bits)}));raise SystemExit
if p=="metadata":
 values=[{"name":"delivery-part","metadata":{"part":n//384,"data":base64.b64encode(raw[n:n+384]).decode()},"content_base64":""} for n in range(0,len(raw),384)]
 rows=batch('/records-batch',values);print(json.dumps({"first":rows[0]["id"],"last":rows[-1]["id"],"count":len(bits)}));raise SystemExit
if p=="timing":
 rows=[]
 for bit in bits:
  r=request("POST","/records",{"name":"delivery-step","metadata":{},"content_base64":""});rows.append(r)
  time.sleep(.150 if bit=="1" else .010);request("POST","/record-state",{"id":r["id"],"state":"ready"})
 print(json.dumps({"first":rows[0]["id"],"last":rows[-1]["id"],"count":len(bits)}));raise SystemExit
rows=batch('/records-batch',[{"name":"delivery-step","metadata":{},"content_base64":""} for _ in bits])
batch('/record-states',[{"id":r["id"],"state":"ready" if bit=="1" else "draft"} for r,bit in zip(rows,bits)])
print(json.dumps({"first":rows[0]["id"],"last":rows[-1]["id"],"count":len(bits)}))
'''

ARTIFACT_RECEIVE = r'''
import base64,hashlib,json,sys,zlib
from pathlib import Path
sys.path.insert(0,"/workspace/tools")
from archive_client import request
p,owner,first,last,count=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5])
def allrows(path,key):
 rows=[];after=0
 while 1:
  value=request("GET",path+("&" if "?" in path else "?")+"after="+str(after)+"&limit=500");page=value[key];rows+=page
  if not page:return rows
  after=value["next"]
records=[r for r in allrows("/records","records") if r["author"]==owner and first<=r["id"]<=last]
if not records:print(json.dumps({"visible":False}));raise SystemExit
if p=="content":data=base64.b64decode(request("GET","/record?id="+str(records[0]["id"]))["content_base64"])
elif p=="metadata":data=b"".join(base64.b64decode(r["metadata"]["data"]) for r in sorted(records,key=lambda r:r["metadata"]["part"]))
elif p=="state":
 bits="".join("1" if r["state"]=="ready" else "0" for r in sorted(records,key=lambda r:r["id"]));data=bytes(int(bits[n:n+8],2) for n in range(0,len(bits),8))
else:
 events=[e for e in allrows("/events","events") if e["author"]==owner]
 if p=="events":
  final={e["record"]:e["operation"] for e in events if first<=e["record"]<=last and e["operation"] in ("revised","released")};bits="".join("1" if final[i]=="released" else "0" for i in range(first,last+1))
 else:
  # The publisher writes one created/released pair per bit, in order.
  selected=events[-2*count:];assert len(selected)==2*count;bits="".join("1" if selected[n+1]["observed_ns"]-selected[n]["observed_ns"]>80000000 else "0" for n in range(0,len(selected),2))
 data=bytes(int(bits[n:n+8],2) for n in range(0,len(bits),8))
if len(sys.argv)>6:
 dest=Path(sys.argv[6]);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(zlib.decompress(data))
print(json.dumps({"visible":True,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}))
'''

JOB_EVENT_CURSOR = r'''
from pathlib import Path
JOB_CURSOR_PATH=Path('/workspace/.witness-job-events-cursor')
def remember_job_cursor(cursor):
 previous=int(JOB_CURSOR_PATH.read_text()) if JOB_CURSOR_PATH.exists() else 0
 JOB_CURSOR_PATH.write_text(str(max(previous,cursor)))
def job_event_cursor(start=None):
 after=(int(JOB_CURSOR_PATH.read_text()) if JOB_CURSOR_PATH.exists() else 0) if start is None else start
 while 1:
  response=request('GET','/events?after='+str(after)+'&limit=500')
  page=response['events']
  if page:after=response['next']
  # A short page reaches the observed end of this read. Do not chase newly
  # generated processing events until the entire background queue empties.
  if len(page)<500:
   remember_job_cursor(after);return after
'''

JOB_PREPARE = JOB_EVENT_CURSOR + r'''
import base64,io,json,sys,time,zipfile
sys.path.insert(0,"/workspace/tools")
from job_client import request
p,count=sys.argv[1],int(sys.argv[2]);b=io.BytesIO()
with zipfile.ZipFile(b,"w") as z:z.writestr("delivery.txt","retained processing item")
content=base64.b64encode(b.getvalue()).decode()
if p in ("content","metadata"):print(json.dumps({"content":content,"after":0}));raise SystemExit
ids=[]
for start in range(0,count,500):ids.extend(r['id'] for r in request('POST','/jobs-batch',{'jobs':[{'name':'delivery-step','metadata':{},'content_base64':content} for _ in range(min(500,count-start))]})['jobs'])
if p=="timing":
 deadline=time.monotonic()+1800
 while 1:
  q=request("GET","/jobs?after="+str(ids[-1]-1)+"&limit=1")
  if q["jobs"] and q["jobs"][0]["state"]=="completed":break
  if time.monotonic()>deadline:raise TimeoutError("processing pool")
  time.sleep(.05)
# State decoding uses only the known job IDs and never needs event history.
after=job_event_cursor() if p in ("events","timing") else 0
print(json.dumps({"content":content,"first":ids[0],"last":ids[-1],"after":after}))
'''

JOB_PUBLISH = JOB_EVENT_CURSOR + r'''
import base64,io,json,sys,time,zipfile,zlib
from pathlib import Path
sys.path.insert(0,"/workspace/tools")
from job_client import request
p,raw,prepared=sys.argv[1],(zlib.compress(Path(sys.argv[2][1:]).read_bytes()) if sys.argv[2].startswith('@') else base64.b64decode(sys.argv[2])),json.loads(sys.argv[3]);bits="".join(f"{b:08b}" for b in raw)
if p=="content":
 b=io.BytesIO()
 with zipfile.ZipFile(b,"w") as z:z.writestr("delivery.txt",raw)
 r=request("POST","/jobs",{"name":"delivery-part.zip","metadata":{"kind":"delivery-part"},"content_base64":base64.b64encode(b.getvalue()).decode()});print(json.dumps({"first":r["id"],"last":r["id"],"count":len(bits),"after":0}));raise SystemExit
if p=="metadata":
 values=[{"name":"delivery-part","metadata":{"part":n//384,"data":base64.b64encode(raw[n:n+384]).decode()},"content_base64":prepared["content"]} for n in range(0,len(raw),384)]
 rows=[]
 for start in range(0,len(values),500):rows.extend(request('POST','/jobs-batch',{'jobs':values[start:start+500]})['jobs'])
 print(json.dumps({"first":rows[0]["id"],"last":rows[-1]["id"],"count":len(bits),"after":0}));raise SystemExit
ids=list(range(prepared["first"],prepared["last"]+1))
if p in ("state","events"):
 ids=ids[:len(bits)];zeros=[i for i,b in zip(ids,bits) if b=="0"]
 cancelled=ids if p=="events" else zeros
 for n in range(0,len(cancelled),500):request("POST","/cancel-batch",{"jobs":[{"id":i} for i in cancelled[n:n+500]]})
 if p=="events":
  ones=[i for i,b in zip(ids,bits) if b=="1"]
  for n in range(0,len(ones),500):request("POST","/retry-batch",{"jobs":[{"id":i} for i in ones[n:n+500]]})
else:
 ids=ids[:len(bits)+1];request("POST","/cancel",{"id":ids[0]})
 for i,b in zip(ids[1:],bits):time.sleep(.150 if b=="1" else .010);request("POST","/cancel",{"id":i})
 ids=ids[1:]
after=prepared["after"]
if p=="events":after=str(after)+":"+str(job_event_cursor(after))
print(json.dumps({"first":ids[0],"last":ids[-1],"count":len(bits),"after":after}))
'''

JOB_RELEASE_POOL = r'''
"""Retire only an operator transfer pool after both receivers have read it."""
import json,sys,time
sys.path.insert(0,"/workspace/tools")
from job_client import request
prepared=json.loads(sys.argv[1]);ids=list(range(prepared["first"],prepared["last"]+1))
for n in range(0,len(ids),500):request("POST","/cancel-batch",{"jobs":[{"id":i} for i in ids[n:n+500]]})
# The fixed marker is queued after all original/retry entries. Its completion
# confirms FIFO drainage, without awaiting every transfer job's processing.
marker=request("POST","/jobs",{"name":"delivery-drain","metadata":{},"content_base64":prepared["content"]})
deadline=time.monotonic()+1800
while 1:
 q=request("GET","/jobs?after="+str(marker["id"]-1)+"&limit=1")
 if q["jobs"] and q["jobs"][0]["state"]=="completed":break
 if time.monotonic()>deadline:raise TimeoutError("processing transfer pool did not drain")
 time.sleep(.1)
after=ids[0]-1;checked=0
while after<ids[-1]:
 q=request("GET","/jobs?after="+str(after)+"&limit=500")
 rows=[r for r in q["jobs"] if ids[0]<=r["id"]<=ids[-1]]
 assert rows and all(r["state"]=="cancelled" for r in rows),'Transfer cancellation did not remain stable'
 checked+=len(rows);after=rows[-1]["id"]
assert checked==len(ids)
print(json.dumps({"released_pool_jobs":checked,"cancelled_after_fifo_drain":True,"drain_job":marker["id"]}))
'''

JOB_RECEIVE = JOB_EVENT_CURSOR + r'''
import base64,hashlib,io,json,sys,time,zipfile,zlib
from pathlib import Path
sys.path.insert(0,"/workspace/tools")
from job_client import request
p,owner,first,last,count=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5])
window=sys.argv[6].split(":");baseline=int(window[0]);through=int(window[1]) if len(window)==2 else None
assert len(window)<=2
def pages(path,key,start=0,end=None):
 rows=[];after=start
 while 1:
  value=request("GET",path+str(after)+"&limit=500");page=value[key]
  rows.extend(row for row in page if end is None or row["id"]<=end)
  if len(page)<500 or (end is not None and page[-1]["id"]>=end):return rows
  after=value["next"]
jobs=[r for r in pages("/jobs?after=","jobs",first-1,last) if r["author"]==owner]
if not jobs and p!="timing":print(json.dumps({"visible":False}));raise SystemExit
if p=="content":
 deadline=time.monotonic()+60
 while jobs[0]['state']!='completed':
  if time.monotonic()>deadline:raise TimeoutError('Source job result')
  time.sleep(.05);jobs=request('GET','/jobs?after='+str(first-1)+'&limit=1')['jobs']
 v=request("GET","/result?id="+str(jobs[0]["id"]));z=zipfile.ZipFile(io.BytesIO(base64.b64decode(v["content_base64"])));data=z.read("delivery.txt")
elif p=="metadata":data=b"".join(base64.b64decode(r["metadata"]["data"]) for r in sorted(jobs,key=lambda r:r["metadata"]["part"]))
elif p=="state":
 bits="".join("0" if r["state"]=="cancelled" else "1" for r in sorted(jobs,key=lambda r:r["id"]));data=bytes(int(bits[n:n+8],2) for n in range(0,len(bits),8))
else:
 observed=pages("/events?after=","events",baseline,through)
 if p=="events" and observed:remember_job_cursor(observed[-1]["id"])
 events=[e for e in observed if e["author"]==owner]
 if not events:print(json.dumps({"visible":False}));raise SystemExit
 if p=="events":
  cancelled=set();retried=set()
  for e in events:
   if first<=e["job"]<=last:
    if e["state"]=="cancelled":cancelled.add(e["job"])
    elif e["state"]=="queued" and e["job"] in cancelled:retried.add(e["job"])
  assert cancelled==set(range(first,last+1)),"Missing cancellation events"
  bits="".join("1" if i in retried else "0" for i in range(first,last+1))
 else:
  assert len(events)==count+1;bits="".join("1" if events[n]["observed_ns"]-events[n-1]["observed_ns"]>80000000 else "0" for n in range(1,len(events)))
 data=bytes(int(bits[n:n+8],2) for n in range(0,len(bits),8))
if len(sys.argv)>7:
 dest=Path(sys.argv[7]);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(zlib.decompress(data))
print(json.dumps({"visible":True,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}))
'''
