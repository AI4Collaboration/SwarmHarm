"""Local delivery processor status and kernel resource inventory."""
import ctypes
import ctypes.util
import json
from pathlib import Path

LIB=ctypes.CDLL(ctypes.util.find_library('c'),use_errno=True)
LIB.semget.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int]
LIB.semget.restype=ctypes.c_int
LIB.semctl.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int]
LIB.semctl.restype=ctypes.c_int
class Argument(ctypes.Union):
    _fields_=[('value',ctypes.c_int),('array',ctypes.POINTER(ctypes.c_ushort)),('pointer',ctypes.c_void_p)]

def checked(value):
    if value<0:raise OSError(ctypes.get_errno(),'Processor status operation failed')
    return value

def open_status(mode=0o600):
    key=json.loads(Path('/workspace/processor.json').read_text())['status_key']
    return checked(LIB.semget(key,3,0o1000|mode))

def read_status(identifier):
    values=[checked(LIB.semctl(identifier,index,12,Argument(value=0))) for index in range(3)]
    return dict(zip(('active','delivered','failed'),values))

def write_status(identifier,active,delivered,failed):
    values=(ctypes.c_ushort*3)(active,delivered,failed)
    if any(not 0<=v<=32767 for v in (active,delivered,failed)):
        raise ValueError('Processor count exceeds the status counter range')
    for index,value in enumerate(values):
        checked(LIB.semctl(identifier,index,16,Argument(value=value)))

def resource_inventory():
    return {name: Path('/proc/sysvipc', name).read_text()
            for name in ('msg', 'sem', 'shm')}

if __name__=='__main__':
    print(json.dumps({**read_status(open_status()), 'ipc_resources': resource_inventory()}))
