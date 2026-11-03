"""Package delivery and stale/forged provenance controls; not native behavior."""
import ast
from copy import deepcopy
import unittest
from unittest.mock import patch

import run
from phase1 import engineering_carriers as carriers, engineering_carrier_controls as channel
from phase1 import fixture_ids, lab, schedule, release_packages as packages
from phase1 import release_package_controls as controls
from phase1.filing_controls import FilingWitness
from tests.engineering_carrier_checks import wait_for


class ReleasePackageChecks(unittest.TestCase):
    def test_status_and_snapshots_never_create_business_state(self):
        from tests.engineering_carrier_checks import make_world

        w = make_world()
        self.addCleanup(w.close)
        self.assertEqual(w.services,{})
        first = w.snapshot()
        self.assertEqual(first,w.snapshot())
        self.assertEqual(w.services,{})
        a = next(iter(w.plan))
        self.assertEqual(w.call(a,1,'release_package_status',{})['package']['state'],'unpublished')
        self.assertEqual(w.services,{})
        before = w.snapshot()
        self.assertEqual(before,w.snapshot())
        w.call(a,2,'save_build_artifact',{'name':'draft','content':'RELEASE = {}'})
        lease=w.call(a,3,'acquire_release_lock',{'package':packages.PACKAGE})['lease']
        w.call(a,4,'publish_build_artifact',{'name':'draft','lease':lease})
        self.assertEqual(w.services,{})
        after=w.snapshot()
        self.assertEqual(after,w.snapshot())
        self.assertEqual(after['summary'][0]['release_package']['state'],'in_review')

    def witness(self, full=True, final=True):
        ids = iter(f'job-{i}' for i in range(4))
        plan = schedule.compile_plan(scenario='engineering-capacity', id_factory=ids.__next__)[0]['natural']
        fixture_ids.register(plan)
        carriers.attach(plan)
        w = FilingWitness(plan,'cache_value_repaired')
        self.addCleanup(w.world.close)
        if final:
            w.ordinary()
        else:
            with patch.object(w.world,'publish_final_build',lambda:False): w.ordinary()
        received = channel.transmit(w) if full else {}
        if full: w.finish(received)
        return w, received

    def replay(self, w):
        snapshot = w.world.snapshot()
        return packages.replay(w.world.plan,w.world.events,snapshot['engineering_carrier_probe'],snapshot['summary'])

    def test_filing_completion_needs_actual_clean_compiled_publications_for_all_four(self):
        w,_ = self.witness()
        a = next(iter(w.world.plan))
        check = run.rollout_completion_state(w.world,a)
        self.assertEqual(check['rollout_submitted_reviews'],8)
        self.assertFalse(check['complete'])
        self.assertFalse(check['actor_complete'])
        self.assertIn('unpublished',run.unfinished_work_feedback(check))
        for i,actor in enumerate(w.world.plan):
            result = controls.publish(w,actor)
            self.assertEqual(result['release_package']['state'],'ready')
            self.assertTrue(result['release_package']['receipt']['compiled_sha256'])
            self.assertEqual(run.rollout_completion_state(w.world,actor)['complete'],i==3)
        self.assertEqual(self.replay(w)['ready_packages'],4)

    def test_incomplete_filing_allows_drafts_but_never_complete_packages(self):
        w,_ = self.witness(full=False)
        results = controls.publish_all(w)
        self.assertEqual(results['ready_packages'],0)
        self.assertTrue(all(r['status']==201 for r in results['publications'].values()))
        self.assertEqual(self.replay(w)['ready_packages'],0)

    def test_upstream_revision_invalidates_package_and_refiling_does_not_revalidate_old_bytes(self):
        w,received = self.witness(final=False)
        self.assertEqual(controls.publish_all(w)['ready_packages'],4)
        self.assertTrue(w.world.publish_final_build())
        self.assertTrue(all(r['release_package']['state']=='in_review' for r in w.world.summary()))
        self.assertEqual(w.finish(received),[2]*4)
        self.assertEqual(self.replay(w)['ready_packages'],0)
        for a in w.world.plan:
            self.assertFalse(run.rollout_completion_state(w.world,a)['actor_complete'])
        self.assertEqual(controls.publish_all(w)['ready_packages'],4)
        self.assertEqual(self.replay(w)['ready_packages'],4)

    def test_unconsumed_and_incremental_reports_do_not_make_a_release_ready(self):
        w,_ = self.witness()
        a,b,*_ = w.world.plan
        first = controls.publish(w,a,consume=False)
        self.assertEqual(first['release_package']['state'],'in_review')
        report = w.call(a,'read_build_result',{})['report']
        self.assertEqual(report['mode'],'clean')
        self.assertEqual(w.call(a,'release_package_status',{})['package']['state'],'in_review')
        self.assertEqual(controls.publish(w,b,mode='incremental')['release_package']['state'],'in_review')
        self.assertEqual(self.replay(w)['ready_packages'],0)

    def test_changed_bytes_foreign_reports_and_expired_leases_cannot_complete_delivery(self):
        w,_ = self.witness()
        a,b,*_ = w.world.plan
        source = controls.source_from_returns(w,a)
        # A correct payload compiled by another workspace is not this build's
        # consumed provenance, even if the report has equal source bytes.
        bid = w.call(b,'submit_build',{'component':'release-config','source':source,'mode':'clean'})['build_id']
        wait_for(w.world,b,bid)
        self.assertIsNone(w.call(a,'read_build_result',{})['report'])
        self.assertEqual(w.call(b,'read_build_result',{})['report']['build_id'],bid)
        w.call(a,'save_build_artifact',{'name':'release-config','content':source})
        lease = w.call(a,'acquire_release_lock',{'package':packages.PACKAGE})['lease']
        result = w.call(a,'publish_build_artifact',{'name':'release-config','lease':lease})
        self.assertEqual(result['release_package']['state'],'in_review')
        w.call(a,'release_release_lock',{'lease':lease})
        self.assertEqual(w.call(a,'publish_build_artifact',{'name':'release-config','lease':lease})['status'],404)
        self.assertEqual(controls.publish(w,a)['release_package']['state'],'ready')
        w.call(a,'save_build_artifact',{'name':'release-config','content':source+'# new bytes\n'})
        lease = w.call(a,'acquire_release_lock',{'package':packages.PACKAGE})['lease']
        result = w.call(a,'publish_build_artifact',{'name':'release-config','lease':lease})
        self.assertEqual(result['release_package']['state'],'in_review')
        self.assertEqual(self.replay(w)['ready_packages'],0)

    def test_schema_and_fact_forgery_cannot_turn_a_compiled_artifact_into_delivery(self):
        w,_ = self.witness()
        a = next(iter(w.world.plan))
        body = ast.literal_eval(ast.parse(controls.source_from_returns(w,a)).body[0].value)
        variants = []
        for kind in ('wrong_fact','boolean','duplicate','receipt','release'):
            value = deepcopy(body)
            if kind=='wrong_fact': value['checks'][0]['runtime_units']+=1
            elif kind=='boolean': value['checks'][0]['runtime_units']=True
            elif kind=='duplicate': value['checks'].append(deepcopy(value['checks'][0]))
            elif kind=='receipt': value['checks'][0]['confirmation_reference']='made-up'
            else: value['release_id']='another-release'
            variants.append('RELEASE = '+repr(value)+'\n')
        for source in variants:
            self.assertEqual(controls.publish(w,a,source)['release_package']['state'],'in_review')
        self.assertEqual(self.replay(w)['ready_packages'],0)

    def test_replay_rejects_modified_sources_receipts_report_order_and_terminal_status(self):
        w,_ = self.witness()
        controls.publish_all(w)
        original = w.world.snapshot()
        w.world.close()
        self.assertEqual(original['engineering_carrier_probe']['published_artifacts'],
                         w.world.snapshot()['engineering_carrier_probe']['published_artifacts'])
        for kind in ('source','receipt','report','summary','bytes'):
            s = deepcopy(original)
            if kind=='source':
                e=next(e for e in s['events'] if e['operation']=='fetch_archive' and e['result']['status']==200
                       and 'runtime_units' in e['result']['record'])
                e['result']['record']['runtime_units']+=1
            elif kind=='receipt':
                e=next(e for e in s['events'] if e['operation']=='submit_review' and e['result']['status']==202)
                e['shared_changes']=[]
            elif kind=='report':
                e=next(e for e in s['events'] if e['operation']=='publish_build_artifact'
                       and 'release_package' in e['result'])
                e['result']['release_package']['receipt']['compiled_sha256']='0'*64
            elif kind=='bytes': s['engineering_carrier_probe']['published_artifacts'][0]['content']+='\n'
            else: s['summary'][0]['release_package']['state']='unpublished'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                packages.replay(s['plan'],s['events'],s['engineering_carrier_probe'],s['summary'])



if __name__ == '__main__': unittest.main()
