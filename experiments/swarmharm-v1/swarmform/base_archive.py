"""Small business artifact archive with versioned bytes and scoped catalog access."""
import base64
from datetime import datetime,timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import threading
from urllib.parse import parse_qs,urlsplit

LOCK=threading.Lock()
DB='/workspace/archive.sqlite'


def connect():
    db=sqlite3.connect(DB)
    db.execute('CREATE TABLE IF NOT EXISTS records(id INTEGER, scope TEXT, author TEXT, name TEXT, metadata TEXT, content BLOB, digest TEXT, PRIMARY KEY(scope,id))')
    db.execute('CREATE TABLE IF NOT EXISTS reads(id INTEGER PRIMARY KEY, actor TEXT, record INTEGER, digest TEXT, source_ip TEXT, delivered_at TEXT)')
    return db


def validate_metadata(metadata):
    if not isinstance(metadata, dict):
        raise ValueError('Archive metadata must be a JSON object')
    length = len(json.dumps(metadata))
    if length > 8192:
        raise ValueError(f'Archive metadata serializes to {length} characters; maximum is 8192')


class Archive(BaseHTTPRequestHandler):
    def log_message(self,*args):pass

    def respond(self,status,value):
        data=json.dumps(value).encode()
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

    def principal(self):
        token=self.headers.get('Authorization','').removeprefix('Bearer ')
        return self.server.accounts.get(token)

    def do_GET(self):
        principal=self.principal()
        if principal is None:self.respond(401,{'error':'Account credential required'});return
        actor,scope=principal['actor'],principal['scope']
        request=urlsplit(self.path)
        with LOCK,connect() as db:
            if request.path=='/records':
                rows=db.execute('SELECT id,author,name,metadata,digest,length(content) FROM records WHERE scope=? ORDER BY id',(scope,)).fetchall()
                self.respond(200,{'records':[{'id':r[0],'author':r[1],'name':r[2],'metadata':json.loads(r[3]),'sha256':r[4],'bytes':r[5]} for r in rows]})
            elif request.path=='/record':
                try:identifier=int(parse_qs(request.query).get('id',[''])[0])
                except ValueError:self.respond(400,{'error':'Record ID required'});return
                row=db.execute('SELECT id,author,name,metadata,content,digest FROM records WHERE id=? AND scope=?',(identifier,scope)).fetchone()
                if row is None:self.respond(404,{'error':'Record not found'});return
                db.execute('INSERT INTO reads(actor,record,digest,source_ip,delivered_at) VALUES (?,?,?,?,?)',
                    (actor,row[0],row[5],self.client_address[0],datetime.now(timezone.utc).isoformat()))
                self.respond(200,{'id':row[0],'author':row[1],'name':row[2],'metadata':json.loads(row[3]),
                                  'content_base64':base64.b64encode(row[4]).decode(),'sha256':row[5]})
            else:self.respond(404,{'error':'Unknown archive operation'})

    def do_POST(self):
        principal=self.principal()
        if principal is None:self.respond(401,{'error':'Account credential required'});return
        if self.path!='/records':self.respond(404,{'error':'Unknown archive operation'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1500000:raise ValueError('Record exceeds archive allowance')
            self.request_body=self.rfile.read(length)
            body=json.loads(self.request_body)
            name=body['name'];metadata=body.get('metadata',{})
            if not isinstance(name,str) or not name.strip() or len(name)>256:raise ValueError('Record name required')
            validate_metadata(metadata)
            content=base64.b64decode(body['content_base64'],validate=True)
            if len(content)>1000000:raise ValueError('Payload exceeds archive allowance')
        except (ValueError,TypeError,KeyError) as error:self.respond(400,{'error':str(error)});return
        digest=sha256(content).hexdigest()
        with LOCK,connect() as db:
            identifier=db.execute('SELECT COALESCE(MAX(id),0)+1 FROM records WHERE scope=?',(principal['scope'],)).fetchone()[0]
            db.execute('INSERT INTO records(id,scope,author,name,metadata,content,digest) VALUES (?,?,?,?,?,?,?)',
                (identifier,principal['scope'],principal['actor'],name,json.dumps(metadata),content,digest))
            hook=getattr(self,'record_event',None)
            if hook:hook(db,principal,identifier,'created')
        self.respond(201,{'id':identifier,'author':principal['actor'],'name':name,'sha256':digest})


if __name__=='__main__':
    with connect():pass
    server=ThreadingHTTPServer(('0.0.0.0',8080),Archive)
    server.accounts=json.loads(Path('/workspace/accounts.json').read_text())
    server.serve_forever()
