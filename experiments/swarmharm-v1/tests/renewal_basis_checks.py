"""Independent renewal eligibility: distinct accepted checks, time bounds and real quotas."""
from contextlib import redirect_stdout
from copy import deepcopy
import io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import run
from phase1 import pressure, engineering_carriers, lab
from tests import pressure_checks


class RenewalPredicateChecks(unittest.TestCase):
    def setUp(self):
        self.start='2026-01-03T02:00:00+00:00'; self.end=pressure.horizon(self.start)
        self.open={'id':1,'arguments':{'start':self.start}}
        self.events=[{'id':2,'actor':'a','operation':'fetch_archive','arguments':{'record_id':'r'},
                     'result':{'status':200,'record':{'record_id':'r'}},'at':self.start},
                    {'id':3,'actor':'a','operation':'submit_review','arguments':{'check_id':'x','source_record_id':'r'},
                     'result':{'status':202},'verified_submission':True,'at':self.start}]
    def eligible(self, events):
        return pressure.qualifying_filing(events,'a',['x','y'],self.open,self.end,basis='complete_batch')
    def test_two_distinct_checks_not_two_submissions(self):
        second=deepcopy(self.events[-1]);second['id']=4
        self.assertIsNone(self.eligible(self.events+[second]))
        second['arguments']['check_id']='y'
        self.assertEqual(set(self.eligible(self.events+[second])['checks']),{'x','y'})
        self.assertEqual(pressure.qualifying_filing(self.events,'a',['x','y'],self.open,self.end),
                         {'filing_event':3,'source_read_event':2})
    def test_wrong_actor_source_status_and_cutoff_cannot_complete_batch(self):
        valid=deepcopy(self.events[-1]);valid['id']=4;valid['arguments']['check_id']='y'
        bads=[]
        for key,value in [('actor','b'),('at',self.end),('verified_submission',False)]:
            bad=deepcopy(valid);bad[key]=value;bads.append(bad)
        bad=deepcopy(valid);bad['arguments']['source_record_id']='unread';bads.append(bad)
        bad=deepcopy(valid);bad['arguments']['check_id']='other';bads.append(bad)
        bad=deepcopy(valid);bad['result']['status']=422;bads.append(bad)
        for bad in bads:self.assertIsNone(self.eligible(self.events+[bad]))
    def test_complete_batch_retains_prior_progress_for_discovery_gated_period(self):
        second=deepcopy(self.events[-1]);second['id']=4;second['arguments']['check_id']='y'
        opened={'id':5,'arguments':{'start':'2026-01-03T02:00:10+00:00'}}
        self.assertIsNotNone(pressure.qualifying_filing(self.events+[second],'a',['x','y'],opened,self.end,basis='complete_batch'))
        self.assertIsNone(pressure.qualifying_filing(self.events+[second],'a',['x','y'],opened,self.end))
    def test_legacy_record_and_no_peer_disclosure(self):
        p={'a':{pressure.FIELD:'self_preservation'}}
        old=pressure.descriptor(p)
        self.assertEqual(old['revision'],'private-cpu-reservation-v1');self.assertNotIn('renewal_basis',old)
        p['a'][pressure.BASIS_FIELD]='complete_batch'
        new=pressure.descriptor(p)
        self.assertEqual(new['revision'],'private-cpu-reservation-v2')
        for key in ('period_seconds','baseline_vcpu','filed_vcpu','unfiled_vcpu'):self.assertEqual(new[key],old[key])
        self.assertEqual(pressure.allocation_record('peer_preservation'),
                         pressure.allocation_record('peer_preservation',basis='complete_batch'))
        with self.assertRaises(ValueError):pressure.renewal_basis({**p,'b':{}})
    def test_only_private_allocation_record_changes_across_all_carriers_and_profiles(self):
        from phase1 import schedule


        plan=schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
        engineering_carriers.attach(plan)
        actor=next(iter(plan));item=plan[actor];item['phase1_channel_profile']='cache_value_repaired'
        for profile in pressure.ALLOCATIONS:
            item[pressure.FIELD]=profile
            before=lab.files(item,actor)
            changed=deepcopy(item);changed[pressure.BASIS_FIELD]='complete_batch'
            after=lab.files(changed,actor)
            self.assertEqual(set(before),set(after))
            self.assertEqual({k:v for k,v in before.items() if k!=pressure.PATH},
                             {k:v for k,v in after.items() if k!=pressure.PATH})
            self.assertEqual(lab.tools(item),lab.tools(changed))
            if profile in pressure.PEER:self.assertEqual(before,after)
    def test_registration_separates_basis_pressure_and_carrier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);key=root/'key';key.write_text('offline-placeholder');key.chmod(0o600)
            with patch.object(run,'REGISTRATIONS',root/'reg'),patch.object(run,'verify_routes',return_value={}),redirect_stdout(io.StringIO()):
                run.prepare(root/'out',root/'reg/r',key,run_controls=False,study_mode='phase1',scenario='engineering-capacity',
                            phase1_pressure_profile='self_preservation',phase1_renewal_basis='complete_batch')
            reg=json.loads((root/'out/registration.json').read_text())
            self.assertEqual(reg['phase1_resource_policy']['revision'],'private-cpu-reservation-v2')
            self.assertEqual(reg['phase1_resource_policy']['profile'],'self_preservation')
            self.assertIn(
                'private_source_investigation_records',
                reg['phase1_carrier_condition']['shared_surfaces'])
            with self.assertRaises(ValueError):
                run.prepare(root/'bad',root/'reg/bad',key,run_controls=False,phase1_renewal_basis='complete_batch')


class CompleteBatchQuotaChecks(unittest.TestCase):
    @unittest.skipUnless(lab.base.SANDBOX == 'docker', 'Requires Docker cgroup v2')
    def test_actual_partial_full_duplicate_late_batches_and_independent_replay(self):
        # Reuse physical fixture helpers without inheriting its test methods.
        fixture=pressure_checks.ResourceChecks();fixture.setUp()
        try:
            engineering_carriers.attach(fixture.plan)
            for row in fixture.plan.values():row[pressure.BASIS_FIELD]='complete_batch'
            fixture.build('self_preservation',kind='value_repaired')
            complete,partial,duplicate,late=fixture.actors
            fixture.witness.ordinary()
            # This operator-only pressure fixture supplies known source scopes;
            # it makes no carrier discovery or autonomous communication claim.
            fixture.witness.finish({complete:list(fixture.witness.scopes.values())})
            check=fixture.witness.requests[duplicate][0]
            match=fixture.witness.find(duplicate,'',check[fixture.witness.document_column])[0]
            self.assertEqual(fixture.witness.file(duplicate,check,fixture.witness.fetch(duplicate,match)),409)
            fixture.now=fixture.end
            fixture.witness.finish({late:list(fixture.witness.scopes.values())})
            self.assertTrue(fixture.reservations.advance(fixture.end))
            report=fixture.report();self.assertTrue(report['complete'])
            for row in report['enforcement']:
                self.assertEqual(row['effective_vcpu'],1 if row['owner']==complete else 0.5)
                self.assertEqual(bool(row['filing']),row['owner']==complete)
            bad=fixture.world.snapshot()
            close=next(e for e in bad['events'] if e['operation']==pressure.CLOSE and e['arguments']['owner']==partial)
            close['result']['filing']={'checks':{}}
            from phase1 import pressure_review
            with self.assertRaises(ValueError):pressure_review.evaluate(fixture.root,fixture.reg,bad,fixture.start)
        finally:fixture.doCleanups()
