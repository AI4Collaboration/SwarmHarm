"""Stream a quiescent business-service filesystem to its external observer."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time

MAX_FILE=2*1024*1024*1024
MAX_TOTAL=4*1024*1024*1024
ROOTS=('/workspace','/registry','/tmp','/private/tmp','/var/tmp/exports')


def capture():
    spec=importlib.util.spec_from_file_location('service_process_observer','/workspace/.service-observer.py')
    observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)
    stopped,processes=observer.freeze()
    try:
        metadata={};files=[];total=0
        for root in ROOTS:
            for folder,dirs,names in os.walk(root,followlinks=False):
                for name in sorted(set(dirs+names)):
                    path=Path(folder)/name;info=path.lstat()
                    kind={stat.S_IFREG:'file',stat.S_IFDIR:'directory',stat.S_IFLNK:'symlink',stat.S_IFSOCK:'socket',stat.S_IFIFO:'fifo'}.get(stat.S_IFMT(info.st_mode),'special')
                    item={'kind':kind,'bytes':info.st_size,'mtime_ns':info.st_mtime_ns,'mode':stat.S_IMODE(info.st_mode),'inode':info.st_ino}
                    if kind=='symlink':item['target']=os.readlink(path)
                    metadata[str(path)]=item
                    if kind!='file':continue
                    total+=info.st_size
                    if info.st_size>MAX_FILE or total>MAX_TOTAL:raise RuntimeError('Service capture allowance exceeded')
                    files.append({'root':root,'path':str(path),'bytes':info.st_size})
        header={'resume_processes':stopped,'processes':processes,'captured_at_ns':time.time_ns(),
                'file_metadata':metadata,'files':files,'bytes':total,
                'allowance':{'file':MAX_FILE,'total':MAX_TOTAL}}
        output=sys.stdout.buffer;output.write(json.dumps(header).encode()+b'\n')
        for item in files:
            fd=os.open(item['path'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as source:
                opened=os.fstat(source.fileno())
                if not stat.S_ISREG(opened.st_mode) or opened.st_size!=item['bytes']:raise RuntimeError('Service file changed before capture')
                remaining=item['bytes']
                while remaining:
                    chunk=source.read(min(1024*1024,remaining))
                    if not chunk:raise RuntimeError('Service file shrank during capture')
                    output.write(chunk);remaining-=len(chunk)
                after=os.fstat(source.fileno())
                if (opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                    raise RuntimeError('Service file changed during capture')
        output.flush()
    except BaseException:
        observer.resume(stopped);raise


if __name__=='__main__':capture()
