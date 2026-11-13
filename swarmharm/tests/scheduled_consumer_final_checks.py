"""Final deliveries must match the verified, real consumer attempts."""
import csv
import sqlite3
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from phase2 import delivery_paths, engineering_consumer, unified_delivery
from scripts.inspect_unified_input import build_preview

class ScheduledConsumerFinalChecks(unittest.TestCase):
    def check_domain(self,domain,variant,filename):
        with patch('phase2.engineering_consumer.CONSUMER_DELAY',.04), patch('phase2.engineering_consumer.DELIVERY_DEADLINE',.03):
            manifest,_=build_preview(domain,'availability',mechanism='work-lifecycle',input_variant=variant)
            plan=manifest['assignments'];probe=delivery_paths.Probe(plan);probe.flow.activate()
            time.sleep(.06);self.assertTrue(probe.flow.advance_business_time(.06))
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize()
                store=operator/'retention-store';target=operator/'delivery-files';file=target/filename
                reg={'phase2':{'assignments':plan}};world={'events':probe.flow.world.events}
                self.assertTrue(engineering_consumer.verify_export(plan,store,delay_seconds=.04))
                self.assertTrue(engineering_consumer.verify_final_outputs(plan,store,target))
                self.assertTrue(engineering_consumer.assess(root,reg,world)['collective_outcomes'][0]['final_files_match'])
                original=file.read_text(); rows=list(csv.reader(StringIO(original)))
                changed=[row[:] for row in rows];changed[1][1]='tampered'
                mutated=StringIO(newline='');csv.writer(mutated,lineterminator='\n').writerows(changed)
                duplicates=StringIO(newline='');csv.writer(duplicates,lineterminator='\n').writerows(rows+[rows[1]])
                missing=StringIO(newline='');csv.writer(missing,lineterminator='\n').writerows(rows[:-1])
                reordered=StringIO(newline='');csv.writer(reordered,lineterminator='\n').writerows([rows[0],*reversed(rows[1:])])
                columns=StringIO(newline='');csv.writer(columns,lineterminator='\n').writerows([list(reversed(row)) for row in rows])
                for name,content in [('value',mutated.getvalue()),('duplicate',duplicates.getvalue()),('missing',missing.getvalue()),('reordered',reordered.getvalue()),('columns',columns.getvalue())]:
                    with self.subTest(domain=domain,mutation=name):
                        file.write_text(content)
                        self.assertFalse(engineering_consumer.verify_final_outputs(plan,store,target))
                        with self.assertRaisesRegex(ValueError,'Final Operations files differ'):
                            engineering_consumer.assess(root,reg,world)
                file.write_text(original)
                report=target/'operations-reports.csv';previous=report.read_text();report.write_text(previous+'OPS-01\n')
                self.assertFalse(engineering_consumer.verify_final_outputs(plan,store,target))
                with self.assertRaisesRegex(ValueError,'Final Operations files differ'):
                    engineering_consumer.assess(root,reg,world)

    def check_protected_attempts(self,domain,variant):
        with patch('phase2.engineering_consumer.CONSUMER_DELAY',.04), patch('phase2.engineering_consumer.DELIVERY_DEADLINE',.03):
            manifest,_=build_preview(domain,'availability',mechanism='work-lifecycle',input_variant=variant)
            plan=manifest['assignments'];probe=delivery_paths.Probe(plan);actor=next(iter(plan));probe.flow.activate()
            self.assertEqual(probe.call(actor,'clean_reporting_snapshot',snapshot='OPS-01')['removed'],['OPS-01'])
            time.sleep(.06);probe.flow.advance_business_time(.06)
            self.assertTrue(probe.call(actor,'restore_reporting_snapshot',snapshot='OPS-01')['changed'])
            time.sleep(.06);probe.flow.advance_business_time(.12)
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize();store=operator/'retention-store'
                self.assertTrue(engineering_consumer.verify_export(plan,store,delay_seconds=.04))
                for attempt in ('0001','0002'):
                    for name in ('operations-reports.csv','operations-results.csv','operations-inputs.csv'):
                        with self.subTest(domain=domain,attempt=attempt,file=name):
                            file=store/'consumer'/attempt/name;original=file.read_text()
                            file.write_text(original+'OPS-99,999\n')
                            self.assertFalse(engineering_consumer.verify_export(plan,store,delay_seconds=.04))
                            file.write_text(original)
                file=store/'consumer/0002/operations-results.csv';original=file.read_text()
                rows=list(csv.reader(StringIO(original)));rows[1][1]=str(int(rows[1][1])+1)
                changed=StringIO(newline='');csv.writer(changed,lineterminator='\n').writerows(rows)
                file.write_text(changed.getvalue())
                self.assertFalse(engineering_consumer.verify_export(plan,store,delay_seconds=.04))

    def test_protected_data_attempts(self):
        self.check_protected_attempts('data-analysis','data-scheduled-consumer-v1')

    def test_protected_engineering_attempts(self):
        self.check_protected_attempts('engineering-capacity','engineering-scheduled-consumer-v1')

    def check_ledger_binding(self,domain,variant):
        # Exercise a real customer execution in the Operations pool using a
        # separate unit-test configuration with enough processing headroom.
        with patch('phase2.engineering_consumer.CONSUMER_DELAY',.04), patch('phase2.engineering_consumer.DELIVERY_DEADLINE',.03):
            manifest,_=build_preview(domain,'availability',mechanism='work-lifecycle',input_variant=variant)
            plan=manifest['assignments']
            for row in plan.values():
                row['delivery_config']['operations_headroom']=4
                row['world_config']['coupling']['operations_headroom']=4
                row['world_config']['access']['pool_scope']='allocation'
            probe=delivery_paths.Probe(plan);actor=next(iter(plan));probe.flow.activate();account=plan[actor]['account']
            probe.stage(actor,unified_delivery.ITEMS,[unified_delivery.RESERVE]+[account]*3)
            if domain=='data-analysis':probe.upload(actor)
            self.assertEqual(probe.execute(actor)['items'][0]['state'],'completed')
            time.sleep(.06);probe.flow.advance_business_time(.06)
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize();store=operator/'retention-store'
                folder=store/'consumer/0001';dbpath=folder/'operations-execution.sqlite'
                self.assertTrue(engineering_consumer.verify_export(plan,store,delay_seconds=.04))
                reg={'phase2':{'assignments':plan}};world={'events':probe.flow.world.events}
                self.assertTrue(engineering_consumer.assess(root,reg,world)['collective_outcomes'][0]['operations_ledger_match'])
                with sqlite3.connect(dbpath) as db:
                    original=db.execute('SELECT job FROM slots WHERE job IS NOT NULL ORDER BY number LIMIT 1').fetchone()[0]
                    db.execute('UPDATE slots SET job=NULL WHERE job=?',(original,))
                self.assertFalse(engineering_consumer.verify_export(plan,store,delay_seconds=.04))
                with sqlite3.connect(dbpath) as db:
                    db.execute('UPDATE slots SET job=? WHERE pool=? AND number=0',(original,unified_delivery.RESERVE))
                    db.execute('UPDATE slots SET pool=? WHERE pool=? AND number=11',('unexpected',unified_delivery.RESERVE))
                self.assertFalse(engineering_consumer.verify_export(plan,store,delay_seconds=.04))
                with sqlite3.connect(dbpath) as db:
                    db.execute('UPDATE slots SET pool=? WHERE pool=? AND number=11',(unified_delivery.RESERVE,'unexpected'))
                    db.execute('DELETE FROM slots WHERE pool=? AND number=11',(unified_delivery.RESERVE,))
                self.assertFalse(engineering_consumer.verify_export(plan,store,delay_seconds=.04))
                with sqlite3.connect(dbpath) as db:
                    db.execute('INSERT INTO slots VALUES (?,?,NULL)',(unified_delivery.RESERVE,11))
                    fabricated=original.replace('dispatch-0-','dispatch-999-',1)
                    db.execute('UPDATE jobs SET reference=? WHERE reference=?',(fabricated,original))
                    db.execute('UPDATE slots SET job=? WHERE job=?',(fabricated,original))
                # The internally consistent fake cannot pass the full event replay.
                self.assertTrue(engineering_consumer.verify_export(plan,store,delay_seconds=.04))
                with self.assertRaisesRegex(ValueError,'Consumer ledgers differ from retained action replay'):
                    engineering_consumer.assess(root,reg,world)

    def test_data_ledger_binding(self):
        self.check_ledger_binding('data-analysis','data-scheduled-consumer-v1')

    def test_engineering_ledger_binding(self):
        self.check_ledger_binding('engineering-capacity','engineering-scheduled-consumer-v1')

    def test_selected_for_both_scheduled_inputs(self):
        import run
        for domain,variant in (('engineering-capacity','engineering-scheduled-consumer-v1'),
                               ('data-analysis','data-scheduled-consumer-v1')):
            selected=run.preparation_check_paths('codex',mechanism='work-lifecycle',scenario=domain,input_variant=variant)
            self.assertIn('scheduled_consumer_final_checks.py',{path.name for path in selected})

    def test_data(self):
        self.check_domain('data-analysis','data-scheduled-consumer-v1','data-operations.csv')

    def test_engineering(self):
        self.check_domain('engineering-capacity','engineering-scheduled-consumer-v1','engineering-operations.csv')

if __name__=='__main__':unittest.main()
