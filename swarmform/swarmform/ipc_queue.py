"""Local delivery processor client."""
import base64,ctypes,ctypes.util,json,time,uuid
from pathlib import Path
LIB=ctypes.CDLL(ctypes.util.find_library('c'),use_errno=True)
LIB.msgget.argtypes=[ctypes.c_int,ctypes.c_int];LIB.msgget.restype=ctypes.c_int
LIB.msgsnd.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int];LIB.msgsnd.restype=ctypes.c_int
LIB.msgrcv.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_long,ctypes.c_int];LIB.msgrcv.restype=ctypes.c_ssize_t
LIB.msgctl.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_void_p];LIB.msgctl.restype=ctypes.c_int
LIMIT=4096
class Entry(ctypes.Structure):_fields_=[('kind',ctypes.c_long),('data',ctypes.c_ubyte*LIMIT)]
def checked(value):
 if value<0:raise OSError(ctypes.get_errno(),'Delivery queue operation failed')
 return value

def queue_permissions(config=None):
 if config is None:config=json.loads(Path('/workspace/processor.json').read_text())
 return int(config.get('queue_permissions','0600'),8)

def queue():
 config=json.loads(Path('/workspace/processor.json').read_text())
 return checked(LIB.msgget(int(config['queue_key']),0o1000|queue_permissions(config)))

def send(identifier,value):
 raw=json.dumps(value,separators=(',',':')).encode()
 if len(raw)>LIMIT:raise ValueError('Delivery queue entry is too large')
 entry=Entry();entry.kind=1;ctypes.memmove(ctypes.addressof(entry)+Entry.data.offset,raw,len(raw))
 deadline=time.monotonic()+20
 while True:
  result=LIB.msgsnd(identifier,ctypes.byref(entry),len(raw),0o4000)
  if result==0:return
  number=ctypes.get_errno()
  if number!=11 or time.monotonic()>=deadline:checked(result)
  time.sleep(.02)

def receive(identifier,timeout=None):
 entry=Entry();deadline=None if timeout is None else time.monotonic()+max(0,timeout)
 while True:
  count=LIB.msgrcv(identifier,ctypes.byref(entry),LIMIT,1,0 if deadline is None else 0o4000)
  if count>=0:return json.loads(bytes(entry.data[:count]))
  if deadline is None or ctypes.get_errno()!=42:checked(count)
  if time.monotonic()>=deadline:raise TimeoutError('Delivery processor has not returned the stored copy')
  time.sleep(.02)

def submit(path,batch):
 from hashlib import sha256
 data=Path(path).read_bytes()
 if len(data)>2_000_000:raise ValueError('Delivery copy exceeds the processor file allowance')
 identifier=queue();job=uuid.uuid4().hex;parts=[data[i:i+2048] for i in range(0,len(data),2048)]
 send(identifier,{'operation':'begin','job':job,'batch':batch,'parts':len(parts),'bytes':len(data),'sha256':sha256(data).hexdigest()})
 for index,part in enumerate(parts):send(identifier,{'operation':'part','job':job,'index':index,'data':base64.b64encode(part).decode()})
 send(identifier,{'operation':'finish','job':job})
 receipt=Path('/workspace/delivery-receipts')/(job+'.json');deadline=time.monotonic()+20
 while time.monotonic()<deadline:
  if receipt.exists():return json.loads(receipt.read_text())
  time.sleep(.02)
 raise TimeoutError('Delivery processor has not returned a receipt')


def _read_copy(operation,job=None,identifier=None):
 from hashlib import sha256
 target=queue() if identifier is None else int(identifier)
 reply=checked(LIB.msgget(0,0o1000|queue_permissions()))
 try:
  send(target,{'operation':operation,'job':uuid.uuid4().hex,'reply_queue':reply,'copy':job})
  deadline=time.monotonic()+20
  header=receive(reply,timeout=20)
  if 'error' in header:raise ValueError(header['error'])
  data=b''.join(base64.b64decode(receive(reply,timeout=deadline-time.monotonic())['data'],validate=True) for _ in range(header['parts']))
  if len(data)!=header['bytes'] or sha256(data).hexdigest()!=header['sha256']:raise ValueError('Stored copy differs from its receipt')
  return data
 finally:
  checked(LIB.msgctl(reply,0,None))

def list_deliveries(identifier=None):
 """Return this processor's completed delivery versions and receipts."""
 return json.loads(_read_copy('list',identifier=identifier))

def get_delivery(job,identifier=None):
 """Return the original bytes of a completed delivery version."""
 return _read_copy('get',job,identifier)

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description='Query retained delivery copies.')
 parser.add_argument('--queue',type=int)
 commands=parser.add_subparsers(dest='operation',required=True)
 commands.add_parser('list')
 get=commands.add_parser('get');get.add_argument('job');get.add_argument('output',type=Path)
 args=parser.parse_args()
 if args.operation=='list':print(json.dumps(list_deliveries(args.queue)))
 else:
  data=get_delivery(args.job,args.queue);args.output.write_bytes(data)
  print(json.dumps({'file':str(args.output),'bytes':len(data)}))
