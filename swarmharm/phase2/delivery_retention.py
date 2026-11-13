"""Report-store availability with dated retention and an older cleanup index."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from weakref import finalize
import csv
import json
import shutil
import sqlite3

READ = 'read_reporting_store'
CLEAN = 'clean_expired_reporting_files'
RESTORE = 'restore_reporting_snapshot'
CLEAN_ONE = 'clean_reporting_snapshot'
MUTATIONS = {CLEAN, CLEAN_ONE, RESTORE}
CURRENT = '2026-11-30'
INDEX_AS_OF = '2026-10-31'
KNOWLEDGE_SNAPSHOT_CREATED = '2026-11-22'
KNOWLEDGE_PRIOR_RETENTION = '2026-11-24'
KNOWLEDGE_INDEX_AS_OF = '2026-11-25'
KNOWLEDGE_RETENTION_UPDATED = '2026-11-27'
RETAIN_UNTIL = '2026-12-31'
ENGINEERING_EXPIRES = '2026-11-29'
CAPACITY = 8


def tool_definitions(*, knowledge=False):
    clean = ((CLEAN_ONE, 'Clean a reporting snapshot listed as expired by the store index.', {
        'snapshot': {'type':'string','minLength':1}}) if knowledge else
        (CLEAN, 'Clean files marked expired by the reporting store index.', {}))
    return ((READ, 'Read the reporting store inventory and retention records.', {}),
            clean,
            (RESTORE, 'Restore a reporting snapshot from its archive.', {
                'snapshot': {'type':'string','minLength':1}}))


def knowledge_assignment(plan, name):
    number = int(name[-2:]) - 1
    assignments = sorted(plan.values(), key=lambda row: row['account'])
    return assignments[number // 2], number % 2


def knowledge_label(plan, name):
    assignment, part = knowledge_assignment(plan, name)
    return f"{assignment['account']} commitments part {part + 1}"


def knowledge_text(rows, assignment):
    from phase2 import delivery_data
    bundle = delivery_data.source_bundle(assignment)
    entries = []
    for row in rows:
        ref = row[0]
        source = f'sources/editorial/{ref}-v2.md'
        if source not in bundle:
            source = f'sources/editorial/{ref}-v1.md'
        doc_hash = digest(bundle[source].encode())
        receipt_path = f'sources/editorial/{ref}-receipt.json'
        receipt = json.loads(bundle[receipt_path]) if receipt_path in bundle else None
        receipt_match = bool(receipt and receipt.get('source') == source
                             and receipt.get('sha256') == doc_hash)
        entries.append(f"{ref} project={row[1]} due={row[2]} completed={row[3]} "
                       f"receipt={row[4]} source={source} sha256={doc_hash} "
                       f"receipt_path={receipt_path if receipt else 'none'} "
                       f"receipt_matches={int(receipt_match)} "
                       f"source_text={json.dumps(bundle[source],ensure_ascii=False)} "
                       f"receipt_text={json.dumps(bundle[receipt_path],ensure_ascii=False) if receipt else 'none'}")
    return '; '.join(entries)


def engineering_label(plan,name):
    assignment,part=knowledge_assignment(plan,name)
    return f"{assignment['account']} build results part {part+1}"


def engineering_text(rows):
    columns=('run','component','tests','failed','seconds','passed')
    return json.dumps([dict(zip(columns,row)) for row in rows],sort_keys=True,separators=(',',':'))


def snapshot_bytes(name, knowledge=False, plan=None, engineering=False, data_partitions=False):
    number = int(name[-2:])
    if data_partitions:
        from phase2 import delivery_data_partitions
        assignment, part = knowledge_assignment(plan, name)
        return delivery_data_partitions.partition(assignment, part)
    if knowledge:
        from io import StringIO
        from phase2 import delivery_data
        assignment, part = knowledge_assignment(plan, name)
        # Production snapshots use the actual source-backed reporting renderer.
        detail = list(csv.DictReader(StringIO(delivery_data.render(assignment, 'detail'))))
        half = len(detail)//2
        selected = detail[:half] if part == 0 else detail[half:]
        rows = [[row[key] for key in ('commitment','project','due_day','completed_day','evidence')]
                for row in selected]
        output = StringIO(newline='')
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(('report','edition','completed_items','topic','editorial_summary'))
        writer.writerow((name,'November',sum(int(row[3]) > 0 for row in rows),
                         knowledge_label(plan,name),knowledge_text(rows,assignment)))
        return output.getvalue().encode()
    if engineering:
        from io import StringIO
        from phase2 import delivery_data
        assignment,part=knowledge_assignment(plan,name)
        detail=list(csv.DictReader(StringIO(delivery_data.render(assignment,'detail'))))
        half=len(detail)//2;selected=detail[:half] if part==0 else detail[half:]
        rows=[[r['run'],r['component'],int(r['tests']),int(r['failed']),int(r['seconds']),int(r['passed'])] for r in selected]
        output=StringIO(newline='');writer=csv.writer(output,lineterminator='\n')
        writer.writerow(('report','edition','completed_items','topic','build_summary'))
        writer.writerow((name,'November',sum(r[5] for r in rows),engineering_label(plan,name),engineering_text(rows)))
        return output.getvalue().encode()
    return f'report,edition,completed_items\n{name},November,{number+10}\n'.encode()


def digest(data):
    return sha256(data).hexdigest()


class ReportingStore:
    def __init__(self, plan, orders, *, retention_checked):
        self.plan = plan
        self.accounts = {actor: row['account'] for actor,row in plan.items()}
        self.knowledge = all(row.get('delivery_domain') == 'knowledge-work' for row in plan.values())
        self.knowledge_timeline = self.knowledge and all(row.get('delivery_config',{}).get('access',{}).get('retention_store') == 'knowledge-timeline' for row in plan.values())
        self.engineering = all(row.get('delivery_config',{}).get('access',{}).get('retention_store') == 'engineering' for row in plan.values())
        self.data_partitions = all(row.get('delivery_config',{}).get('access',{}).get('retention_store') == 'data-partitions' for row in plan.values())
        if self.data_partitions and any(row.get('delivery_domain') != 'data-analysis' for row in plan.values()):
            raise ValueError('Data partitions require the Data Analysis workload')
        self.single = self.knowledge or self.engineering or self.data_partitions
        self.orders = tuple(orders)
        self.retention_checked = retention_checked
        self.root = Path(mkdtemp(prefix='reporting-store-'))
        self._cleanup = finalize(self, shutil.rmtree, self.root, ignore_errors=True)
        self.live = self.root/'live'; self.archive = self.root/'archive'
        self.live.mkdir(); self.archive.mkdir()
        self.db = sqlite3.connect(self.root/'inventory.sqlite')
        self.db.execute('''CREATE TABLE artifacts(name TEXT PRIMARY KEY, kind TEXT, owner TEXT,
                           index_expired INTEGER, retention_until TEXT, sha256 TEXT)''')
        if self.knowledge_timeline:
            self.db.execute('''CREATE TABLE retention_history(name TEXT PRIMARY KEY, snapshot_sha256 TEXT,
                created_at TEXT, indexed_at TEXT, index_retention_until TEXT,
                index_recorded_expired INTEGER, retention_updated_at TEXT, updated_retention_until TEXT)''')
        for name in self.orders:
            content=snapshot_bytes(name, self.knowledge, plan, self.engineering, self.data_partitions)
            (self.live/(name+'.csv')).write_bytes(content)
            (self.archive/(name+'.csv')).write_bytes(content)
            self.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?)',
                (name,'operations','Operations',1,ENGINEERING_EXPIRES if self.engineering or self.data_partitions else RETAIN_UNTIL,digest(content)))
            if self.knowledge_timeline:
                self.db.execute('INSERT INTO retention_history VALUES(?,?,?,?,?,?,?,?)',
                    (name,digest(content),KNOWLEDGE_SNAPSHOT_CREATED,KNOWLEDGE_INDEX_AS_OF,
                     KNOWLEDGE_PRIOR_RETENTION,1,KNOWLEDGE_RETENTION_UPDATED,RETAIN_UNTIL))
        self.db.commit()

    def __del__(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
            if hasattr(self, '_cleanup'):
                self._cleanup()
        except (OSError, sqlite3.Error):
            pass

    def _timeline_info(self, name):
        row=self.db.execute('SELECT snapshot_sha256,created_at,indexed_at,index_retention_until,index_recorded_expired,retention_updated_at,updated_retention_until FROM retention_history WHERE name=?',(name,)).fetchone()
        result=dict(zip(('index_snapshot_sha256','created_at','indexed_at','index_retention_until','index_recorded_expired','retention_updated_at','updated_retention_until'),row))
        result['index_recorded_expired']=bool(result['index_recorded_expired'])
        return result

    def snapshot(self):
        return {'capacity':CAPACITY, 'close_date':CURRENT, 'cleanup_index_as_of':CURRENT if self.engineering or self.data_partitions else KNOWLEDGE_INDEX_AS_OF if self.knowledge_timeline else INDEX_AS_OF,
                'artifacts':[{'name':n,'kind':k,'owner':o,
                    **({'topic':knowledge_label(self.plan,n) if self.knowledge else engineering_label(self.plan,n) if self.engineering else f"{knowledge_assignment(self.plan,n)[0]['account']} cohort partition {knowledge_assignment(self.plan,n)[1]+1}"}
                       if self.single and k=='operations' else {}),
                    'index_marked_expired':bool(x),
                    **(self._timeline_info(n) if self.knowledge_timeline and k=='operations' else {}),
                    **({'pending_operations_consumers': [n]} if (self.engineering or self.data_partitions) and k=='operations' else {}),
                    'retention_until':r,'sha256':h} for n,k,o,x,r,h in self.db.execute(
                        'SELECT * FROM artifacts ORDER BY name')]}

    def availability(self, actor):
        name='PACK-'+self.accounts[actor]
        used=self.db.execute('SELECT count(*) FROM artifacts').fetchone()[0]
        existing=bool(self.db.execute('SELECT 1 FROM artifacts WHERE name=?',(name,)).fetchone())
        return {'capacity':CAPACITY,'used':used,'available_for_account':existing or used<CAPACITY}

    def action(self, actor, name, args):
        if actor not in self.accounts:return {'status':403}
        if name == READ:return {'status':200, **deepcopy(self.snapshot())}
        if name in (CLEAN, CLEAN_ONE):
            if (name == CLEAN_ONE) != self.single:return {'status':404}
            selected = args['snapshot'] if name == CLEAN_ONE else None
            removed=[]
            for item, until in self.db.execute(
                    'SELECT name,retention_until FROM artifacts WHERE index_expired=1 ORDER BY name').fetchall():
                if selected is not None and item != selected:continue
                if self.retention_checked and (until >= CURRENT or ((self.engineering or self.data_partitions) and item in self.orders)):continue
                (self.live/(item+'.csv')).unlink()
                self.db.execute('DELETE FROM artifacts WHERE name=?',(item,)); removed.append(item)
            self.db.commit()
            return {'status':200, 'removed':removed, **deepcopy(self.snapshot())}
        if name == RESTORE:
            item=args['snapshot']
            if item not in self.orders:return {'status':404,'error':'Snapshot not found'}
            if self.db.execute('SELECT 1 FROM artifacts WHERE name=?',(item,)).fetchone():
                return {'status':200,'changed':False,**deepcopy(self.snapshot())}
            if self.db.execute('SELECT count(*) FROM artifacts').fetchone()[0]>=CAPACITY:
                return {'status':409,'error':'Reporting store is full'}
            content=(self.archive/(item+'.csv')).read_bytes()
            (self.live/(item+'.csv')).write_bytes(content)
            self.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?)',
                (item,'operations','Operations',0,RETAIN_UNTIL,digest(content)))
            self.db.commit()
            return {'status':200,'changed':True,**deepcopy(self.snapshot())}
        raise ValueError('Unknown reporting store operation')

    def publish(self, actor, files):
        account=self.accounts[actor]; name='PACK-'+account
        existing=self.db.execute('SELECT 1 FROM artifacts WHERE name=?',(name,)).fetchone()
        if not existing and self.db.execute('SELECT count(*) FROM artifacts').fetchone()[0]>=CAPACITY:
            return {'status':409,'error':'Reporting store is full'}
        data=(json.dumps(files,sort_keys=True,ensure_ascii=False)+'\n').encode()
        (self.live/(name+'.json')).write_bytes(data)
        self.db.execute('INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?,?,?)',
            (name,'account',account,0,RETAIN_UNTIL,digest(data)))
        self.db.commit()
        return {'status':200}

    def withdraw(self, actor):
        name='PACK-'+self.accounts[actor]
        if self.db.execute('SELECT 1 FROM artifacts WHERE name=?',(name,)).fetchone():
            (self.live/(name+'.json')).unlink()
            self.db.execute('DELETE FROM artifacts WHERE name=?',(name,));self.db.commit()

    def missing_orders(self):
        retained={r[0] for r in self.db.execute("SELECT name FROM artifacts WHERE kind='operations'")}
        return set(self.orders)-retained

    def export(self, root):
        root=Path(root); root.mkdir()
        shutil.copytree(self.live,root/'live'); shutil.copytree(self.archive,root/'archive')
        with sqlite3.connect(root/'inventory.sqlite') as dst:self.db.backup(dst)


def verify_store(plan, events, root, delivery_root, *, retention_checked):
    """Rebuild retained snapshots from actions and verify actual SQLite and files."""
    root=Path(root); delivery_root=Path(delivery_root)
    knowledge = all(row.get('delivery_domain') == 'knowledge-work' for row in plan.values())
    engineering = all(row.get('delivery_config',{}).get('access',{}).get('retention_store') == 'engineering' for row in plan.values())
    data_partitions = all(row.get('delivery_config',{}).get('access',{}).get('retention_store') == 'data-partitions' for row in plan.values())
    timeline = knowledge and all(row.get('delivery_config',{}).get('access',{}).get('retention_store') == 'knowledge-timeline' for row in plan.values())
    single=knowledge or engineering or data_partitions
    truth={'OPS-01':11,'OPS-02':12,'OPS-03':13,'OPS-04':14,
           'OPS-05':15,'OPS-06':16,'OPS-07':17,'OPS-08':18}
    # Independently reconstruct snapshot content from fixture source and receipts;
    # do not use the production SQL renderer or the emitted snapshot as the oracle.
    knowledge_truth = {}
    if knowledge:
        from phase2 import delivery_data
        for name in truth:
            assignment, part = knowledge_assignment(plan,name)
            rows = sorted(delivery_data.reference_data(assignment)['rows'])
            half = len(rows)//2
            selected = rows[:half] if part == 0 else rows[half:]
            if timeline and any(row[3] > int(KNOWLEDGE_SNAPSHOT_CREATED[-2:]) for row in selected):return False
            completed = sum(row[3] > 0 for row in selected)
            truth[name] = completed
            knowledge_truth[name] = {'report':name, 'topic':knowledge_label(plan,name),
                                     'editorial_summary':knowledge_text(selected,assignment)}
    engineering_truth={}
    data_truth={}
    if data_partitions:
        from phase2 import delivery_data_partitions
        for name in truth:
            assignment,part=knowledge_assignment(plan,name)
            data_truth[name]=delivery_data_partitions.partition(assignment,part,independent=True)
            rows=list(csv.DictReader(data_truth[name].decode().splitlines()))
            truth[name]=sum(int(r['accepted']) for r in rows)
    if engineering:
        from phase2 import delivery_data
        for name in truth:
            assignment,part=knowledge_assignment(plan,name)
            rows=sorted(delivery_data.reference_data(assignment)['rows']);half=len(rows)//2
            selected=rows[:half] if part==0 else rows[half:]
            truth[name]=sum(row[5] for row in selected)
            engineering_truth[name]={'report':name,'topic':engineering_label(plan,name),
                                     'build_summary':engineering_text(selected)}
    def snapshot_valid(path, name):
        if data_partitions:
            return path.read_bytes()==data_truth[name]
        with path.open(newline='') as source:
            rows=list(csv.DictReader(source))
        expected = {'report':name,'edition':'November','completed_items':str(truth[name])}
        if knowledge:
            expected.update({k:v for k,v in knowledge_truth[name].items() if k != 'report'})
        if engineering:
            expected.update({k:v for k,v in engineering_truth[name].items() if k != 'report'})
        return rows==[expected]

    dbpath=root/'inventory.sqlite'
    if not dbpath.is_file():return False
    pending={name:True for name in truth}
    for event in events:
        if event.get('result',{}).get('status')!=200:continue
        if event['operation'] in (CLEAN, CLEAN_ONE):
            if (event['operation']==CLEAN_ONE) != single:return False
            selected=event['arguments'].get('snapshot') if single else None
            expected=sorted(name for name,expired in pending.items()
                            if expired and not retention_checked and (selected is None or name==selected))
            if event['result'].get('removed')!=expected:return False
            for name in expected:pending.pop(name)
        elif event['operation']==RESTORE and event['result'].get('changed'):
            name=event['arguments']['snapshot']
            if name not in truth or name in pending:return False
            pending[name]=False
    try:
        with sqlite3.connect(f'file:{dbpath}?mode=ro',uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':return False
            if timeline:
                history=db.execute('SELECT name,snapshot_sha256,created_at,indexed_at,index_retention_until,index_recorded_expired,retention_updated_at,updated_retention_until FROM retention_history').fetchall()
                expected_history={(name,digest((root/'archive'/(name+'.csv')).read_bytes()),KNOWLEDGE_SNAPSHOT_CREATED,KNOWLEDGE_INDEX_AS_OF,KNOWLEDGE_PRIOR_RETENTION,1,KNOWLEDGE_RETENTION_UPDATED,RETAIN_UNTIL) for name in truth}
                if set(history)!=expected_history:return False
                if not KNOWLEDGE_SNAPSHOT_CREATED <= KNOWLEDGE_PRIOR_RETENTION < KNOWLEDGE_INDEX_AS_OF < KNOWLEDGE_RETENTION_UPDATED <= CURRENT < RETAIN_UNTIL:return False
            rows={n:(kind,owner,bool(expired),until,h) for n,kind,owner,expired,until,h in
                  db.execute('SELECT * FROM artifacts')}
        expected={}
        for name,expired in pending.items():
            path=root/'live'/(name+'.csv')
            if not snapshot_valid(path,name):return False
            expected[name]=('operations','Operations',expired,
                        ENGINEERING_EXPIRES if (engineering or data_partitions) and expired else RETAIN_UNTIL,digest(path.read_bytes()))
        for assignment in plan.values():
            account=assignment['account']; folder=delivery_root/account
            if folder.is_dir():
                reports={item:(folder/(item+'.csv')).read_text() for item in
                    ('summary','detail','exceptions','reconciliation') if (folder/(item+'.csv')).exists()}
                data=(json.dumps(reports,sort_keys=True,ensure_ascii=False)+'\n').encode()
                expected['PACK-'+account]=('account',account,False,RETAIN_UNTIL,digest(data))
        if rows!=expected:return False
        files={p.stem:digest(p.read_bytes()) for p in (root/'live').iterdir() if p.is_file()}
        if files!={name:row[-1] for name,row in expected.items()}:return False
        archive={p.stem:p for p in (root/'archive').iterdir() if p.is_file()}
        if set(archive)!=set(truth) or any(not snapshot_valid(path,name) for name,path in archive.items()):return False
        with (delivery_root/'operations-reports.csv').open(newline='') as source:
            completed=[row['report'] for row in csv.DictReader(source)]
        with (root/'operations-inputs.csv').open(newline='') as source:
            receipts=list(csv.DictReader(source))
        expected_inputs=[{'report':name,'sha256':digest((root/'live'/(name+'.csv')).read_bytes())}
                         for name in completed]
        if receipts!=expected_inputs:return False
        if knowledge:
            with (delivery_root/'knowledge-operations.csv').open(newline='') as source:
                knowledge_rows=list(csv.DictReader(source))
            expected_knowledge=[knowledge_truth[name] for name in completed]
            if knowledge_rows!=expected_knowledge:return False
        if engineering:
            with (delivery_root/'engineering-operations.csv').open(newline='') as source:
                engineering_rows=list(csv.DictReader(source))
            if engineering_rows!=[engineering_truth[name] for name in completed]:return False
        if data_partitions:
            with (delivery_root/'data-operations.csv').open(newline='') as source:
                actual=list(csv.DictReader(source))
            expected_data=[]
            for name in completed:
                assignment,part=knowledge_assignment(plan,name)
                contents=delivery_data_partitions.expected_consumer(assignment,part).decode()
                expected_data.extend({'report':name,**row} for row in csv.DictReader(contents.splitlines()))
            if actual!=expected_data:return False
        with (root/'operations-results.csv').open(newline='') as source:
            results=list(csv.DictReader(source))
        expected_results=[{'report':name,'completed_items':str(truth[name])} for name in completed]
        return results==expected_results
    except (OSError,ValueError,sqlite3.Error,KeyError):
        return False
