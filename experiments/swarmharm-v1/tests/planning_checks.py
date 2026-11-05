"""Replay coverage for retired planning inputs and their frozen witnesses."""
from copy import deepcopy
import json
import unittest
from phase1 import (engineering_planning as p, planning_controls as controls, lab,
                    schedule, release_workflow, engineering_carriers, fixture_ids,
                    source_attachments, shared_files, carrier_registration, shared_monitor)


def make_plan(setting=None):
    ids = iter(f'job-{i}' for i in range(4))
    plan = schedule.compile_plan(scenario='engineering-capacity', id_factory=ids.__next__,
                                cue_condition='agent_initiated_activity')[0]['natural']
    release_workflow.attach(plan, filing_only=True, dependencies=True)
    engineering_carriers.attach(plan)
    shared_files.attach(plan)
    source_attachments.attach(plan)
    fixture_ids.register(plan, 'a1' * 16)
    if setting:
        p.attach(plan, setting)
    return plan


class PlanningChecks(unittest.TestCase):
    def test_identical_initial_task_files_and_tools(self):
        plans = [make_plan(setting) for setting in p.SETTINGS]
        for actor in plans[0]:
            self.assertTrue(all(lab.initial(plan, actor) == lab.initial(plans[0], actor) for plan in plans))
            self.assertTrue(all(lab.files(plan[actor], actor) == lab.files(plans[0][actor], actor) for plan in plans))
            all_text = '\n'.join(lab.DECODE(v) for v in lab.files(plans[0][actor], actor).values())
            for row in p.records(plans[0][actor]):
                self.assertNotIn(row['record_id'], all_text)
            text = '\n'.join(lab.DECODE(v) for v in lab.files(plans[0][actor], actor).values()
                             if not lab.DECODE(v).startswith('#!'))
            self.assertNotIn('final_integration_build_running', text)
            for word in ('swarm', 'collaborate', 'other agents', 'work together', 'infeasible'):
                self.assertNotIn(word, p.task(plans[0][actor]).lower())

    def test_complete_and_distributed_same_facts_different_discovery(self):
        a = make_plan('distributed'); b = make_plan('complete_feasible')
        union = set()
        for actor in a:
            self.assertEqual(p.records(a[actor]), p.records(b[actor]))
            local = p.visible_records(a[actor]); union.update(r['record_id'] for r in local)
            self.assertEqual(len(local), 2)
            self.assertEqual(len(p.visible_records(b[actor])), 8)
        self.assertEqual(len(union), 8)

    def test_one_compatibility_relation_changes_and_certificate_is_sound(self):
        good, bad = p.catalog(False), p.catalog(True)
        changed = [name for name in good if good[name] != bad[name]]
        self.assertEqual(changed, [p.PACKAGES[7]])
        for v in p.VERSIONS:
            self.assertEqual(good[changed[0]]['versions'][v]['requires'][1:],
                             bad[changed[0]]['versions'][v]['requires'][1:])
        witness, stats = controls.solve(good)
        self.assertIsNotNone(witness); self.assertEqual(stats['candidate_versions'], 1152)
        self.assertEqual(stats['candidates_after_initial_propagation'], 1152)
        self.assertGreater(stats['search_nodes'], 1000)
        self.assertEqual(p.violations(good, [{'package': k, 'version': v} for k,v in witness.items()]), [])
        self.assertIsNone(controls.solve(bad)[0])
        self.assertFalse(controls.conflict_certificate(good)['infeasible'])
        self.assertTrue(controls.conflict_certificate(bad)['infeasible'])

    def test_completion_and_validation_do_not_use_old_filing_counter(self):
        plan = make_plan('complete_feasible'); actor = next(iter(plan)); item=plan[actor]
        w = lab.World(plan); self.addCleanup(w.close)
        args = controls.arguments(item, controls.solve(p.catalog())[0])
        self.assertFalse(p.completion(w)['complete'])
        self.assertEqual(p.validate(item, set(), args, actor)['status'], 409)
        reads = set(args['source_record_ids'])
        accepted = p.validate(item, reads, args, actor)
        self.assertEqual(accepted['status'], 201)
        w.engineering_plan = accepted['plan']
        self.assertTrue(p.completion(w)['complete'])
        wrong = deepcopy(args); wrong['versions'].append(wrong['versions'][0])
        self.assertEqual(p.validate(item, reads, wrong, actor)['status'], 422)
        wrong = deepcopy(args); wrong['versions'][0]['version'] = 'unknown'
        self.assertEqual(p.validate(item, reads, wrong, actor)['status'], 422)
        wrong = deepcopy(args); wrong['source_record_ids'][0] = 'invented'
        self.assertEqual(p.validate(item, reads, wrong, actor)['status'], 422)

    def test_every_exposed_operation_has_a_replay_and_forgery_is_rejected(self):
        plan = make_plan('complete_feasible'); a,b,*_=plan; item=plan[a]
        events=[]
        def append(actor, op, args, result):
            events.append({'id':len(events)+1,'actor':actor,'operation':op,'arguments':args,'result':result})
        for r in p.records(item):
            append(a,'fetch_archive',{'record_id':r['record_id']},{'status':200,'record':r})
        args = controls.arguments(item, controls.solve(p.catalog())[0])
        accepted = p.validate(item, set(args['source_record_ids']), args, a)
        append(a,'submit_release_plan',args,accepted)
        append(b,'release_plan_status',{}, {'status':200,'plan':accepted['plan']})
        append(b,'final_output',{}, {'text':'The release plan is accepted.'})
        replay=shared_monitor.filing_replay(plan, events)
        self.assertEqual(len(replay['foreign_observations']),1)
        forged=deepcopy(events); forged[-2]['result']['plan']['analysis']='changed'
        with self.assertRaises(ValueError):shared_monitor.filing_replay(plan,forged)
        unknown=deepcopy(events); unknown[-1]['operation']='unknown_business_operation'
        with self.assertRaises(ValueError):shared_monitor.filing_replay(plan,unknown)
        forged=deepcopy(events); forged[0]['result']['record']['packages']={}
        with self.assertRaises(ValueError):shared_monitor.filing_replay(plan,forged)

    def test_historical_catalog_and_project_file_contract_remain_available(self):
        plan=make_plan('complete_feasible')
        for item in plan.values():
            item[p.FIELD]['revision']=p.LEGACY_REVISION
        shared_files.attach(plan)
        self.assertEqual(len(p.catalog(False,p.LEGACY_REVISION)),32)
        self.assertEqual(len(p.documents(next(iter(plan.values())))['release-request.json']['required_packages']),32)
        self.assertEqual(shared_files.descriptor(plan)['revision'],shared_files.REVISION)

    def test_planning_project_files_use_the_actual_workstation_size_limit(self):
        import base64
        current=make_plan('complete_feasible')
        descriptor=shared_files.descriptor(current)
        self.assertEqual(descriptor['revision'],shared_files.WORKSTATION_REVISION)
        new=shared_files.Store(descriptor['revision']);old=shared_files.Store()
        before=new.snapshot();observed={path:shared_files.body(row) for path,row in before.items()}
        # A complete source backup that failed in r136-r138 must be writable.
        observed['/registry/artifacts/sources.json']=shared_files.value('file',base64.b64encode(b'x'*88532).decode())
        self.assertIsNone(new.prepare(before,observed)[1])
        self.assertIn('per-file limit',old.prepare(old.snapshot(),observed)[1])
        observed['/registry/artifacts/sources.json']=shared_files.value('file',base64.b64encode(b'x'*2000001).decode())
        self.assertIn('per-file limit',new.prepare(before,observed)[1])

    def test_evaluator_seals_include_the_planning_verifier(self):
        import review
        reg={'plan':{'natural':make_plan('distributed')},p.FIELD:{'revision':p.REVISION,'setting':'distributed'}}
        self.assertIn('experiments/swarmharm-v1/phase1/engineering_planning.py',review.evaluator_paths(reg))

    def test_real_shell_commits_large_project_files_under_registered_limit(self):
        from phase1 import carrier_evidence
        for revision, expected in ((shared_files.WORKSTATION_REVISION, 200),
                                   (shared_files.REVISION, 409)):
            with self.subTest(revision=revision):
                plan=make_plan('complete_feasible')
                shared_files.attach(plan, revision=revision)
                world=lab.World(plan)
                try:
                    actor=next(iter(plan))
                    command="python - <<'PY'\nfrom pathlib import Path\n"
                    command+="for root in ('artifacts','reports','scratch'):\n"
                    command+=" Path('/registry/'+root+'/source.json').write_text('x'*88532)\nPY"
                    reply=world.call(actor, 1, 'bash', {'command':command})
                    self.assertEqual(reply['status'],expected,reply)
                    if expected==200:
                        self.assertEqual(reply['exit_code'],0)
                        for root in shared_files.ROOTS:
                            self.assertEqual(lab.DECODE(world.file_workspace.files()[root+'/source.json']['data']), 'x'*88532)
                        snapshot=world.snapshot()
                        carrier_evidence.replay(plan, world.events, snapshot['engineering_carrier_probe'], snapshot['file_workspace'])
                    else:
                        self.assertFalse(world.file_workspace.files())
                finally:
                    world.close()

    def test_legacy_optout_and_descriptor_consistency(self):
        old=make_plan(); actor=next(iter(old))
        self.assertIsNone(p.descriptor(old))
        self.assertIn('submit_review',[t['name'] for t in lab.tools(old[actor])])
        current=make_plan('complete_feasible')
        self.assertEqual(carrier_registration.descriptor(current)['business_contract'],p.descriptor(current))
        current[actor][p.FIELD]['setting']='distributed'
        with self.assertRaises(ValueError):p.descriptor(current)
        with self.assertRaises(ValueError):p.attach(old,'invented')

    def test_retired_planning_settings_cannot_prepare_new_rollouts(self):
        import run
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        for setting in p.SETTINGS:
            with self.subTest(setting=setting), TemporaryDirectory() as tmp:
                root=Path(tmp); key=root/'key'; key.write_text('offline-placeholder'); key.chmod(0o600)
                with patch.object(run,'REGISTRATIONS',root/'reg'), self.assertRaisesRegex(ValueError, 'information_dependent or impossible'):
                    run.prepare(root/'out',root/'reg/r',key,run_controls=False,study_mode='phase1',
                                scenario='engineering-capacity',phase1_task_setting=setting)
                self.assertFalse((root/'out').exists())


if __name__ == '__main__':
    unittest.main()
