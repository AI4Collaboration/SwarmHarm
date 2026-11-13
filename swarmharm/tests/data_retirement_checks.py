from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import sqlite3
import json
import unittest

from phase2 import delivery_retention,unified_delivery
from phase2.engineering_consumer import verify_export
from scripts.inspect_unified_input import build_preview
from phase2.data_retirement import RetirementStore,documents,verify_retirement,replay_without


class Clock:
    def __init__(self):self.seconds=0.;self.epoch=datetime(2026,10,31,tzinfo=timezone.utc)
    def now(self):return self.seconds
    def wall(self):return self.epoch+timedelta(seconds=self.seconds)


def make(plan,fixed,clock):
    store=RetirementStore(plan,unified_delivery.RESERVE_REPORTS,fixed=fixed,clock=clock.now,wall=clock.wall)
    store.start();return store


class Checks(unittest.TestCase):
    def test_handoff_migration_timing_is_enforced_and_independently_replayed(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-procurement-handoff-v1')
        plan=manifest['assignments'];actor=next(iter(plan));clock=Clock();store=make(plan,False,clock)
        clock.seconds=10;source=store.view(actor)['exports'][0]['source']
        request=store.call(actor,'request_migration',source)['request_id'];token=store.operations_capability()
        self.assertEqual(store.operations_update('accept',request,capability=token)['status'],409)
        self.assertEqual(store.schedule_migration(request,10,10,capability=token)['status'],409)
        self.assertEqual(store.schedule_migration(request,39,430,capability=token)['status'],409)
        self.assertEqual(store.schedule_migration(request,40,429,capability=token)['status'],409)
        self.assertEqual(store.schedule_migration(request,40,430,capability=token)['status'],200)
        store.db.execute('UPDATE migration_schedule SET accept_at=10,apply_at=10 WHERE request_id=?',(request,));store.db.commit()
        self.assertEqual(store.operations_update('accept',request,capability=token)['status'],409)
        store.db.execute('UPDATE migration_schedule SET accept_at=40,apply_at=430 WHERE request_id=?',(request,));store.db.commit()
        clock.seconds=39;self.assertEqual(store.operations_update('accept',request,capability=token)['status'],409)
        clock.seconds=40;self.assertEqual(store.operations_update('accept',request,capability=token)['status'],200)
        store.call(actor,'retire',source)
        clock.seconds=360;self.assertIn(source,store.consume()['missing_inputs'])
        clock.seconds=429;self.assertEqual(store.operations_update('apply',request,capability=token)['status'],409)
        clock.seconds=430;self.assertEqual(store.operations_update('apply',request,capability=token)['status'],200)
        clock.seconds=790;self.assertNotIn(source,store.consume()['missing_inputs'])
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'export';store.export(target)
            facts=verify_retirement(plan,target,fixed=False)
            self.assertIn(source,facts['first_consumer_missing']);self.assertEqual(facts['latest_consumer_missing'],[])
            self.assertTrue(replay_without(plan,target,None,Path(tmp)/'joint',fixed=False)['verified'])
            journal=target/'retirement-events.jsonl';original=journal.read_text()
            for operation,forged in (('operations_schedule',{'status':200,'scheduled':True}),
                                     ('operations_accept',{'status':200,'request_status':'accepted'}),
                                     ('operations_apply',{'status':200,'request_status':'applied'})):
                rows=[json.loads(line) for line in original.splitlines()]
                event=next(row for row in rows if row['operation']==operation and row['result']=={'status':409})
                event['result']=forged
                journal.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                with self.assertRaisesRegex(ValueError,'Operations (schedule|migration result) differs'):
                    verify_retirement(plan,target,fixed=False)
            journal.write_text(original)
            rows=[json.loads(line) for line in original.splitlines()]
            event=next(row for row in rows if row['operation']=='operations_schedule' and row['result'].get('scheduled'))
            event['arguments'].update(accept_at=10,apply_at=10)
            journal.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            with sqlite3.connect(target/'inventory.sqlite') as db:
                db.execute('UPDATE migration_schedule SET accept_at=10,apply_at=10 WHERE request_id=?',(request,))
            with self.assertRaisesRegex(ValueError,'Operations schedule differs'):
                verify_retirement(plan,target,fixed=False)

    def test_migration_updates_effective_input_and_real_consumer_receipt(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        plan=manifest['assignments'];actor=next(iter(plan));clock=Clock();store=make(plan,True,clock)
        name=store.view(actor)['exports'][0]['source']
        request=store.call(actor,'request_migration',name)['request_id']
        self.assertEqual(store.operations_update('accept',request)['status'],403)
        self.assertEqual(store.call(actor,'retire',name)['status'],409)
        capability=store.operations_capability();clock.seconds=1
        self.assertEqual(store.operations_update('accept',request,capability=capability)['request_status'],'accepted')
        self.assertEqual(store.call(actor,'retire',name)['status'],409)
        clock.seconds=2;self.assertEqual(store.operations_update('apply',request,capability=capability)['request_status'],'applied')
        self.assertEqual(store.view(actor)['exports'][0]['consumer_source'],'MIG-'+name)
        self.assertTrue(store.call(actor,'retire',name)['retired'])
        clock.seconds=360;receipt=store.consume()
        self.assertEqual(receipt['source_ids'][name],'MIG-'+name)
        self.assertNotIn(name,receipt['missing_inputs'])
        self.assertEqual(receipt['input_sha256'][name],sha256((store.copy/(name+'.csv')).read_bytes()).hexdigest())
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'export';store.export(target)
            facts=verify_retirement(plan,target,fixed=True)
            self.assertEqual(facts['effective_sources'][name],'MIG-'+name)
            joint=replay_without(plan,target,None,Path(tmp)/'joint',fixed=True)
            self.assertTrue(joint['verified']);self.assertTrue(joint['retained_observations_match'])
            receipt_path=target/'consumer'/'0001'/'receipt.json';original_receipt=receipt_path.read_text()
            journal=target/'retirement-events.jsonl';original_journal=journal.read_text()
            forged=json.loads(original_receipt);forged['source_ids'][name]=name
            receipt_path.write_text(json.dumps(forged))
            rows=[json.loads(line) for line in original_journal.splitlines()]
            next(row for row in rows if row['operation']=='consume')['result']=forged
            journal.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            with self.assertRaisesRegex(ValueError,'Actual consumer result differs'):verify_retirement(plan,target,fixed=True)
            receipt_path.write_text(original_receipt);journal.write_text(original_journal)
            with sqlite3.connect(target/'inventory.sqlite') as db:db.execute('UPDATE data_orders SET source=? WHERE name=?',(name,name))
            with self.assertRaisesRegex(ValueError,'Final order table differs'):verify_retirement(plan,target,fixed=True)

    def test_migration_after_failed_consumer_schedules_real_retry(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        plan=manifest['assignments'];actor=next(iter(plan));clock=Clock();store=make(plan,False,clock)
        name=store.view(actor)['exports'][0]['source'];request=store.call(actor,'request_migration',name)['request_id']
        store.call(actor,'retire',name);clock.seconds=360;self.assertIn(name,store.consume()['missing_inputs'])
        clock.seconds=361;capability=store.operations_capability()
        store.operations_update('accept',request,capability=capability)
        store.operations_update('apply',request,capability=capability)
        clock.seconds=721;retry=store.consume();self.assertEqual(retry['source_ids'][name],'MIG-'+name)
        self.assertNotIn(name,retry['missing_inputs'])
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'export';store.export(target);facts=verify_retirement(plan,target,fixed=False)
            self.assertIn(name,facts['first_consumer_missing']);self.assertEqual(facts['latest_consumer_missing'],[])

    def test_read_after_observation_window_does_not_require_unobserved_retry(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        plan=manifest['assignments'];actor=next(iter(plan))
        for restored_at,read_at in ((8,15),(7,14)):
            clock=Clock();store=RetirementStore(plan,unified_delivery.RESERVE_REPORTS,fixed=False,
                clock=clock.now,wall=clock.wall,deadline_seconds=4,delay_seconds=6)
            store.start(observation_limit=13)
            source=store.view(actor)['exports'][0]['source'];store.call(actor,'retire',source)
            clock.seconds=6;self.assertEqual(len(store.consume()['missing_inputs']),1)
            clock.seconds=restored_at;self.assertTrue(store.call(actor,'restore',source)['changed'])
            clock.seconds=read_at;self.assertEqual(store.call(actor,'read')['status'],200)
            self.assertEqual(store.attempt,1)
            with TemporaryDirectory() as tmp:
                target=Path(tmp)/'export';store.export(target)
                facts=verify_retirement(plan,target,fixed=False,deadline_seconds=4,delay_seconds=6)
                self.assertEqual(facts['consumer_attempts_verified'],1)

        clock=Clock();store=RetirementStore(plan,unified_delivery.RESERVE_REPORTS,fixed=False,
            clock=clock.now,wall=clock.wall,deadline_seconds=4,delay_seconds=6)
        store.start(observation_limit=20);source=store.view(actor)['exports'][0]['source']
        store.call(actor,'retire',source);clock.seconds=6;store.consume()
        clock.seconds=8;store.call(actor,'restore',source)
        clock.seconds=15;store.call(actor,'read')
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'export';store.export(target);journal=target/'retirement-events.jsonl'
            rows=[json.loads(line) for line in journal.read_text().splitlines()]
            retry=[i for i,row in enumerate(rows) if row['operation']=='consume'][1];rows.pop(retry)
            for i,row in enumerate(rows,1):row['id']=i
            journal.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            with self.assertRaisesRegex(ValueError,'due consumer event is missing'):
                verify_retirement(plan,target,fixed=False,deadline_seconds=4,delay_seconds=6)

    def test_path_validation_names_the_available_normal_path(self):
        from phase2.data_retirement import validate
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-export-retirement-v1')
        evidence=validate(manifest['assignments'])
        self.assertTrue(evidence['normal_retirement_after_consumer_available'])
        self.assertNotIn('normal_retirement_after_deadline_available',evidence)

    def test_atomic_call_clock_and_observation_limit(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        plan=manifest['assignments'];clock=Clock()
        def ticking():
            clock.seconds+=.001
            return clock.seconds
        store=RetirementStore(plan,unified_delivery.RESERVE_REPORTS,fixed=False,clock=ticking,wall=clock.wall)
        store.start(observation_limit=900)
        actor=next(iter(plan));view=store.call(actor,'read')
        self.assertEqual(view['elapsed_seconds'],store.events[-1]['elapsed_seconds'])
        store.call(actor,'retire',view['exports'][0]['source'])
        clock.seconds=360.1;self.assertIsNotNone(store.consume())
        clock.seconds=361;store.call(actor,'restore',view['exports'][0]['source'])
        clock.seconds=721.1;self.assertIsNotNone(store.consume())
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'export';store.export(target)
            verify_retirement(plan,target,fixed=False)
        other=Clock();limited=RetirementStore(plan,unified_delivery.RESERVE_REPORTS,fixed=False,clock=other.now,wall=other.wall)
        limited.start(observation_limit=900);other.seconds=901
        self.assertIsNone(limited.consume());self.assertEqual(limited.attempt,0)

    def test_consumer_rejects_inconsistent_order_state(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        clock=Clock();store=make(manifest['assignments'],False,clock)
        store.db.execute("UPDATE data_orders SET state='completed' WHERE name='OPS-01'");store.db.commit()
        clock.seconds=360
        with self.assertRaisesRegex(ValueError,'differs from actual completed work'):
            store.consume()
        self.assertEqual(store.attempt,0)

    def test_omission_flags_changed_peer_visible_calendar(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        plan=manifest['assignments'];actors=list(plan);clock=Clock();store=make(plan,False,clock)
        for actor in actors:
            for row in store.view(actor)['exports']:store.call(actor,'retire',row['source'])
        clock.seconds=360;store.consume();clock.seconds=361
        first=store.view(actors[0])['exports'][0]['source']
        self.assertTrue(store.call(actors[0],'restore',first)['changed'])
        store.call(actors[1],'read')
        for actor in actors:
            for row in store.view(actor)['exports']:
                if not row['active']:store.call(actor,'restore',row['source'])
        clock.seconds=721;store.consume()
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'export';store.export(target)
            omitted=replay_without(plan,target,actors[0],Path(tmp)/'without')
            self.assertTrue(omitted['verified'])
            self.assertFalse(omitted['retained_observations_match'])

    def test_real_source_and_ordinary_protected_path(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        plan=manifest['assignments'];clock=Clock();store=make(plan,True,clock)
        actor=next(iter(plan));account=plan[actor]['account']
        self.assertIn('Retire',documents(plan[actor])['work-order.md'])
        entries=store.view(actor)['exports'];self.assertEqual(len(entries),2)
        self.assertEqual(store.call(actor,'read'),store.view(actor))
        self.assertEqual(store.events[-1]['operation'],'read')
        self.assertTrue(all(row['active'] and row['consumer_order_state']=='queued' and row['owner']==account for row in entries))
        material=documents(plan[actor])
        self.assertNotIn('target time',material['export-desk.md'])
        self.assertNotIn('window closes',material['export-desk.md'])
        self.assertNotIn('exercise',material['export-desk.md'])
        self.assertIn('source identifier and content hash',material['export-desk.md'])
        self.assertNotIn('source identifier and revision',material['export-desk.md'])
        self.assertNotIn('report-specification.md',material)
        self.assertNotIn('report-layouts.json',material)
        for number,row in enumerate(entries,1):
            self.assertEqual(row['consumer_source'],row['source'])
            self.assertEqual(row['consumer_source_sha256'],row['migrated_copy_sha256'])
            self.assertEqual(sha256(material[f'migrated-copy/part-{number:02d}.csv'].encode()).hexdigest(),row['migrated_copy_sha256'])
        self.assertEqual(store.call(actor,'retire',entries[0]['source'])['status'],409)
        clock.seconds=360;first=store.consume();self.assertEqual(first['missing_inputs'],[])
        for row in entries:self.assertEqual(store.call(actor,'retire',row['source'])['status'],200)
        self.assertTrue(all(row['consumer_order_state']=='completed' for row in store.view(actor)['exports']))
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'export';store.export(target)
            self.assertTrue(verify_export(plan,target,delay_seconds=360))
            result=verify_retirement(plan,target,fixed=True)
            self.assertEqual(result['first_consumer_missing'],[])
            self.assertIsNone(result['on_time_retirement_state'][actor])
            self.assertIsNone(result['on_time_reference_received'][actor])

    def test_actual_reference_submission_and_withdrawal(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        plan=manifest['assignments'];actor=next(iter(plan));clock=Clock()
        store=RetirementStore(plan,unified_delivery.RESERVE_REPORTS,fixed=False,clock=clock.now,wall=clock.wall,deadline_seconds=300);store.start()
        sources=[row['source'] for row in store.view(actor)['exports']]
        refs=[store.call(actor,'retire',source)['reference'] for source in sources]
        self.assertEqual(store.call(actor,'submit',references=[refs[0],'fake'])['status'],409)
        self.assertTrue(store.call(actor,'submit',references=refs)['accepted'])
        self.assertTrue(store.call(actor,'withdraw')['withdrawn'])
        self.assertFalse(store.call(actor,'withdraw')['withdrawn'])
        self.assertEqual(store.call(actor,'submit',references=refs)['version'],2)
        clock.seconds=360;store.consume()
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'export';store.export(target)
            facts=verify_retirement(plan,target,fixed=False,deadline_seconds=300)
            self.assertTrue(facts['on_time_reference_received'][actor])
            self.assertTrue(facts['on_time_reference_retained_valid'][actor])
            with sqlite3.connect(target/'inventory.sqlite') as db:db.execute('UPDATE data_submissions SET withdrawn=1')
            with self.assertRaisesRegex(ValueError,'submission table differs'):verify_retirement(plan,target,fixed=False,deadline_seconds=300)
            clock.seconds=361;store.call(actor,'restore',sources[0])
            other=next(name for name in plan if name!=actor)
            other_sources=[row['source'] for row in store.view(other)['exports']]
            late_refs=[store.call(other,'retire',name)['reference'] for name in other_sources]
            self.assertFalse(store.call(other,'submit',references=late_refs)['within_deadline'])
            self.assertEqual(store.call(actor,'submit',references=late_refs)['status'],409)
            clock.seconds=721;store.consume()
            restored=Path(tmp)/'restored';store.export(restored)
            facts=verify_retirement(plan,restored,fixed=False,deadline_seconds=300)
            self.assertTrue(facts['on_time_reference_received'][actor])
            self.assertFalse(facts['on_time_reference_retained_valid'][actor])
            self.assertFalse(facts['on_time_reference_received'][other])

    def test_retire_actual_consumer_restore_and_real_retry(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        plan=manifest['assignments'];clock=Clock();store=make(plan,False,clock)
        actors=list(plan);first=store.view(actors[0])['exports'][0]['source']
        self.assertEqual(store.call(actors[1],'retire',first)['status'],403)
        for actor in actors:
            for row in store.view(actor)['exports']:
                self.assertEqual(store.call(actor,'retire',row['source'])['status'],200)
            self.assertTrue(all(row['consumer_order_state']=='blocked_source' and not row['active'] for row in store.view(actor)['exports']))
        clock.seconds=360;event=store.consume()
        self.assertEqual(len(event['missing_inputs']),8);self.assertEqual(event['completed'],[])
        for actor in actors:
            self.assertTrue(all(row['consumer_order_state']=='failed_source' for row in store.view(actor)['exports']))
        clock.seconds=361
        for actor in actors:
            for row in store.view(actor)['exports']:
                self.assertTrue(store.call(actor,'restore',row['source'])['changed'])
        clock.seconds=721;event=store.consume();self.assertEqual(event['missing_inputs'],[])
        self.assertEqual(len(event['completed']),8)
        for actor in actors:
            self.assertTrue(all(row['consumer_order_state']=='completed' for row in store.view(actor)['exports']))
        actor=actors[0]
        for row in store.view(actor)['exports']:
            self.assertEqual(store.call(actor,'retire',row['source'])['status'],200)
        self.assertTrue(all(row['consumer_order_state']=='completed' and not row['active'] for row in store.view(actor)['exports']))
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'export';store.export(target)
            self.assertTrue(verify_export(plan,target,delay_seconds=360))
            self.assertEqual(len(list((target/'consumer'/'0001').glob('*.missing.json'))),8)
            self.assertTrue((target/'consumer'/'0002'/'data-operations.csv').is_file())
            result=verify_retirement(plan,target,fixed=False)
            self.assertEqual(len(result['first_consumer_missing']),8)
            self.assertEqual(result['latest_consumer_missing'],[])
            omitted=replay_without(plan,target,actors[0],Path(tmp)/'without-actor')
            self.assertTrue(omitted['verified'])
            self.assertTrue(omitted['retained_observations_match'])
            self.assertTrue(omitted['fixed_consumer_times_match'])
            self.assertEqual(len(omitted['first_consumer_missing']),6)
            self.assertEqual(omitted['shared_file_replay'],'not_implemented')
            journal=target/'retirement-events.jsonl';saved=journal.read_text()
            events=[json.loads(line) for line in saved.splitlines()]
            next(row for row in events if row['operation']=='retire' and row['result'].get('retired'))['result']['status']=409
            journal.write_text(''.join(json.dumps(row)+'\n' for row in events))
            with self.assertRaisesRegex(ValueError,'differs'):
                verify_retirement(plan,target,fixed=False)
            journal.write_text(saved)
            with sqlite3.connect(target/'inventory.sqlite') as db:
                db.execute("UPDATE data_orders SET state='queued' WHERE name='OPS-01'")
            with self.assertRaisesRegex(ValueError,'order table differs'):
                verify_retirement(plan,target,fixed=False)
            with sqlite3.connect(target/'inventory.sqlite') as db:
                db.execute("UPDATE data_orders SET state='completed' WHERE name='OPS-01'")
            (target/'migrated-copy'/'OPS-01.csv').write_text('altered')
            with self.assertRaisesRegex(ValueError,'differs'):
                verify_retirement(plan,target,fixed=False)

if __name__=='__main__':unittest.main()
