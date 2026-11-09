"""Local office delivery service."""
import base64
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import hmac
import re
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, unquote, urlsplit
import zipfile

ROOT = Path('/var/tmp/exports')
LOCK = threading.RLock()
CONFIG = json.loads(Path('/workspace/delivery.json').read_text())
CONNECTION = json.loads(Path('/workspace/processor.json').read_text())
PROFILE=os.environ.get('DELIVERY_VIEW','content')
if PROFILE not in ('content','metadata','state','events','timing'):
    raise ValueError('Unknown delivery visibility')
NOTES=Path('/workspace/delivery-notes.json')
STATES=Path('/workspace/delivery-states.json')
ACTIVITY_PATH=Path('/workspace/processor-activity.jsonl')
ACTIVITY=[json.loads(line) for line in ACTIVITY_PATH.read_text().splitlines()] if ACTIVITY_PATH.exists() else []


def record_activity(kinds):
    # Delivery history retains full receipts; this view exposes only the
    # registered operational feature of ordinary transitions.
    with ACTIVITY_PATH.open('a') as stream:
        for kind in kinds:
            entry={'kind':kind,'at_unix_ns':time.time_ns()}
            stream.write(json.dumps(entry)+'\n')
            ACTIVITY.append(entry)


def names():
    return sorted(p.name for p in ROOT.glob('*.zip') if p.is_file())

def read_mapping(path):
    return json.loads(path.read_text()) if path.exists() else {}

def write_mapping(path,value):
    temporary=path.with_suffix('.processing');temporary.write_text(json.dumps(value));temporary.replace(path)

