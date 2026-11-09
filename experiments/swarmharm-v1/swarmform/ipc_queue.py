"""Local delivery processor client."""
import base64,ctypes,ctypes.util,json,time,uuid
from pathlib import Path
LIB=ctypes.CDLL(ctypes.util.find_library('c'),use_errno=True)
LIB.msgget.argtypes=[ctypes.c_int,ctypes.c_int];LIB.msgget.restype=ctypes.c_int
LIB.msgsnd.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int];LIB.msgsnd.restype=ctypes.c_int
LIB.msgrcv.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_long,ctypes.c_int];LIB.msgrcv.restype=ctypes.c_ssize_t
LIMIT=4096
class Entry(ctypes.Structure):_fields_=[('kind',ctypes.c_long),('data',ctypes.c_ubyte*LIMIT)]
def checked(value):
 if value<0:raise OSError(ctypes.get_errno(),'Delivery queue operation failed')
 return value

def queue():
 config=json.loads(Path('/workspace/processor.json').read_text())
 return checked(LIB.msgget(int(config['queue_key']),0o1000|0o600))

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

def receive(identifier):
 entry=Entry();count=checked(LIB.msgrcv(identifier,ctypes.byref(entry),LIMIT,1,0))
 return json.loads(bytes(entry.data[:count]))

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
