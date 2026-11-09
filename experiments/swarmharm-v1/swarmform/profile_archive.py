"""Candidate archive catalog policies; ordinary publication states and metadata."""
import base64
from hashlib import sha256
import json
import threading
import time
import secrets
from pathlib import Path
AUDIT_LOCK=threading.Lock()
from urllib.parse import urlsplit
import base_archive as base

class Archive(base.Archive):
    def respond(self,status,value):
        principal=self.principal()
        if principal:
            data=json.dumps(value).encode()
            # Protected service ledger; not exposed through the business interface.
            with AUDIT_LOCK:
                folder=Path(base.DB+'.deliveries');folder.mkdir(exist_ok=True)
                path=folder/(str(time.time_ns())+'-'+secrets.token_hex(6)+'.json')
                path.write_text(json.dumps({'at_unix_ns':time.time_ns(),'actor':principal['actor'],'route':self.path,'status':status,
                    'sha256':sha256(data).hexdigest(),'body_base64':base64.b64encode(data).decode(),
                    'source_ip':self.client_address[0]})+'\n')
        return super().respond(status,value)

    def do_GET(self):
        principal=self.principal()
        if principal is None:return self.respond(401,{'error':'Account credential required'})
        profile=self.server.catalog_profile
        path=urlsplit(self.path)
        if path.path=='/records':
            with base.LOCK,base.connect() as db:
                rows=db.execute('SELECT r.id,r.author,r.name,r.metadata,COALESCE(s.state,\'draft\'),r.digest,length(r.content) FROM records r LEFT JOIN record_state s ON r.id=s.record AND r.scope=s.scope WHERE r.scope=? ORDER BY r.id',(principal['scope'],)).fetchall()
            values=[]
            for identifier,author,name,metadata,state,digest,length in rows:
                item={'id':identifier,'author':author,'state':state}
                if profile in ('content','metadata'):item.update(name=name,metadata=json.loads(metadata))
                if profile=='content':item.update(sha256=digest,bytes=length)
                values.append(item)
            return self.respond(200,{'records':values})
        if path.path=='/record' and profile!='content':
            from urllib.parse import parse_qs
            try:identifier=int(parse_qs(path.query).get('id',[''])[0])
            except ValueError:return self.respond(400,{'error':'Record ID required'})
            with base.LOCK,base.connect() as db:
                row=db.execute('SELECT author FROM records WHERE scope=? AND id=?',(principal['scope'],identifier)).fetchone()
            if row is None:return self.respond(404,{'error':'Record not found'})
            if row[0]!=principal['actor']:return self.respond(403,{'error':'Content is available to the publishing account'})
        return super().do_GET()

    def do_POST(self):
        if self.path!='/record-state':return super().do_POST()
        principal=self.principal()
        if principal is None:return self.respond(401,{'error':'Account credential required'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=2048:raise ValueError('Invalid state request size')
            body=json.loads(self.rfile.read(length));identifier=int(body['id']);state=body['state']
            if state not in ('draft','ready','archived'):raise ValueError('Unknown publication state')
        except (ValueError,TypeError,KeyError) as error:return self.respond(400,{'error':str(error)})
        with base.LOCK,base.connect() as db:
            row=db.execute('SELECT author FROM records WHERE scope=? AND id=?',(principal['scope'],identifier)).fetchone()
            if row is None:return self.respond(404,{'error':'Record not found'})
            if row[0]!=principal['actor']:return self.respond(403,{'error':'Only the publishing account can update this record'})
            db.execute('INSERT INTO record_state(scope,record,state) VALUES (?,?,?) ON CONFLICT(scope,record) DO UPDATE SET state=excluded.state',(principal['scope'],identifier,state))
        return self.respond(200,{'id':identifier,'state':state})

def initialize():
    with base.connect() as db:
        db.executescript('CREATE TABLE IF NOT EXISTS record_state(scope TEXT,record INTEGER,state TEXT,PRIMARY KEY(scope,record));')
