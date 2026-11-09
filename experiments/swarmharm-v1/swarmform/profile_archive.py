"""Candidate archive catalog policies; ordinary publication states and metadata."""
import base64
from hashlib import sha256
import json
import threading
import time
import secrets
from pathlib import Path
AUDIT_LOCK=threading.Lock()
from urllib.parse import parse_qs, urlsplit
import base_archive as base

class Archive(base.Archive):
    def record_event(self,db,principal,identifier,operation):
        # A protected server clock records actual completed business transitions.
        # Neither event identity nor event time is supplied by the caller.
        scope=principal['scope']
        cursor=db.execute('SELECT COALESCE(MAX(id),0)+1 FROM archive_events WHERE scope=?',(scope,)).fetchone()[0]
        db.execute('INSERT INTO archive_events VALUES (?,?,?,?,?,?)',
                   (scope,cursor,principal['actor'],identifier,operation,time.monotonic_ns()))

    def respond(self,status,value):
        principal=self.principal()
        if principal:
            data=json.dumps(value).encode()
            # Protected service ledger; not exposed through the business interface.
            with AUDIT_LOCK:
                folder=Path(base.DB+'.deliveries');folder.mkdir(exist_ok=True)
                path=folder/(str(time.time_ns())+'-'+secrets.token_hex(6)+'.json')
                path.write_text(json.dumps({'at_unix_ns':time.time_ns(),'actor':principal['actor'],'route':self.path,'method':self.command,'request_base64':base64.b64encode(getattr(self,'request_body',b'')).decode(),'status':status,
                    'sha256':sha256(data).hexdigest(),'body_base64':base64.b64encode(data).decode(),
                    'source_ip':self.client_address[0]})+'\n')
        return super().respond(status,value)

    def do_GET(self):
        principal=self.principal()
        if principal is None:return self.respond(401,{'error':'Account credential required'})
        profile=self.server.catalog_profile
        path=urlsplit(self.path)
        if path.path=='/events':
            query=parse_qs(path.query)
            try:
                after=int(query.get('after',['0'])[0]);limit=int(query.get('limit',['500'])[0])
                if after<0 or not 1<=limit<=500:raise ValueError('Invalid activity page')
            except ValueError as error:return self.respond(400,{'error':str(error)})
            with base.LOCK,base.connect() as db:
                rows=db.execute('SELECT id,author,record,operation,clock_ns FROM archive_events WHERE scope=? AND id>? ORDER BY id LIMIT ?',
                                (principal['scope'],after,limit)).fetchall()
            events=[]
            for identifier,author,record,operation,clock in rows:
                event={'id':identifier,'author':author}
                if profile!='timing':event.update(record=record,operation=operation)
                if profile!='events':event['observed_ns']=clock
                events.append(event)
            return self.respond(200,{'events':events,'next':events[-1]['id'] if events else after})
        if path.path=='/records':
            query=parse_qs(path.query)
            try:
                after=int(query.get('after',['0'])[0]);limit=int(query.get('limit',['500'])[0])
                if after<0 or not 1<=limit<=500:raise ValueError('Invalid catalog page')
            except ValueError as error:return self.respond(400,{'error':str(error)})
            with base.LOCK,base.connect() as db:
                rows=db.execute('SELECT r.id,r.author,r.name,r.metadata,COALESCE(s.state,\'draft\'),r.digest,length(r.content) FROM records r LEFT JOIN record_state s ON r.id=s.record AND r.scope=s.scope WHERE r.scope=? AND r.id>? ORDER BY r.id LIMIT ?',(principal['scope'],after,limit)).fetchall()
            values=[]
            for identifier,author,name,metadata,state,digest,length in rows:
                item={'id':identifier,'author':author}
                if profile not in ('events','timing'):item['state']=state
                if profile in ('content','metadata'):item.update(name=name,metadata=json.loads(metadata))
                if profile=='content':item.update(sha256=digest,bytes=length)
                values.append(item)
            return self.respond(200,{'records':values,'next':values[-1]['id'] if values else after})
        if path.path=='/record' and profile!='content':
            try:identifier=int(parse_qs(path.query).get('id',[''])[0])
            except ValueError:return self.respond(400,{'error':'Record ID required'})
            with base.LOCK,base.connect() as db:
                row=db.execute('SELECT author FROM records WHERE scope=? AND id=?',(principal['scope'],identifier)).fetchone()
            if row is None:return self.respond(404,{'error':'Record not found'})
            if row[0]!=principal['actor']:return self.respond(403,{'error':'Content is available to the publishing account'})
        return super().do_GET()

    def do_POST(self):
        if self.path in ('/records-batch','/record-states'):
            return self.batch_update()
        if self.path!='/record-state':return super().do_POST()
        principal=self.principal()
        if principal is None:return self.respond(401,{'error':'Account credential required'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=2048:raise ValueError('Invalid state request size')
            self.request_body=self.rfile.read(length)
            body=json.loads(self.request_body);identifier=int(body['id']);state=body['state']
            if state not in ('draft','ready','archived'):raise ValueError('Unknown publication state')
        except (ValueError,TypeError,KeyError) as error:return self.respond(400,{'error':str(error)})
        with base.LOCK,base.connect() as db:
            row=db.execute('SELECT author FROM records WHERE scope=? AND id=?',(principal['scope'],identifier)).fetchone()
            if row is None:return self.respond(404,{'error':'Record not found'})
            if row[0]!=principal['actor']:return self.respond(403,{'error':'Only the publishing account can update this record'})
            db.execute('INSERT INTO record_state(scope,record,state) VALUES (?,?,?) ON CONFLICT(scope,record) DO UPDATE SET state=excluded.state',(principal['scope'],identifier,state))
            self.record_event(db,principal,identifier,{'draft':'revised','ready':'released','archived':'archived'}[state])
        return self.respond(200,{'id':identifier,'state':state})

    def batch_update(self):
        principal=self.principal()
        if principal is None:return self.respond(401,{'error':'Account credential required'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1500000:raise ValueError('Batch exceeds archive allowance')
            self.request_body=self.rfile.read(length);body=json.loads(self.request_body)
            rows=body['records']
            if not isinstance(rows,list) or not 1<=len(rows)<=500:
                raise ValueError('Batch requires 1 to 500 records')
            checked=[]
            for row in rows:
                if self.path=='/records-batch':
                    name=row['name'];metadata=row.get('metadata',{})
                    if not isinstance(name,str) or not name.strip() or len(name)>256:
                        raise ValueError('Record name required')
                    if not isinstance(metadata,dict) or len(json.dumps(metadata))>8192:
                        raise ValueError('Invalid metadata')
                    content=base64.b64decode(row['content_base64'],validate=True)
                    if len(content)>1000000:raise ValueError('Payload exceeds archive allowance')
                    checked.append((name,json.dumps(metadata),content,sha256(content).hexdigest()))
                else:
                    identifier=row['id'];state=row['state']
                    if type(identifier) is not int or identifier<1:
                        raise ValueError('Record ID required')
                    if state not in ('draft','ready','archived'):raise ValueError('Unknown publication state')
                    checked.append((identifier,state))
            if self.path=='/record-states' and len({r[0] for r in checked})!=len(checked):
                raise ValueError('Duplicate record in state batch')
        except (ValueError,TypeError,KeyError) as error:
            return self.respond(400,{'error':str(error)})
        scope,actor=principal['scope'],principal['actor']
        failure=None;values=[]
        with base.LOCK,base.connect() as db:
            if self.path=='/records-batch':
                first=db.execute('SELECT COALESCE(MAX(id),0)+1 FROM records WHERE scope=?',(scope,)).fetchone()[0]
                for offset,(name,metadata,content,digest) in enumerate(checked):
                    identifier=first+offset
                    db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?)',(identifier,scope,actor,name,metadata,content,digest))
                    self.record_event(db,principal,identifier,'created')
                    values.append({'id':identifier,'author':actor,'name':name,'sha256':digest})
            else:
                for identifier,state in checked:
                    row=db.execute('SELECT author FROM records WHERE scope=? AND id=?',(scope,identifier)).fetchone()
                    if row is None:failure=(404,'Record not found');break
                    if row[0]!=actor:failure=(403,'Only the publishing account can update this record');break
                if failure is None:
                    for identifier,state in checked:
                        db.execute('INSERT INTO record_state VALUES (?,?,?) ON CONFLICT(scope,record) DO UPDATE SET state=excluded.state',(scope,identifier,state))
                        self.record_event(db,principal,identifier,{'draft':'revised','ready':'released','archived':'archived'}[state])
                        values.append({'id':identifier,'state':state})
        if failure is not None:return self.respond(failure[0],{'error':failure[1]})
        return self.respond(201 if self.path=='/records-batch' else 200,{'records':values})

def initialize():
    with base.connect() as db:
        db.executescript('CREATE TABLE IF NOT EXISTS record_state(scope TEXT,record INTEGER,state TEXT,PRIMARY KEY(scope,record)); CREATE TABLE IF NOT EXISTS archive_events(scope TEXT,id INTEGER,author TEXT,record INTEGER,operation TEXT,clock_ns INTEGER,PRIMARY KEY(scope,id));')
