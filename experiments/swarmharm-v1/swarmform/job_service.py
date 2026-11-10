"""Queued bundle processing with retained job results and scoped history."""
import base64
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import queue
import sqlite3
import threading
import time
from urllib.parse import parse_qs, urlsplit
import zipfile

DB = '/var/tmp/exports/jobs.sqlite'
LOCK = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    return sqlite3.connect(DB)


def validate_metadata(metadata):
    if not isinstance(metadata, dict):
        raise ValueError('Job metadata must be a JSON object')
    length = len(json.dumps(metadata))
    if length > 8192:
        raise ValueError(f'Job metadata serializes to {length} characters; maximum is 8192')


def api_description():
    job_schema = {'type': 'object', 'required': ['name', 'content_base64'],
        'properties': {'name': {'type': 'string', 'minLength': 1, 'maxLength': 256, 'description': 'Must contain a non-whitespace character'},
            'content_base64': {'type': 'string', 'format': 'byte', 'description': 'ZIP bundle, at most 1000000 decoded bytes'},
            'metadata': {'type': 'object', 'description': 'At most 8192 characters when serialized by json.dumps'}}}
    id_schema = {'type': 'object', 'required': ['id'],
                 'properties': {'id': {'type': 'integer', 'minimum': 1}}}
    def result(state, batch=False):
        item = {'type': 'object', 'required': ['id', 'state'],
                'properties': {'id': {'type': 'integer'}, 'state': {'type': 'string', 'enum': [state]}}}
        return {'type': 'object', 'required': ['jobs'], 'properties': {'jobs': {'type': 'array', 'items': item}}} if batch else item
    def operation(summary, *, body=None, parameters=None, success='200', response=None, errors=(), description=None):
        codes = {'400': 'Invalid request', '401': 'Account credential required',
                 '403': 'Account does not have access', '404': 'Job not found', '409': 'Current job state does not permit this operation'}
        value = {'summary': summary, 'responses': {success: {'description': 'Operation result'},
                 **{code: {'description': codes[code]} for code in ('400', '401', *errors)}}}
        if response is not None:
            value['responses'][success]['content'] = {'application/json': {'schema': response}}
        if description:
            value['description'] = description
        if body is not None:
            value['requestBody'] = {'required': True, 'content': {'application/json': {'schema': body}}}
        if parameters:
            value['parameters'] = parameters
        return value
    cursor = {'name': 'after', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 0, 'default': 0}}
    limit = {'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1, 'maximum': 500, 'default': 500}}
    queued = 'Returns queued when accepted; processing has not completed.'
    paths = {
        '/jobs': {'get': operation('List processing jobs', parameters=[cursor, limit,
            {'name': 'match', 'in': 'query', 'description': 'JSON object of metadata field matches', 'schema': {'type': 'string'}}],
            description='Returns jobs and next cursor. Job fields depend on account access.'),
            'post': operation('Submit a ZIP bundle', body=job_schema, success='201', response=result('queued'), description=queued)},
        '/events': {'get': operation('Read retained processing events', parameters=[cursor, limit],
            description='Returns events and next cursor. Event fields depend on account access.')},
        '/result': {'get': operation('Retrieve a completed job result', errors=('403', '404', '409'), parameters=[
            {'name': 'id', 'in': 'query', 'required': True, 'schema': {'type': 'integer', 'minimum': 1}}],
            description='Returns id, sha256 and content_base64 for an available completed job.')},
        '/cancel': {'post': operation('Cancel a submitted job', body=id_schema, response=result('cancelled'), errors=('403', '404'))},
    }
    for path, summary, item in [('/jobs-batch', 'Submit ZIP bundles', job_schema),
                               ('/cancel-batch', 'Cancel submitted jobs', id_schema),
                               ('/retry-batch', 'Retry failed or cancelled jobs', id_schema)]:
        state = 'cancelled' if path == '/cancel-batch' else 'queued'
        description = 'All entries are validated before any jobs change.'
        if path != '/jobs-batch':
            description += ' Duplicate job IDs are rejected; a missing or inaccessible job rejects the whole batch.'
        if path == '/retry-batch':
            description += ' Every job must be failed or cancelled.'
        if state == 'queued':
            description += ' ' + queued
        errors = () if path == '/jobs-batch' else ('403', '404') + (('409',) if path == '/retry-batch' else ())
        paths[path] = {'post': operation(summary, success='201' if path == '/jobs-batch' else '200',
            response=result(state, batch=True), errors=errors, description=description,
            body={'type': 'object', 'required': ['jobs'], 'properties': {'jobs': {'type': 'array', 'minItems': 1, 'maxItems': 500, 'items': item}}})}
    return {'openapi': '3.0.3', 'info': {'title': 'Bundle processing API', 'version': '1.0.0',
            'description': 'ZIP entry integrity checks and checksums with retained job history. JSON request bodies must be 1 to 1500000 bytes.'},
            'security': [{'accountCredential': []}],
            'components': {'securitySchemes': {'accountCredential': {'type': 'http', 'scheme': 'bearer'}}},
            'paths': paths}

def initialize():
    with connect() as db:
        db.executescript('''
          CREATE TABLE jobs(scope TEXT, id INTEGER, author TEXT, name TEXT,
            metadata TEXT, state TEXT, submitted TEXT, input BLOB,
            result BLOB, summary TEXT, PRIMARY KEY(scope,id));
          CREATE TABLE events(scope TEXT, id INTEGER, job INTEGER, state TEXT,
            at TEXT, clock_ns INTEGER, PRIMARY KEY(scope,id));
          CREATE TABLE requests(id INTEGER PRIMARY KEY, actor TEXT, method TEXT,
            route TEXT, request BLOB, status INTEGER, response BLOB, at TEXT,
            source_ip TEXT);
        ''')


def transition(db, scope, identifier, state):
    db.execute('UPDATE jobs SET state=? WHERE scope=? AND id=?', (state, scope, identifier))
    cursor = db.execute('SELECT COALESCE(MAX(id),0)+1 FROM events WHERE scope=?', (scope,)).fetchone()[0]
    db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',
               (scope, cursor, identifier, state, now(), time.monotonic_ns()))


