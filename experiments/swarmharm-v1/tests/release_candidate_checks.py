"""Compiled candidate delivery is possible before full release qualification."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import run
from phase1 import engineering_carriers as carriers, engineering_carrier_controls as channel
from phase1 import release_packages as packages, release_package_controls as controls, lab
from phase1.filing_controls import FilingWitness
from tests import release_package_checks as legacy


class ReleaseCandidateChecks(unittest.TestCase):
    witness = legacy.ReleasePackageChecks.witness
    replay = legacy.ReleasePackageChecks.replay

    def test_partial_candidate_delivers_without_qualifying_release(self):

        w,_ = self.witness(full=False)
        for actor in w.world.plan:
            result = controls.publish(w,actor,package=packages.CANDIDATE)
            self.assertEqual(result['candidate_package']['state'],'ready')
            self.assertTrue(result['candidate_package']['receipt']['compiled_sha256'])
            status = w.call(actor,'release_package_status',{})
            self.assertEqual(status['candidate']['state'],'ready')
            self.assertEqual(status['package']['state'],'unpublished')
            self.assertFalse(run.rollout_completion_state(w.world,actor)['actor_complete'])
        replay = self.replay(w)
        self.assertEqual(replay['ready_candidates'],4)
        self.assertEqual(replay['ready_packages'],0)
        w.world.close()
        self.assertEqual(self.replay(w)['ready_candidates'],4)

    def test_new_filings_stale_the_candidate_and_final_only_does_not_finish(self):
        w,_ = self.witness(full=False)
        for actor in w.world.plan: controls.publish(w,actor,package=packages.CANDIDATE)
        received=channel.transmit(w);w.finish(received)
        for actor in w.world.plan:
            self.assertEqual(w.world.release_packages.candidate_status(actor)['state'],'in_review')
            self.assertEqual(controls.publish(w,actor,stage_candidate=False)['release_package']['state'],'ready')
            self.assertFalse(run.rollout_completion_state(w.world,actor)['actor_complete'])
        self.assertEqual(self.replay(w)['ready_candidates'],0)
        for actor in w.world.plan: controls.publish(w,actor,package=packages.CANDIDATE)
        self.assertTrue(run.rollout_completion_state(w.world,actor)['complete'])
        replay=self.replay(w)
        self.assertEqual((replay['ready_candidates'],replay['ready_packages']),(4,4))

    def test_candidate_rejects_empty_forged_and_unqualified_compilation(self):
        w,_ = self.witness(full=False)
        actor=next(iter(w.world.plan))
        source=controls.source_from_returns(w,actor)
        import ast
        body=ast.literal_eval(source.split('=',1)[1])
        empty=deepcopy(body);empty['checks']=[]
        forged=deepcopy(body);forged['checks'][0]['runtime_units']+=1
        for bad in (empty,forged):
            result=controls.publish(w,actor,'RELEASE = '+repr(bad)+'\n',package=packages.CANDIDATE)
            self.assertEqual(result['candidate_package']['state'],'in_review')
        for i,opts in enumerate(({'consume':False},{'mode':'incremental'}),1):
            result=controls.publish(w,actor,source+'\n'*i,package=packages.CANDIDATE,**opts)
            self.assertEqual(result['candidate_package']['state'],'in_review')
        result=controls.publish(w,actor,source,package=packages.CANDIDATE)
        self.assertEqual(result['candidate_package']['state'],'ready')
        original=w.world.snapshot()
        for kind in ('receipt','status','bytes'):
            s=deepcopy(original)
            if kind=='receipt':
                event=next(e for e in s['events'] if 'candidate_package' in e['result'])
                event['result']['candidate_package']['receipt']['compiled_sha256']='0'*64
            elif kind=='status':s['summary'][0]['candidate_package']['state']='unpublished'
            else:s['engineering_carrier_probe']['published_artifacts'][0]['content']+='\n'
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                packages.replay(s['plan'],s['events'],s['engineering_carrier_probe'],s['summary'])

    @patch.object(carriers,'REVISION','engineering-carriers-feasibility-v8')
    def test_v8_keeps_its_original_task_and_no_candidate_requirement(self):
        fresh,_=self.witness(full=False)
        plan=deepcopy(fresh.world.plan);fresh.world.close()
        for item in plan.values():item[carriers.FIELD]['revision']='engineering-carriers-feasibility-v8'
        w=FilingWitness(plan,'cache_value_repaired');self.addCleanup(w.world.close)
        w.ordinary();w.finish(channel.transmit(w))
        controls.publish_all(w)
        for actor,item in plan.items():
            self.assertNotIn('qualification',lab.task(item))
            self.assertNotIn('candidate_package',w.world.summary()[0])
            self.assertNotIn('Candidate qualification',lab.DECODE(lab.files(item,actor)['/workspace/PLATFORM.md']))
            self.assertTrue(run.rollout_completion_state(w.world,actor)['complete'])
        self.assertEqual(self.replay(w)['revision'],packages.REVISION)
        self.assertNotIn('ready_candidates',self.replay(w))


if __name__ == '__main__': unittest.main()
