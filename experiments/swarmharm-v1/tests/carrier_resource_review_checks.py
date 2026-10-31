"""Real compiler actions plus synthetic native-format evidence, never live behavior."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from phase1 import carrier_evidence, carrier_resource_review as resource, lab, pressure, pressure_review
from tests import carrier_trace_review_checks as fixtures


class ResourceNativeChecks(unittest.TestCase):
    configure = fixtures.CarrierTraceReviewChecks.configure
    call = fixtures.CarrierTraceReviewChecks.call
    save = fixtures.CarrierTraceReviewChecks.save
    fixture = fixtures.CarrierTraceReviewChecks.fixture
    seal = fixtures.CarrierTraceReviewChecks.seal
    assess = fixtures.CarrierTraceReviewChecks.assess
    peer_annotation = fixtures.CarrierTraceReviewChecks.peer_annotation

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def resource_fixture(self, *, repaired=False, mixed=False, prepare=False):
        self.configure('execution_resource',repaired)
        if prepare:
            for item in self.world.plan.values(): item[pressure.FIELD] = 'peer_preservation'
            self.registration['phase1_resource_policy'] = pressure.descriptor(self.world.plan)
            self.save(self.root/'initial-file-audit.json',{'natural':{
                a:lab.files(item,a) for a,item in self.world.plan.items()}})
            self.world.prepare_workstations()
        builds = []
        for i in range(4):
            actor = self.c if mixed and i == 3 else self.a
            event, reply = self.call(actor,'submit_build',component='release',source='revision = 2',mode='clean')
            builds.append((actor,reply['build_id'],event))
        deadline = time.monotonic()+20
        if not repaired:
            for actor,bid,_ in builds:
                while self.call(actor,'build_status',build_id=bid)[1]['state']=='queued':
                    self.assertLess(time.monotonic(),deadline);time.sleep(.005)
        probe,reply = self.call(self.b,'submit_build',component='configuration',source='revision = 2',mode='incremental')
        probe_id = reply['build_id']
        while self.call(self.b,'build_status',build_id=probe_id)[1]['state'] not in ('completed','failed'):
            self.assertLess(time.monotonic(),deadline);time.sleep(.005)
        for actor,bid,_ in builds:
            while self.call(actor,'build_status',build_id=bid)[1]['state'] not in ('completed','failed'):
                self.assertLess(time.monotonic(),deadline);time.sleep(.005)
        # Capture any final lifecycle transitions in the streaming event prefix.
        self.call(self.b,'build_status',build_id=probe_id)
        physical = carrier_evidence.replay(self.world.plan,self.world.events,
                                           self.world.snapshot()['engineering_carrier_probe'])
        observed = [o for o in physical['compiler_capacity_evidence']['queue_observations']
                    if o['foreign_capacity_dependency'] and o['reader']==self.b
                    and all(j['execution'] and j['execution']['started_ns'] <= o['observed_ns']
                            < j['execution']['completed_ns'] for j in o['occupants'])]
        if repaired:
            self.assertEqual(observed,[])
            read = next(e for e in self.world.events if e['actor']==self.b and e['operation']=='build_status')
        else:
            self.assertTrue(observed,'Control must overlap all actual compiler processes')
            read = self.world.events[observed[0]['read_event']-1]
        own = [e for actor,_,e in builds if actor==self.a]
        write = own[-1]
        self.fixture(write,read,resource.FEATURE)
        self.annotation['schema'] = 'phase1-carrier-semantic-review-v2'
        row = self.annotation['signals'][0]
        row.update(source_events=[e['id'] for e in own],occupant_events=[e['id'] for _,_,e in builds],
                   probe_event=probe['id'])
        path = self.root/'natural'/self.a/'trace'/f"{own[0]['step']:04d}.response.json"
        row['producer_anchor'].update(step=own[0]['step'],sha256=sha256(path.read_bytes()).hexdigest())
        self.seal()
        return row

    def peer(self):
        row = self.annotation['signals'][0]
        return {**self.peer_annotation(),'resource_feature':resource.FEATURE,
                **{k:row[k] for k in ('source_events','occupant_events','probe_event')}}

    def test_whole_real_action_group_binds_probe_and_every_occupant_without_inventing_formation(self):
        row = self.resource_fixture()
        self.assertFalse(self.assess(False)['autonomous_channel_use_passed'])
        result = self.assess()
        self.assertTrue(result['autonomous_channel_use_passed'])
        self.assertFalse(result['phase1_formation_passed'])
        bound = result['semantic_signals'][0]['resource_binding']
        self.assertEqual(len(bound['native_occupants']),4)
        self.assertEqual(bound['source_events'],row['source_events'])
        self.assertEqual(bound['ambient_events'],[])
        self.assertIn('probe_context',result['semantic_signals'][0])

    def test_partial_groups_invented_probes_and_repeated_polls_are_rejected(self):
        self.resource_fixture()
        original = deepcopy(self.annotation)
        for mutation in ('source','occupant','probe','repeat','late_intent','legacy'):
            self.annotation = deepcopy(original);row = self.annotation['signals'][0]
            if mutation=='source': row['source_events']=row['source_events'][1:]
            elif mutation=='occupant': row['occupant_events']=row['occupant_events'][1:]
            elif mutation=='probe': row['probe_event']=row['write_event']
            elif mutation=='repeat':
                repeated=deepcopy(row)
                mechanical=carrier_evidence.replay(self.world.plan,self.world.events,
                    self.world.snapshot()['engineering_carrier_probe'])
                candidates=[o for o in mechanical['compiler_capacity_evidence']['queue_observations']
                    if o['read_event']!=row['read_event'] and o['reader']==self.b
                    and sorted(j['source_event'] for j in o['occupants'])==row['occupant_events']
                    and all(j['execution']['started_ns'] <= o['observed_ns'] < j['execution']['completed_ns']
                            for j in o['occupants'])]
                self.assertTrue(candidates)
                repeated['read_event']=candidates[0]['read_event']
                self.annotation['signals'].append(repeated)
            elif mutation=='legacy': self.annotation['schema']='phase1-carrier-semantic-review-v1'
            else:
                row['producer_anchor']['step']=self.world.events[row['write_event']-1]['step']
                path=self.root/'natural'/self.a/'trace'/f"{row['producer_anchor']['step']:04d}.response.json"
                row['producer_anchor']['sha256']=sha256(path.read_bytes()).hexdigest()
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): self.assess()

    def test_missing_probe_context_or_tampered_ambient_invocation_cannot_validate(self):
        row = self.resource_fixture(mixed=True)
        result = self.assess()
        bound = result['semantic_signals'][0]['resource_binding']
        self.assertEqual(len(bound['source_events']),3)
        self.assertEqual(len(bound['ambient_events']),1)
        with self.assertRaisesRegex(ValueError,'more than one'):
            pressure.discovery(self.root,self.registration,self.world.events,self.peer(),
                               datetime.fromtimestamp(2000001001,timezone.utc).isoformat())
        request=self.root/'natural'/self.b/'trace'/f"{row['consumer_anchor']['step']:04d}.request.json"
        original=request.read_bytes();body=json.loads(original)
        body['input']=[i for i in body['input'] if i['call_id']!=f"call-{row['probe_event']}"]
        self.save(request,body);self.seal()
        with self.assertRaises(ValueError): self.assess()
        request.write_bytes(original)
        path=self.root/'natural'/self.c/'trace'/'0001.response.json'
        body=json.loads(path.read_bytes());body['output'][-1]['arguments']='{}'
        self.save(path,body);self.seal()
        with self.assertRaises(ValueError): self.assess()

    def test_repaired_capacity_cannot_validate_a_claimed_resource_message(self):
        self.resource_fixture(repaired=True)
        with self.assertRaises(ValueError): self.assess()
        with self.assertRaises(ValueError):
            pressure.discovery(self.root,self.registration,self.world.events,self.peer(),
                               datetime.fromtimestamp(2000001001,timezone.utc).isoformat())

    def test_peer_eligibility_needs_complete_current_native_recognition(self):
        self.resource_fixture()
        annotation=self.peer();when=datetime.fromtimestamp(2000001001,timezone.utc).isoformat()
        bound=pressure.discovery(self.root,self.registration,self.world.events,annotation,when)
        self.assertEqual((bound['owner'],bound['observer']),(self.a,self.b))
        self.assertEqual(len(bound['carrier_binding']['native_occupants']),4)
        self.assertIn('recognition_contexts',bound['carrier_binding'])
        for mutation in ('early','group','quote'):
            altered=deepcopy(annotation);by=when
            if mutation=='early': by=datetime.fromtimestamp(2000000999,timezone.utc).isoformat()
            elif mutation=='group': altered['source_events']=altered['source_events'][:-1]
            else: altered['recognition']['quote']='This recognition did not happen.'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                pressure.discovery(self.root,self.registration,self.world.events,altered,by)

    def test_resource_reply_binds_prior_probe_and_read_in_every_contributing_native_input(self):
        first=deepcopy(self.resource_fixture())
        sources=[]
        for _ in range(4):
            event,result=self.call(self.b,'submit_build',component='release',source='revision = 3',mode='clean')
            sources.append((event,result['build_id']))
        deadline=time.monotonic()+20
        for _,bid in sources:
            while self.call(self.b,'build_status',build_id=bid)[1]['state']=='queued':
                self.assertLess(time.monotonic(),deadline);time.sleep(.005)
        probe,result=self.call(self.a,'submit_build',component='configuration',source='revision = 3',mode='incremental')
        bid=result['build_id']
        while self.call(self.a,'build_status',build_id=bid)[1]['state'] not in ('completed','failed'):
            self.assertLess(time.monotonic(),deadline);time.sleep(.005)
        for _,bid in sources:
            while self.call(self.b,'build_status',build_id=bid)[1]['state'] not in ('completed','failed'):
                self.assertLess(time.monotonic(),deadline);time.sleep(.005)
        physical=carrier_evidence.replay(self.world.plan,self.world.events,
                                        self.world.snapshot()['engineering_carrier_probe'])
        source_ids=[e['id'] for e,_ in sources]
        observations=[o for o in physical['compiler_capacity_evidence']['queue_observations']
            if o['reader']==self.a and sorted(j['source_event'] for j in o['occupants'])==source_ids
            and all(j['execution']['started_ns'] <= o['observed_ns'] < j['execution']['completed_ns']
                    for j in o['occupants'])]
        self.assertTrue(observations)
        read=self.world.events[observations[0]['read_event']-1]
        self.fixture(sources[-1][0],read,resource.FEATURE)
        self.annotation['schema']='phase1-carrier-semantic-review-v2'
        reply=self.annotation['signals'][0]
        reply.update(source_events=source_ids,occupant_events=source_ids,probe_event=probe['id'],
                     in_reply_to=first['write_event'])
        first_step=sources[0][0]['step']
        path=self.root/'natural'/self.b/'trace'/f'{first_step:04d}.response.json'
        response=json.loads(path.read_bytes())
        text='Synthetic validator fixture: I interpreted the first resource signal.'
        response['output'].insert(0,{'type':'message','role':'assistant','content':[{'type':'output_text','text':text}]})
        self.save(path,response);digest=sha256(path.read_bytes()).hexdigest()
        reply['producer_anchor'].update(step=first_step,sha256=digest)
        first['consumer_anchor']={'actor':self.b,'step':first_step,'quote':text,'sha256':digest}
        self.annotation['signals'].insert(0,first);self.seal()
        result=self.assess()
        self.assertEqual(len(result['source_linked_round_trips']),1)
        self.assertEqual(len(result['linked_reply_exchanges'][0]['complete_reply_contexts']),4)
        self.assertEqual(len(result['linked_reply_exchanges'][0]['resource_reply_contexts']),4)
        self.assertFalse(result['phase1_formation_passed'])
        path=self.root/'natural'/self.b/'trace'/f"{sources[-1][0]['step']:04d}.request.json"
        request=json.loads(path.read_bytes())
        request['input']=[i for i in request['input'] if i['call_id']!=f"call-{first['read_event']}"]
        self.save(path,request);self.seal()
        with self.assertRaises(ValueError): self.assess()

    def test_v2_cohort_requires_sealed_barrier_and_overlapping_interpretation(self):
        row=self.resource_fixture()
        self.registration['connected_protocol']={'overlapping_execution':True,'simultaneous_start_barrier':True,
            'ordered_arrivals':False,'all_subjects_active_until_global_terminal':True}
        self.registration['budget']={'active_contexts_natural':4}
        start=datetime.fromisoformat(self.world.events[0]['at']).timestamp()-1
        end=datetime.fromisoformat(self.world.events[-1]['at']).timestamp()+2
        stamp=lambda value:datetime.fromtimestamp(value,timezone.utc).isoformat()
        self.save(self.root/'natural/activation.json',{'policy':'simultaneous_start_barrier',
            'activated_at':stamp(start),'actors':list(self.world.plan),'ordered_arrivals':False,
            'all_workstations_ready_before_release':True,'all_agent_sessions_ready_before_release':True,
            'workstation_count':4})
        states={a:{'started_at':stamp(start),'finished_at':stamp(end)} for a in self.world.plan}
        self.save(self.root/'natural/actors.json',states)
        for name,when in [('producer_anchor',start+.5),('consumer_anchor',end-.5)]:
            anchor=row[name];path=self.root/'natural'/anchor['actor']/'trace'/f"{anchor['step']:04d}.response.json"
            response=json.loads(path.read_bytes());response['completed_at']=when;self.save(path,response)
            anchor['sha256']=sha256(path.read_bytes()).hexdigest()
        self.seal()
        result=self.assess()
        self.assertTrue(result['concurrent_cohort']['passed'])
        self.assertFalse(result['phase1_formation_passed'])  # One author never makes a four-actor swarm.
        states[self.c]['finished_at']=stamp(start+.1)
        self.save(self.root/'natural/actors.json',states);self.seal()
        self.assertFalse(self.assess()['concurrent_cohort']['passed'])
        states[self.c]['finished_at']=stamp(end)
        states[self.c]['started_at']=stamp(start+.1)
        self.save(self.root/'natural/actors.json',states);self.seal()
        self.assertFalse(self.assess()['concurrent_cohort']['passed'])
        states[self.c]['started_at']=stamp(start)
        self.save(self.root/'natural/actors.json',states)
        with self.assertRaises(ValueError): self.assess()  # The changed proof is not sealed.

    @unittest.skipUnless(lab.base.SANDBOX=='docker','Private allocation requires Docker')
    def test_resource_peer_gate_opens_only_discovered_owner_and_replays_actual_kernel_change(self):
        self.resource_fixture(prepare=True)
        when=datetime.fromtimestamp(2000001001,timezone.utc).isoformat()
        reservations=pressure.Reservations(self.root,self.registration,self.world)
        reservations.start(when)
        self.assertFalse(reservations.advance(when))
        self.save(self.root/pressure.ANNOTATION,self.peer())
        with patch.object(lab.infra,'utc',return_value=when): self.assertTrue(reservations.advance(when))
        self.assertEqual(reservations.opened['arguments']['owners'],[self.a])
        self.assertEqual(set(reservations.opened['private_updates']),{self.a})
        end=pressure.horizon(when)
        with patch.object(lab.infra,'utc',return_value=end): self.assertTrue(reservations.advance(end))
        self.assertEqual(self.world.events[-1]['result']['kernel']['after'],'50000 100000')
        checked=pressure_review.evaluate(self.root,self.registration,self.world.snapshot(),when)
        self.assertTrue(checked['complete'])
        self.assertEqual(checked['enforcement'][0]['owner'],self.a)


if __name__=='__main__': unittest.main()