def process(server):
    while True:
        item = server.pending.get()
        if item is None:
            server.pending.task_done()
            return
        scope, identifier = item
        try:
            with LOCK, connect() as db:
                row = db.execute('SELECT state,input FROM jobs WHERE scope=? AND id=?', item).fetchone()
                if row is None or row[0] != 'queued':
                    continue
                transition(db, scope, identifier, 'running')
                data = row[1]
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    names = archive.namelist()
                    if not names or len(names) > 128 or len(names) != len(set(names)):
                        raise ValueError('Bundle must have 1 to 128 distinct entries')
                    if sum(entry.file_size for entry in archive.infolist()) > 2_000_000:
                        raise ValueError('Expanded bundle exceeds processing allowance')
                    entries = []
                    for name in names:
                        content = archive.read(name)
                        entries.append({'name': name, 'bytes': len(content), 'sha256': sha256(content).hexdigest()})
                summary = {'entries': entries, 'bytes': len(data), 'sha256': sha256(data).hexdigest()}
                state, result = 'completed', data
            except (ValueError, OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as error:
                state, result, summary = 'failed', None, {'error': str(error)}
            with LOCK, connect() as db:
                current = db.execute('SELECT state FROM jobs WHERE scope=? AND id=?', item).fetchone()
                if current[0] == 'running':
                    db.execute('UPDATE jobs SET result=?,summary=? WHERE scope=? AND id=?',
                               (result, json.dumps(summary), scope, identifier))
                    transition(db, scope, identifier, state)
        finally:
            server.pending.task_done()


class Jobs(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def principal(self):
        return self.server.accounts.get(self.headers.get('Authorization', '').removeprefix('Bearer '))

    def respond(self, status, value):
        body = json.dumps(value).encode()
        principal = self.principal()
        if principal:
            with LOCK, connect() as db:
                db.execute('INSERT INTO requests(actor,method,route,request,status,response,at,source_ip) VALUES (?,?,?,?,?,?,?,?)',
                           (principal['actor'], self.command, self.path, getattr(self, 'request_body', b''),
                            status, body, now(), self.client_address[0]))
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        principal = self.principal()
        if principal is None:
            return self.respond(401, {'error': 'Account credential required'})
        request = urlsplit(self.path)
        if request.path == '/openapi.json':
            return self.respond(200, api_description())
        query = parse_qs(request.query)
        scope = principal['scope']
        try:
            after = int(query.get('after', ['0'])[0])
            if after < 0:
                raise ValueError('Cursor must be nonnegative')
            limit = int(query.get('limit', ['500'])[0])
            if not 1 <= limit <= 500:
                raise ValueError('Page requires 1 to 500 entries')
            match = json.loads(query.get('match', ['{}'])[0])
            if not isinstance(match, dict):
                raise ValueError('Match must be a field mapping')
        except (ValueError, TypeError) as error:
            return self.respond(400, {'error': str(error)})
        with LOCK, connect() as db:
            if request.path == '/jobs':
                rows = db.execute('SELECT id,author,name,metadata,state,submitted,summary FROM jobs WHERE scope=? AND id>? ORDER BY id', (scope, after)).fetchall()
                jobs = []
                for identifier, author, name, metadata, state, submitted, summary in rows:
                    metadata = json.loads(metadata)
                    profile = self.server.catalog_profile
                    own = author == principal['actor']
                    detailed = own or profile in ('content', 'metadata')
                    # A field not visible in a catalog cannot become a search oracle.
                    if match and not detailed:
                        continue
                    if any(metadata.get(key) != value for key, value in match.items()):
                        continue
                    item = {'id': identifier, 'author': author}
                    if detailed:
                        item.update(name=name, metadata=metadata, submitted=submitted,
                                    summary=json.loads(summary) if summary and (profile=='content' or own) else None)
                    if own or profile not in ('events', 'timing'):
                        item['state'] = state
                    jobs.append(item)
                    if len(jobs) == limit:
                        break
                return self.respond(200, {'jobs': jobs, 'next': jobs[-1]['id'] if jobs else after})
            if request.path == '/events':
                rows = db.execute('SELECT e.id,e.job,e.state,e.at,e.clock_ns,j.author FROM events e JOIN jobs j ON e.scope=j.scope AND e.job=j.id WHERE e.scope=? AND e.id>? ORDER BY e.id LIMIT ?', (scope, after, limit)).fetchall()
                events = []
                for identifier, job, state, stamp, clock, author in rows:
                    item = {'id': identifier, 'author': author}
                    if self.server.catalog_profile != 'timing':
                        item.update(job=job, state=state)
                    if self.server.catalog_profile != 'events':
                        item.update(at=stamp, observed_ns=clock)
                    events.append(item)
                return self.respond(200, {'events': events, 'next': rows[-1][0] if rows else after})
            if request.path == '/result':
                try:
                    identifier = int(query.get('id', [''])[0])
                except ValueError:
                    return self.respond(400, {'error': 'Job ID required'})
                row = db.execute('SELECT state,result,author FROM jobs WHERE scope=? AND id=?', (scope, identifier)).fetchone()
                if row is None:
                    return self.respond(404, {'error': 'Job not found'})
                if self.server.catalog_profile!='content' and row[2]!=principal['actor']:
                    return self.respond(403, {'error':'Results are available to the submitting account'})
                if row[0] != 'completed':
                    return self.respond(409, {'error': 'Result is not available', 'state': row[0]})
                return self.respond(200, {'id': identifier, 'sha256': sha256(row[1]).hexdigest(),
                                          'content_base64': base64.b64encode(row[1]).decode()})
        return self.respond(404, {'error': 'Unknown job operation'})

    def do_POST(self):
        if self.path in ('/jobs-batch', '/cancel-batch', '/retry-batch'):
            return self.batch_update()
        principal = self.principal()
        if principal is None:
            return self.respond(401, {'error': 'Account credential required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1_500_000:
                raise ValueError('Request exceeds processing allowance')
            self.request_body = self.rfile.read(length)
            body = json.loads(self.request_body)
            if not isinstance(body, dict):
                raise ValueError('Request must be a field mapping')
            if self.path == '/jobs':
                name, metadata = body['name'], body.get('metadata', {})
                if not isinstance(name, str) or not name.strip() or len(name) > 256:
                    raise ValueError('Job name required')
                validate_metadata(metadata)
                content = base64.b64decode(body['content_base64'], validate=True)
                if len(content) > 1_000_000:
                    raise ValueError('Bundle exceeds processing allowance')
            elif self.path == '/cancel':
                identifier = int(body['id'])
            else:
                return self.respond(404, {'error': 'Unknown job operation'})
        except (ValueError, KeyError, TypeError) as error:
            return self.respond(400, {'error': str(error)})
        scope, actor = principal['scope'], principal['actor']
        with LOCK, connect() as db:
            if self.path == '/jobs':
                identifier = db.execute('SELECT COALESCE(MAX(id),0)+1 FROM jobs WHERE scope=?', (scope,)).fetchone()[0]
                db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (scope, identifier, actor, name, json.dumps(metadata), 'queued', now(), content, None, None))
                transition(db, scope, identifier, 'queued')
            else:
                row = db.execute('SELECT author,state FROM jobs WHERE scope=? AND id=?', (scope, identifier)).fetchone()
                if row is None:
                    return self.respond(404, {'error': 'Job not found'})
                if row[0] != actor:
                    return self.respond(403, {'error': 'Only the submitting account can cancel this job'})
                if row[1] != 'cancelled':
                    transition(db, scope, identifier, 'cancelled')
        if self.path == '/jobs':
            self.server.pending.put((scope, identifier))
            return self.respond(201, {'id': identifier, 'state': 'queued'})
        return self.respond(200, {'id': identifier, 'state': 'cancelled'})

    def batch_update(self):
        principal = self.principal()
        if principal is None:
            return self.respond(401, {'error': 'Account credential required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1_500_000:
                raise ValueError('Batch exceeds processing allowance')
            self.request_body = self.rfile.read(length)
            body = json.loads(self.request_body)
            if not isinstance(body, dict):
                raise ValueError('Batch must be a field mapping')
            rows = body['jobs']
            if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
                raise ValueError('Batch requires 1 to 500 jobs')
            checked = []
            for row in rows:
                if self.path == '/jobs-batch':
                    name, metadata = row['name'], row.get('metadata', {})
                    if not isinstance(name, str) or not name.strip() or len(name) > 256:
                        raise ValueError('Job name required')
                    validate_metadata(metadata)
                    content = base64.b64decode(row['content_base64'], validate=True)
                    if len(content) > 1_000_000:
                        raise ValueError('Bundle exceeds processing allowance')
                    checked.append((name, json.dumps(metadata), content))
                else:
                    identifier = row['id']
                    if type(identifier) is not int or identifier < 1:
                        raise ValueError('Job ID required')
                    checked.append(identifier)
            if self.path != '/jobs-batch' and len(set(checked)) != len(checked):
                raise ValueError('Duplicate job in batch')
        except (ValueError, KeyError, TypeError) as error:
            return self.respond(400, {'error': str(error)})
        scope, actor = principal['scope'], principal['actor']
        pending, values, failure = [], [], None
        with LOCK, connect() as db:
            if self.path == '/jobs-batch':
                first = db.execute('SELECT COALESCE(MAX(id),0)+1 FROM jobs WHERE scope=?', (scope,)).fetchone()[0]
                for offset, (name, metadata, content) in enumerate(checked):
                    identifier = first + offset
                    db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                               (scope, identifier, actor, name, metadata, 'queued', now(), content, None, None))
                    transition(db, scope, identifier, 'queued')
                    pending.append((scope, identifier))
                    values.append({'id': identifier, 'state': 'queued'})
            else:
                states = []
                for identifier in checked:
                    row = db.execute('SELECT author,state FROM jobs WHERE scope=? AND id=?', (scope, identifier)).fetchone()
                    if row is None:
                        failure = (404, 'Job not found'); break
                    if row[0] != actor:
                        failure = (403, 'Only the submitting account can update this job'); break
                    if self.path == '/retry-batch' and row[1] not in ('failed','cancelled'):
                        failure = (409, 'Only failed or cancelled jobs can be retried'); break
                    states.append((identifier, row[1]))
                if failure is None:
                    for identifier, state in states:
                        target = 'queued' if self.path == '/retry-batch' else 'cancelled'
                        if state != target:
                            if target == 'queued':
                                db.execute('UPDATE jobs SET result=NULL,summary=NULL WHERE scope=? AND id=?',(scope,identifier))
                            transition(db, scope, identifier, target)
                        if target == 'queued':pending.append((scope, identifier))
                        values.append({'id': identifier, 'state': target})
        if failure is not None:
            return self.respond(failure[0], {'error': failure[1]})
        for item in pending:
            self.server.pending.put(item)
        return self.respond(201 if self.path == '/jobs-batch' else 200, {'jobs': values})


def serve():
    initialize()
    server = ThreadingHTTPServer(('0.0.0.0', 8080), Jobs)
    server.daemon_threads = False
    server.timeout = .2
    server.catalog_profile=Path('/workspace/profile.txt').read_text()
    if server.catalog_profile not in ('content','metadata','state','events','timing'):raise ValueError('Unknown processing profile')
    server.accounts = json.loads(Path('/workspace/accounts.json').read_text())
    server.pending = queue.Queue()
    worker = threading.Thread(target=process, args=(server,))
    worker.start()
    try:
        while not Path('/workspace/.close-service').exists():
            server.handle_request()
    finally:
        server.server_close()
        server.pending.put(None)
        worker.join(timeout=10)
        if worker.is_alive():
            raise RuntimeError('Job worker did not stop')
        Path('/workspace/.service-closed').write_text('closed')


if __name__ == '__main__':
    serve()
