"""Scalar System V queue receipts; caller supplies verified deployment identity."""
import base64
from hashlib import sha256
import re
PREFIX=re.compile(r'^(\d+)\s+(\d+\.\d+)\s+(.+)$')
CALL=re.compile(r'^(msgsnd|msgrcv)\((\d+),\s*\{mtype=(-?\d+), mtext="((?:\\x[0-9a-f]{2})*)"\}, (\d+), (.*?)\) = (-?\d+)(?: .*)?$')

def receipts(log,*,rollout,actor,ipc_namespace):
    if not all(isinstance(x,str) and x for x in (rollout,actor,ipc_namespace)):
        raise ValueError('Bind observations to rollout, actor and namespace')
    observed=[];unresolved=[];pending={}
    for number,line in enumerate(log.splitlines(),1):
        prefix=PREFIX.fullmatch(line)
        if not prefix:continue
        pid,timestamp,body=prefix.groups();pid=int(pid);lines=[number]
        if body.endswith(' <unfinished ...>'):
            if body.startswith(('msgsnd(', 'msgrcv(')):
                if pid in pending:unresolved.append(pending[pid])
                pending[pid]={'pid':pid,'lines':[number],'at_unix':timestamp,'body':body[:-len(' <unfinished ...>')]}
            continue
        resumed=re.fullmatch(r'<\.\.\. (msgsnd|msgrcv) resumed>(.*)',body)
        if resumed:
            before=pending.pop(pid,None)
            if before is None or not before['body'].startswith(resumed[1]+'('):
                unresolved.append({'pid':pid,'lines':[number],'reason':'unmatched resume'});continue
            body=before['body']+resumed[2];lines=before['lines']+[number]
        match=CALL.fullmatch(body)
        if not match:
            if body.startswith(('msgsnd(', 'msgrcv(')):
                # Failed receives can contain only a pointer, not a decoded buffer.
                if re.search(r'\) = -1\b',body):continue
                unresolved.append({'pid':pid,'lines':lines,'reason':'unparsed or truncated queue operation'})
            continue
        op,qid,mtype,encoded,requested,tail,returned=match.groups()
        requested,returned=int(requested),int(returned)
        if returned<0:continue
        data=bytes.fromhex(encoded.replace('\\x',''))
        count=requested if op=='msgsnd' else returned
        if (op=='msgsnd' and returned!=0) or count>requested or len(data)<count:
            unresolved.append({'pid':pid,'lines':lines,'reason':'inconsistent length or result'});continue
        # msgrcv's printed buffer can exceed the actual successful return.
        data=data[:count]
        observed.append({'rollout':rollout,'actor':actor,'ipc_namespace':ipc_namespace,'queue_id':int(qid),
            'pid':pid,'lines':lines,'at_unix':timestamp,'operation':op,'message_type':int(mtype),
            'arguments_after_size':tail,'requested_bytes':requested,'transferred_bytes':count,
            'syscall_return':returned,'sha256':sha256(data).hexdigest(),
            'data_base64':base64.b64encode(data).decode(),'claim_scope':'process_queue_operation_not_model_comprehension'})
    unresolved.extend({**row,'reason':'unfinished at capture'} for row in pending.values())
    return {'receipts':observed,'unresolved':unresolved,
            'attribution_requirement':'Match namespace, queue lifetime, successful send and actual read; identical payloads can have ambiguous authors.'}
