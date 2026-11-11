"""Local archive policy checks, with no inference calls."""
import argparse
import base64
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import urllib.error
import urllib.request

import importlib.util
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1] / 'swarmform'
def module(name):
    spec = importlib.util.spec_from_file_location(name, PACKAGE/(name+'.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded
base = module('base_archive')
with patch.dict(sys.modules, {'base_archive':base}):
    service = module('profile_archive')


def exercise(profile, shared):
    with tempfile.TemporaryDirectory() as directory:
        service.base.DB = str(Path(directory)/'archive.sqlite')
        service.initialize()
        server = ThreadingHTTPServer(('127.0.0.1', 0), service.Archive)
        server.catalog_profile = profile
        server.accounts = {a:{'actor':a,'scope':'office' if shared else a} for a in ('A','B','C')}
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()

        def request(actor, method, path, value=None):
            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
                data=json.dumps(value).encode() if value is not None else None,
                method=method, headers={'Authorization':'Bearer '+actor})
            try:
                with urllib.request.urlopen(req, timeout=3) as reply:
                    return reply.status, json.load(reply)
            except urllib.error.HTTPError as error:
                return error.code, json.load(error)

        try:
            ids = {}
            for actor in ('A','B','C'):
                code, result = request(actor, 'POST', '/records', {'name':actor+'-report',
                    'metadata':{'intake':'opening'}, 'content_base64':base64.b64encode((actor+' report\n').encode()).decode()})
                assert code == 201
                ids[actor] = result['id']
            if not shared:
                assert set(ids.values()) == {1}
            for actor in ('A','B','C'):
                for state in ('draft','ready','archived'):
                    code, result = request(actor,'POST','/record-state',{'id':ids[actor],'state':state})
                    assert code == 200
                    rows = request(actor,'GET','/records')[1]['records']
                    assert next(r for r in rows if r['id']==ids[actor])['state'] == state
                for receiver in ('A','B','C'):
                    rows = request(receiver,'GET','/records')[1]['records']
                    assert len(rows) == (3 if shared else 1)
                    assert shared or all(r['author']==receiver for r in rows)
                    fields = {'id','author','state'}
                    if profile in ('content','metadata'): fields |= {'name','metadata'}
                    if profile == 'content': fields |= {'sha256','bytes'}
                    assert all(set(r)==fields for r in rows)
                    if shared and receiver!=actor:
                        code, result = request(receiver,'GET','/record?id='+str(ids[actor]))
                        assert code == (200 if profile=='content' else 403)
                        if code == 200: assert base64.b64decode(result['content_base64']) == (actor+' report\n').encode()
                        assert request(receiver,'POST','/record-state',{'id':ids[actor],'state':'draft'})[0] == 403
            records=[json.loads(p.read_text()) for p in Path(service.base.DB+'.deliveries').glob('*.json')]
            assert all(sha256(base64.b64decode(r['body_base64'])).hexdigest()==r['sha256'] for r in records)
            return {'profile':profile,'shared':shared,'state_transitions_visible':True,
                    'scope_and_fields_checked':True,'protected_responses':len(records)}
        finally:
            server.shutdown(); server.server_close(); thread.join()


class ArchivePolicyChecks(unittest.TestCase):
    def test_catalog_fields_and_owner_state_respect_scope(self):
        for profile in ('content','metadata','state'):
            for shared in (True,False):
                with self.subTest(profile=profile,shared=shared):
                    exercise(profile,shared)

if __name__=='__main__':unittest.main()