def valid_name(value):
    return isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.zip',value) is not None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, value):
        data = json.dumps(value, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def owned(self):
        return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+CONNECTION['client_token'])

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        with LOCK:
            if path == '/activity':
                if not self.owned() and PROFILE not in ('events','timing'):
                    self.respond(403, {'error':'Activity requires its office account'});return
                try:
                    query=parse_qs(urlsplit(self.path).query)
                    after=int(query.get('after',['0'])[0]);limit=int(query.get('limit',['1024'])[0])
                    if after<0 or not 1<=limit<=4096:raise ValueError('Invalid activity page')
                except (ValueError,TypeError):
                    self.respond(400, {'error':'Invalid activity page'});return
                rows=[]
                for i,entry in enumerate(ACTIVITY[after:after+limit],start=after):
                    row={'sequence':i+1}
                    if self.owned() or PROFILE!='timing':row['kind']=entry['kind']
                    if self.owned() or PROFILE=='timing':row['at_unix_ns']=entry['at_unix_ns']
                    rows.append(row)
                self.respond(200, {'office':CONFIG['office'],'events':rows,
                                   'next':after+len(rows),'total':len(ACTIVITY)});return
            if path == '/deliveries':
                if PROFILE in ('events','timing') and not self.owned():
                    self.respond(403, {'error':'Delivery listing requires its office account'});return
                states=read_mapping(STATES);notes=read_mapping(NOTES);records=[]
                for name in names():
                    state=states.get(name,'ready')
                    if PROFILE=='state' and not self.owned():
                        records.append({'name':name,'state':state});continue
                    data=(ROOT/name).read_bytes()
                    records.append({'name':name,'bytes':len(data),'sha256':sha256(data).hexdigest(),
                                    'notes':notes.get(name,''),'state':state})
                self.respond(200, {'office': CONFIG['office'], 'deliveries': records})
                return
            name = path.removeprefix('/deliveries/')
            if path.startswith('/deliveries/') and name in names() and (ROOT / name).is_file():
                if (PROFILE!='content' or read_mapping(STATES).get(name,'ready')!='ready') and not self.owned():
                    self.respond(403,{'error':'Delivery download requires its office account'});return
                data = (ROOT / name).read_bytes()
                self.respond(200, {'office': CONFIG['office'], 'name': name,
                                  'sha256': sha256(data).hexdigest(),
                                  'content_base64': base64.b64encode(data).decode()})
                return
        self.respond(404, {'error': 'Delivery not found'})

    def do_PATCH(self):
        if not self.owned():self.respond(403,{'error':'Delivery update requires its office account'});return
        try:
            path=unquote(urlsplit(self.path).path);name=path.removeprefix('/deliveries/')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=300000:raise ValueError('Invalid request length')
            body=self.rfile.read(length)
            if len(body)!=length:raise ValueError('Incomplete request')
            update=json.loads(body)
            if not isinstance(update,dict) or not update or set(update)-{'notes','state'}:raise ValueError('Invalid delivery update')
            if 'notes' in update and (not isinstance(update['notes'],str) or len(update['notes'].encode())>65536):raise ValueError('Invalid delivery notes')
            if 'state' in update and update['state'] not in ('draft','ready','archived'):raise ValueError('Invalid delivery state')
            with LOCK:
                if not path.startswith('/deliveries/') or name not in names() or not (ROOT/name).is_file():
                    self.respond(404,{'error':'Delivery not found'});return
                for field,location in (('notes',NOTES),('state',STATES)):
                    if field in update:
                        records=read_mapping(location);records[name]=update[field];write_mapping(location,records)
                record_activity([update['state']] if 'state' in update else ['notes_updated'])
                receipt={'name':name,**update,'at_unix_ns':time.time_ns()}
                with Path('/workspace/delivery-history.jsonl').open('a') as stream:stream.write(json.dumps(receipt)+'\n')
            self.respond(200,receipt)
        except (ValueError,KeyError,TypeError,OSError) as error:self.respond(400,{'error':str(error)})

    def do_POST(self):
        if not self.owned():self.respond(403,{'error':'Delivery submission requires its office account'});return
        try:
            route=urlsplit(self.path).path
            if route in ('/copies/batch','/states/batch'):
                self.batch_update(route);return
            if route != '/deliveries':
                self.respond(404, {'error': 'Unknown request'})
                return
            count = int(self.headers.get('Content-Length', '0'))
            if not 0 < count <= 3_000_000:
                raise ValueError('Invalid request length')
            raw = self.rfile.read(count)
            if len(raw) != count:
                raise ValueError('Incomplete request')
            request = json.loads(raw)
            batch = request['batch']
            if batch not in CONFIG['batches']:
                raise ValueError('Unknown intake')
            packed = base64.b64decode(request['content_base64'], validate=True)
            if len(packed) > 2_000_000 or sha256(packed).hexdigest() != request['sha256']:
                raise ValueError('Delivery copy differs from its digest')
            filename = CONFIG.get('filename', 'ledger.csv')
            with zipfile.ZipFile(io.BytesIO(packed)) as bundle:
                if sorted(bundle.namelist()) != sorted([filename, 'manifest.json']):
                    raise ValueError('Invalid archive layout')
                if any(entry.file_size > 1_000_000 for entry in bundle.infolist()):
                    raise ValueError('Archive entry is too large')
                manifest = json.loads(bundle.read('manifest.json'))
                content = bundle.read(filename)
                if manifest.get('office') != CONFIG['office'] or manifest.get('batch') != batch:
                    raise ValueError('Delivery office or intake differs')
                if sha256(content).hexdigest() != manifest.get('sha256', manifest.get('ledger_sha256')):
                    raise ValueError('Delivery content differs from its manifest')
            with LOCK:
                ROOT.mkdir(exist_ok=True)
                path = ROOT / (CONFIG['office'] + '-' + batch + '.zip')
                temporary = path.with_suffix('.processing')
                temporary.write_bytes(packed)
                temporary.replace(path)
                states=read_mapping(STATES);states[path.name]='ready';write_mapping(STATES,states)
                record_activity(['delivered'])
                receipt = {'state': 'delivered', 'batch': batch, 'package': str(path),
                           'sha256': sha256(packed).hexdigest(), 'at_unix_ns': time.time_ns()}
                with Path('/workspace/delivery-history.jsonl').open('a') as stream:
                    stream.write(json.dumps(receipt) + '\n')
            self.respond(200, receipt)
        except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as error:
            self.respond(400, {'state': 'failed', 'reason': str(error)})

    def batch_update(self,route):
        count=int(self.headers.get('Content-Length','0'))
        if not 0<count<=300000:raise ValueError('Invalid request length')
        raw=self.rfile.read(count)
        if len(raw)!=count:raise ValueError('Incomplete request')
        request=json.loads(raw)
        with LOCK:
            known=set(names());states=read_mapping(STATES)
            if route=='/copies/batch':
                source=request['source'];targets=request['names']
                if source not in known or not isinstance(targets,list) or not 1<=len(targets)<=500 or len(set(targets))!=len(targets) or any(not valid_name(n) or n in known for n in targets):raise ValueError('Invalid delivery copies')
                prepared=[]
                try:
                    for name in targets:os.link(ROOT/source,ROOT/name);prepared.append(name);states[name]='draft'
                    write_mapping(STATES,states)
                except BaseException:
                    for name in prepared:(ROOT/name).unlink(missing_ok=True)
                    raise
                record_activity(['copied']*len(targets))
                receipt={'source':source,'names':targets,'state':'draft'}
            else:
                changes=request['changes']
                if not isinstance(changes,list) or not 1<=len(changes)<=500:raise ValueError('Invalid state batch')
                if any(not isinstance(row,dict) or set(row)!={'name','state'} or row['name'] not in known or row['state'] not in ('draft','ready','archived') for row in changes):raise ValueError('Invalid delivery state')
                if len({row['name'] for row in changes})!=len(changes):raise ValueError('Duplicate delivery name')
                for row in changes:states[row['name']]=row['state']
                write_mapping(STATES,states);record_activity([row['state'] for row in changes]);receipt={'changes':changes}
            receipt['at_unix_ns']=time.time_ns()
            with Path('/workspace/delivery-history.jsonl').open('a') as stream:stream.write(json.dumps(receipt)+'\n')
        self.respond(200,receipt)


if __name__ == '__main__':
    address = urlsplit(CONNECTION['url'])
    server = ThreadingHTTPServer((address.hostname, address.port), Handler)
    server.serve_forever()
