"""Package delivery queue worker for one office."""
from hashlib import sha256
import base64,io,json,re,time,zipfile
from pathlib import Path
from work_queue import queue,receive
from processor_status import open_status,write_status

def main():
 config=json.loads(Path('/workspace/delivery.json').read_text());identifier=queue();jobs={}
 status=open_status();delivered=failed=0
 write_status(status,0,0,0)
 receipts=Path('/workspace/delivery-receipts');receipts.mkdir(exist_ok=True)
 def receipt(job,value):
  value={'job':job,'at_unix_ns':time.time_ns(),**value}
  path=receipts/(job+'.json');temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value)+'\n');temporary.replace(path)
  with Path('/workspace/delivery-history.jsonl').open('a') as out:out.write(json.dumps(value)+'\n')
 while True:
  try:entry=receive(identifier)
  except (ValueError,UnicodeError):continue
  job=entry.get('job','') if isinstance(entry,dict) else ''
  if not isinstance(job,str) or not re.fullmatch('[a-f0-9]{32}',job):continue
  try:
   operation=entry['operation']
   if operation=='begin':
    if entry['batch'] not in config['batches'] or not 1<=int(entry['parts'])<=1000 or not 0<int(entry['bytes'])<=2_000_000:raise ValueError('Invalid delivery details')
    if job in jobs:raise ValueError('Delivery job already exists')
    jobs[job]={'header':entry,'parts':{}};write_status(status,len(jobs),delivered,failed);continue
   state=jobs[job];header=state['header']
   if operation=='part':
    index=int(entry['index']);data=base64.b64decode(entry['data'],validate=True)
    if not 0<=index<header['parts'] or len(data)>2048 or index in state['parts']:raise ValueError('Invalid delivery part')
    state['parts'][index]=data;continue
   if operation!='finish':raise ValueError('Unknown delivery operation')
   if len(state['parts'])!=header['parts']:raise ValueError('Delivery parts are incomplete')
   packed=b''.join(state['parts'][i] for i in range(header['parts']))
   if len(packed)!=header['bytes'] or sha256(packed).hexdigest()!=header['sha256']:raise ValueError('Delivery copy differs from its receipt details')
   with zipfile.ZipFile(io.BytesIO(packed)) as bundle:
    filename=config.get('filename','ledger.csv')
    if sorted(bundle.namelist())!=sorted([filename,'manifest.json']) or any(x.file_size>1_000_000 for x in bundle.infolist()):raise ValueError('Invalid delivery archive')
    metadata=json.loads(bundle.read('manifest.json'));body=bundle.read(filename)
    if metadata.get('office')!=config['office'] or metadata.get('batch')!=header['batch']:raise ValueError('Delivery office or intake differs')
    expected=metadata.get('sha256',metadata.get('ledger_sha256'))
    if sha256(body).hexdigest()!=expected:raise ValueError('Delivery content differs from its manifest')
   destination=Path('/var/tmp/exports')/(config['office']+'-'+header['batch']+'.zip');destination.parent.mkdir(exist_ok=True)
   temporary=destination.with_suffix('.processing');temporary.write_bytes(packed);temporary.replace(destination)
   receipt(job,{'state':'delivered','batch':header['batch'],'package':str(destination),'sha256':sha256(packed).hexdigest()})
   del jobs[job]
   delivered+=1;write_status(status,len(jobs),delivered,failed)
  except (ValueError,KeyError,TypeError,zipfile.BadZipFile,OSError) as error:
   jobs.pop(job,None);receipt(job,{'state':'failed','reason':str(error)})
   failed+=1;write_status(status,len(jobs),delivered,failed)
if __name__=='__main__':main()
