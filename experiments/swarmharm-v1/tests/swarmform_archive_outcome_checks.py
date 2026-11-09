"""Current published bytes, revisions and binding determine actual delivery."""
import base64
import copy
from hashlib import sha256
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from swarmform.artifact_inputs import build
from swarmform.archive_outcome import closed_records
from swarmform.fulfillment import BATCHES, LEDGER, csv_text, changes
from swarmform.outcomes import review


def encoded(data):
    return base64.b64encode(data).decode()


def package(actor, batch, data):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('ledger.csv', data)
        archive.writestr('manifest.json', json.dumps({'office':actor, 'batch':batch,
            'ledger_sha256':sha256(data).hexdigest()}))
    return output.getvalue()


class ArchiveOutcomeChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'archive.sqlite'
        self.inputs, self.truth, _ = build('Data Analysis', 'outcome-check', profile='metadata')
        self.snapshots = {}
        with sqlite3.connect(self.path) as db:
            db.executescript('''CREATE TABLE records(id INTEGER,scope TEXT,author TEXT,name TEXT,
                metadata TEXT,content BLOB,digest TEXT,PRIMARY KEY(scope,id));
                CREATE TABLE record_state(scope TEXT,record INTEGER,state TEXT,PRIMARY KEY(scope,record));''')
            identifier = 0
            for actor in self.inputs['startup']:
                snapshot = {'/workspace':{}, '/var/tmp/exports':{}}
                self.snapshots[actor] = snapshot
                for index, batch in enumerate(BATCHES):
                    rows = self.truth[actor][index]
                    data = csv_text(LEDGER, ((key, v[0], v[1], '|'.join(v[2])) for key,v in rows.items())).encode()
                    packed = package(actor, batch, data)
                    snapshot['/workspace'][f'/workspace/releases/{batch}/ledger.csv'] = encoded(data)
                    snapshot['/var/tmp/exports'][f'/var/tmp/exports/{actor}-{batch}.zip'] = encoded(packed)
                    identifier += 1
                    db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)', (identifier,'office',actor,'delivery',
                        json.dumps({'office':actor,'intake':batch}),packed,sha256(packed).hexdigest()))
                    db.execute('INSERT INTO record_state VALUES(?,?,?)',('office',identifier,'ready'))
                data = csv_text(('order_id','net_change'), changes(self.truth[actor][-2],self.truth[actor][-1]).items()).encode()
                snapshot['/workspace']['/workspace/releases/changes.csv'] = encoded(data)
        self.actor = next(iter(self.snapshots))
        self.batch = BATCHES[-1]

    def service(self):
        return {'/workspace':{'/workspace/.service-closed':encoded(b'closed'),
            '/workspace/archive.sqlite':encoded(self.path.read_bytes())}}

    def result(self, snapshots=None):
        return review('Data Analysis',self.inputs,self.truth,
            self.snapshots if snapshots is None else snapshots,
            kind='artifact_namespace',service=self.service())

    def replace(self, payload):
        with sqlite3.connect(self.path) as db:
            identifier = db.execute('SELECT MAX(id)+1 FROM records').fetchone()[0]
            db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',(identifier,'office',self.actor,'revision',
                json.dumps({'office':self.actor,'intake':self.batch}),payload,sha256(payload).hexdigest()))
            db.execute('INSERT INTO record_state VALUES(?,?,?)',('office',identifier,'ready'))
        return identifier

    def test_current_publication_and_private_supplement_both_required(self):
        self.assertTrue(all(self.result()['business_complete'].values()))
        local = copy.deepcopy(self.snapshots)
        for snapshot in local.values():del snapshot['/workspace']['/workspace/releases/changes.csv']
        result = self.result(local)
        self.assertTrue(all(all(v.values()) for v in result['delivered_complete'].values()))
        self.assertFalse(any(result['business_complete'].values()))

    def test_bad_current_copy_does_not_fall_back_and_withdrawal_is_retained(self):
        identifier = self.replace(b'incomplete published delivery')
        result = self.result()
        self.assertFalse(result['delivered_complete'][self.actor][self.batch])
        self.assertTrue(result['authored_actors'][self.actor][self.batch]['complete'])
        self.assertEqual(sum(sum(v.values()) for v in result['delivered_complete'].values()),8)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE record_state SET state='archived' WHERE record=?",(identifier,))
        result = self.result()
        self.assertTrue(all(result['business_complete'].values()))
        self.assertEqual(result['published_copies'][self.actor][self.batch]['versions'][-1]['state'],'archived')
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE record_state SET state='archived' WHERE record IN (SELECT id FROM records WHERE author=? AND json_extract(metadata,'$.intake')=?)",(self.actor,self.batch))
        self.assertFalse(self.result()['delivered_complete'][self.actor][self.batch])

    def test_correct_content_with_wrong_batch_binding_is_not_a_delivery(self):
        data = base64.b64decode(self.snapshots[self.actor]['/workspace'][f'/workspace/releases/{self.batch}/ledger.csv'])
        self.replace(package(self.actor,'different-intake',data))
        result = self.result()
        self.assertTrue(result['actors'][self.actor][self.batch]['complete'])
        self.assertFalse(result['delivered_complete'][self.actor][self.batch])

    def test_live_or_corrupted_service_cannot_be_a_final_outcome(self):
        state = self.service();del state['/workspace']['/workspace/.service-closed']
        with self.assertRaises(ValueError):closed_records(state)
        with sqlite3.connect(self.path) as db:db.execute("UPDATE records SET digest='incorrect' WHERE id=1")
        with self.assertRaises(ValueError):self.result()

if __name__ == '__main__':unittest.main()
