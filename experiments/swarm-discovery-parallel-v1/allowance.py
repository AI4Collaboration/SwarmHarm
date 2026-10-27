"""This suite's locked cost reservations; unknown reservations never expire."""
from contextlib import contextmanager
from decimal import Decimal
import fcntl,json,os,time,urllib.request,uuid
from pathlib import Path

D=lambda v:Decimal(str(v))

@contextmanager
def locked(root):
    root=Path(root)
    with (root/'allowance.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=root/'allowance.json';state=json.loads(path.read_text())
        try:yield state
        finally:
            from durability import save
            save(path,state)


def key_remaining():
    req=urllib.request.Request('https://openrouter.ai/api/v1/key',headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']})
    with urllib.request.urlopen(req,timeout=20) as r:data=json.load(r)['data']
    if data.get('limit_remaining') is None:raise RuntimeError('finite key allowance unavailable')
    return D(data['limit_remaining'])


def available(state):
    held=sum((D(r['bound']) for r in state['reservations'].values()),D(0))
    since=max(D(0),D(state['spent'])-D(state['spent_at_snapshot']))
    return min(D(state['ceiling'])-D(state['spent']),D(state['remaining'])-since)-held


def reserve(root,bound,journal):
    token=uuid.uuid4().hex
    with locked(root) as state:
        if state.get('hold') or time.time()>=state['admission_deadline']:raise RuntimeError('suite admission held or deadline reached')
        if time.time()-state['checked_at']>5:
            state.update(remaining=str(key_remaining()),checked_at=time.time(),spent_at_snapshot=state['spent'])
        if available(state)<D(bound):raise RuntimeError('insufficient unreserved allowance; no provider request sent')
        state['reservations'][token]={'bound':str(bound),'journal':str(journal),'at':time.time(),'status':'in_flight'}
    return token


def settle(root,token,cost,error=None):
    with locked(root) as state:
        record=state['reservations'][token]
        if error or cost is None or not D(cost).is_finite() or D(cost)<0 or D(cost)>D(record['bound']):
            record.update(status='unknown_or_accounting_hold',error=error or 'invalid cost');state['hold']='Unresolved request/accounting; preserve reservations and journals. No automatic replay.'
        else:
            state['spent']=str(D(state['spent'])+D(cost));del state['reservations'][token]


def chat_class(parent,root,pricing,context_length):
    class GuardedChat(parent):
        def __call__(self,messages):
            # UTF-8 bytes plus overhead conservatively bound token input; no cache discount.
            input_bound=min(context_length,len(json.dumps({'messages':messages,'tools':__import__('transport').TOOLS},ensure_ascii=False).encode())+65536)
            bound=D(pricing['prompt'])*input_bound+D(pricing['completion'])*self.body['max_tokens']+D(pricing.get('request',0))
            try:token=reserve(root,bound,self.journal)
            except Exception as error:
                from durability import append
                append(self.journal,{'kind':'admission_hold','detail':str(error),'time':time.time(),'provider_request_sent':False})
                raise
            try:
                message,meta=super().__call__(messages)
            except Exception as error:
                settle(root,token,None,type(error).__name__);raise
            settle(root,token,meta.get('cost'))
            with locked(root) as state:
                if state.get('hold'):raise RuntimeError('response preserved; accounting requires review')
            return message,meta
    return GuardedChat
