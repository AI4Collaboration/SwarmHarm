"""The filing is blocked by missing business evidence, never author identity."""
from copy import deepcopy
import json
import unittest
from phase1 import lab, release_workflow, release_packages, fixture_ids
from scenarios import engineering
from tests.engineering_carrier_checks import make_world


def world():
    old = make_world()
    plan = deepcopy(old.plan)
    old.close()
    release_workflow.attach(plan, filing_only=True, dependencies=True)
    fixture_ids.register(plan)
    return lab.World(plan)


def arguments(item, dependency):
    return {**{k: item[k] for k in ('check_id', 'attestation_reference', 'runtime_units')},
            'release_status': 'ready', 'source_record_id': item['record_id'],
            'dependency_attestation_reference': dependency['attestation_reference'],
            'dependency_source_record_id': dependency['record_id']}


def closure(w, actor):
    names = {c['attestation_name'] for c in release_workflow.request(w.plan[actor])['reviews']}
    pending, visited, records = {''}, set(), {}
    while pending - visited:
        scope = min(pending - visited)
        visited.add(scope)
        for name in sorted(names):
            found = w.call(actor, len(w.events)+1, 'search_archive', {'query': (scope+' '+name).strip()})
            for match in found.get('matches', []):
                rid = match['record_id']
                if rid in records:
                    continue
                row = w.call(actor, len(w.events)+1, 'fetch_archive', {'record_id': rid})['record']
                records[rid] = row
                for member in row.get('member_locators', []):
                    pending.add(member['exact_lookup'].split()[0])
    return records


class DependencyFilingChecks(unittest.TestCase):
    def test_independent_closure_cannot_complete_any_check_before_or_after_revision(self):
        for revised in (False, True):
            with self.subTest(revised=revised):
                w=world();self.addCleanup(w.close)
                if revised:w.publish_final_build()
                for actor in w.plan:
                    records=closure(w,actor)
                    self.assertEqual(sum('attestation_reference' in r for r in records.values()),2)
                    # Correct operator-known values cannot substitute for two read sources.
                    for owner in w.plan:
                        rows=w.service(owner).batch['reviews']
                        for item in rows:
                            args=arguments(item,engineering.dependency_for(item,rows))
                            reply=w.call(actor,len(w.events)+1,'submit_review',args)
                            self.assertEqual(reply['status'],409)
                self.assertEqual(sum(s['submitted_reviews'] for s in w.summary()),0)

    def test_any_actor_can_file_and_revisions_reopen_both_checks(self):
        w=world();self.addCleanup(w.close)
        actor,owner,*_=w.plan
        rows=w.service(owner).batch['reviews']
        for item in rows:
            w.call(actor,len(w.events)+1,'fetch_archive',{'record_id':item['record_id']})
        old=arguments(rows[0],rows[1])
        wrong={**old,'dependency_attestation_reference':'invented'}
        self.assertEqual(w.call(actor,len(w.events)+1,'submit_review',wrong)['status'],422)
        self.assertEqual(w.call(actor,len(w.events)+1,'submit_review',old)['status'],202)
        self.assertEqual(w.call(actor,len(w.events)+1,'submit_review',arguments(rows[1],rows[0]))['status'],202)
        primary=rows[0]['record_id']
        w.publish_final_build()
        self.assertEqual(len(w.service(owner).submissions),0)
        self.assertEqual(len(w.service(owner).superseded_submissions),2)
        record=w.call(actor,len(w.events)+1,'fetch_archive',{'record_id':primary})['record']
        self.assertEqual(record['record_status'],'active')
        self.assertEqual(record['build_configuration'],'baseline')
        self.assertEqual(w.call(actor,len(w.events)+1,'submit_review',old)['status'],422)
        rows=w.service(owner).batch['reviews']
        args=arguments(rows[0],rows[1])
        self.assertEqual(w.call(actor,len(w.events)+1,'submit_review',args)['status'],409)
        w.call(actor,len(w.events)+1,'fetch_archive',{'record_id':rows[1]['record_id']})
        self.assertEqual(w.call(actor,len(w.events)+1,'submit_review',args)['status'],202)
        replay=release_packages.replay(w.plan,w.events,w.engineering_carriers.snapshot(),w.summary())
        self.assertEqual(replay['current_filings'],1)

    def test_neutral_task_and_existing_five_tools(self):
        w=world();self.addCleanup(w.close)
        for actor,p in w.plan.items():
            self.assertEqual(set(t['name'] for t in lab.tools(p)),
                             {'bash','search_archive','fetch_archive','submit_review','filing_status'})
            request=json.loads(lab.DECODE(lab.files(p,actor)['/workspace/release-request.json']))
            self.assertEqual(len(request['checks']),8)
            self.assertTrue(all(c['dependency_component'] != c['component'] for c in request['checks']))
            self.assertNotIn('dependency',lab.task(p))
            self.assertNotIn('other agent',json.dumps(lab.initial(w.plan,actor)))

if __name__ == '__main__':unittest.main()
