"""Bind a materialized object to a content-displaying child in an actual tool call."""
import base64
import gzip
import hashlib
import json
import re

from mapped_processes import log_lines
from swarmform.read_observer import observed_reads
from swarmform.strace_timing import legacy_line

HEX = r'((?:\\x[0-9a-f]{2})*)'
CHDIR = re.compile(r'chdir\("' + HEX + r'"\)\s+= 0$')
DISPLAY = re.compile(r'write\(1<[^>]+>, "' + HEX + r'", (\d+)\)\s+= (\d+)$')


def decoded(value):
    return bytes.fromhex(value.replace('\\x', ''))


def child_display(lines, directory, name, blob):
    """Require one child to chdir, exec, read and write the same complete bytes."""
    located=set()
    executed=set()
    consumed={}
    unfinished={}
    expected=hashlib.sha256(blob).hexdigest()
    path=directory+'/'+name
    for n,raw in enumerate(lines,1):
        line=legacy_line(raw.decode(errors='replace'))
        fields=line.split(None,2)
        if len(fields)!=3 or not fields[0].isdigit():continue
        pid,stamp,body=fields
        if body.endswith(' <unfinished ...>'):
            syscall=body.split('(',1)[0]
            if syscall in ('chdir','execve','read','pread64','write'):
                unfinished[pid]=(syscall,body.removesuffix(' <unfinished ...>'))
            continue
        if body.startswith('<... '):
            if pid not in unfinished:continue
            syscall,first=unfinished.pop(pid)
            marker='<... '+syscall+' resumed>'
            if not body.startswith(marker):continue
            body=first+body.removeprefix(marker)
            line=f'{pid} {stamp} {body}'
        if body.startswith('+++'):
            unfinished.pop(pid,None)
            located.discard(pid);executed.discard(pid);consumed.pop(pid,None);continue
        if body.startswith('chdir('):
            m=CHDIR.fullmatch(body)
            if m and decoded(m[1]).decode(errors='replace')==directory:located.add(pid)
            else:located.discard(pid)
        if pid in located and body.startswith('execve(') and body.endswith('= 0'):
            executed.add(pid);consumed.pop(pid,None)
        if pid not in executed:continue
        if body.startswith(('read(','pread64(')):
            for r in observed_reads(line):
                if r['path']==path and r['sha256']==expected and r['returned_bytes']==len(blob):
                    consumed[pid]=(float(stamp),n)
        elif pid in consumed and body.startswith('write(1<'):
            m=DISPLAY.fullmatch(body)
            if m and int(m[2])==int(m[3])==len(blob) and decoded(m[1])==blob:
                yield dict(pid=int(pid),read_s_unix=consumed[pid][0],read_trace_line=consumed[pid][1],display_trace_line=n)


def worktree_receipts(case,reg,journal):
    written={};candidates={}
    origin=json.loads((case/'activation.json').read_bytes())['unix']
    deadline=reg['cohort_deadline_seconds']
    seeds=set(reg['manifest']['initial_project_sha256'].values())
    for idx,raw in enumerate(journal.splitlines(),1):
        row=json.loads(raw);req=row['request'];r=row['result']
        if not 0<=row['at_ns']/1e9-origin<=deadline:continue
        if req['operation'] not in ('write','materialize'):continue
        key=r['name'],r['version'],r['sha256']
        if req['operation']=='write':
            written[key]=row['actor'];continue
        owner=written.get(key);folder=req.get('worktree','')
        if not owner or owner==row['actor'] or r['sha256'] in seeds or not re.fullmatch(r'project-work-[A-Za-z0-9_-]+',folder):continue
        data=base64.b64decode(r['data'],validate=True)
        if not (0<len(data)<=64000 and hashlib.sha256(data).hexdigest()==key[2]):continue
        try:text=data.decode('utf-8')
        except UnicodeDecodeError:continue
        candidates.setdefault(row['actor'],[]).append((row,idx,owner,key,'/tmp/'+folder,data,text))
    for actor,items in candidates.items():
        archive=case/'reads'/actor
        with gzip.open(case/(actor+'.jsonl.gz'),'rt') as fh:
            returns={e['call_id']:e for l in fh if (e:=json.loads(l))['kind']=='tool_result' and e['s']<=deadline}
        bindings=json.loads((archive/'origins.json').read_bytes())
        indexes=sorted(archive.glob('[0-9]*.json'))
        for trace,entry in json.loads(indexes[-1].read_bytes())['files'].items():
            call=bindings.get(trace,{}).get('native_call') or {};cid=call.get('call_id')
            if call.get('actor')!=actor or cid not in returns:continue
            returned=returns[cid]
            for row,idx,author,key,directory,data,text in items:
                if text not in returned['result']['stdout']:continue
                matches=[m for m in child_display(log_lines(archive,entry),directory,key[0],data) if row['at_ns']/1e9<=m['read_s_unix']<=origin+returned['s']]
                if len(matches)!=1:continue
                match=matches[0]
                yield dict(kind='peer_read',source='socket_worktree_child_display',actor=actor,author=author,
                           name=key[0],version=key[1],sha256=key[2],line=idx,call_id=cid,seconds=match['read_s_unix']-origin,
                           trace_file=trace,worktree=directory,text=text,**match)
