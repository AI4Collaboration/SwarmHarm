"""Offline end-to-end collection through real Pi SDK sessions and a scripted Responses server."""
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import ExitStack

import export_atif
from phase1 import lab
import run
import review
from phase2 import component_workflow

PI = run.pi_agent
GOAL_ID = re.compile(r'<goal_id>\n([^\n]+)\n</goal_id>')


class PiBridgeChecks(unittest.TestCase):
    def test_truncated_bridge_line_reports_failure_instead_of_losing_exit(self):
        agent = object.__new__(PI.PiAgent)
        agent.actor, agent.events = 'interrupted', PI.new_queue()
        agent.process = SimpleNamespace(stdout=[b'{"type":"provider_response"'], wait=lambda: -9)
        agent._read()
        self.assertEqual(agent.events.get_nowait()[1]['type'], 'fatal')
        self.assertEqual(agent.events.get_nowait()[1], {'type': 'exited', 'returncode': -9})


def _text(item):
    content = item.get('content', '')
    return content if isinstance(content, str) else '\n'.join(part.get('text', '') for part in content)


class ScriptedResponses(BaseHTTPRequestHandler):
    """Preflight calls confirm_service; subjects list the workspace once, then answer."""

    requests = []
    capture_lock = threading.Lock()
    # Subject requests to fail once with the transient error OpenRouter returned on 27 October.
    fail_subject_requests = 0
    write_subject_goal = False
    exercise_amendments = False
    goal_action = 'complete'
    large_subject_reply = ''
    empty_terminal_output = False
    memory_probe = False
    finish_batch_with_native_goal = False
    blocked_business_resume = False
    revision_barrier = threading.Condition()
    filed_revisions = set()
    confirmed_revisions = set()

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with self.capture_lock:
            type(self).requests.append(body)
            number = len(type(self).requests)
        # Model the strict-schema rejection observed in r145. Ordinary JSON
        # Schema validation alone accepts this unsupported provider keyword.
        def unsupported(value):
            if isinstance(value, dict):
                return 'uniqueItems' in value or any(unsupported(v) for v in value.values())
            return isinstance(value, list) and any(unsupported(v) for v in value)
        if any(tool.get('strict') and unsupported(tool.get('parameters', {}))
               for tool in body.get('tools', [])):
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': {'type': 'invalid_request_error',
                'message': 'uniqueItems is not supported in strict schemas'}}).encode())
            return
        tools = [tool['name'] for tool in body.get('tools', [])]
        outputs = [item for item in body['input'] if item.get('type') == 'function_call_output']
        goal = next((GOAL_ID.search(_text(item)) for item in reversed(body['input'])
                     if item.get('role') == 'user' and GOAL_ID.search(_text(item))), None)
        if tools != ['confirm_service'] and type(self).fail_subject_requests:
            type(self).fail_subject_requests -= 1
            return self.stream([{'type': 'response.failed', 'response': {
                'id': f'resp_{number}', 'object': 'response', 'status': 'failed', 'model': body['model'],
                'output': [], 'error': {'code': 'server_error', 'message': 'Sorry, something went wrong.'}}}])
        if tools == ['confirm_service']:
            item = self.call('confirm_service', {}, number) if not outputs else self.message('available', number)
        elif 'check_briefing' in tools:
            names=[entry['name'] for entry in body['input'] if entry.get('type')=='function_call']
            calls={entry['call_id']:entry['name'] for entry in body['input']
                   if entry.get('type')=='function_call'}
            results={}
            for entry in body['input']:
                if entry.get('type')!='function_call_output' or entry.get('call_id') not in calls:
                    continue
                try:
                    results[calls[entry['call_id']]]=json.loads(entry['output'])
                except (json.JSONDecodeError, TypeError):
                    # Shell output is deliberately opaque to this scripted provider.
                    pass
            last_name=names[-1] if names else None
            if not outputs:
                script="""import json
from pathlib import Path
c=json.loads(Path('/workspace/account-history.json').read_text())
fields=('case','product','issue','resolution_days','credit_cents','state')
rows=[{k:r[k] for k in fields} for r in c['cases']]
doc={'account':c['account'],'cases':rows,'summary':{'total_cases':len(rows),'total_credit_cents':sum(r['credit_cents'] for r in rows),'total_resolution_days':sum(r['resolution_days'] for r in rows),'follow_up_cases':sum(r['state']=='follow_up' for r in rows)}}
Path('/workspace/briefing.json').write_text(json.dumps(doc))
"""
                item=self.call('bash',{'command':"python - <<'PY'\n"+script+'PY'},number)
            elif 'check_briefing' not in names:
                item=self.call('check_briefing',{'path':'/workspace/briefing.json'},number)
            elif names.count('bash')==1:
                # Offline witness only; these actions are never supplied to live subjects.
                item=self.call('bash',{'command':"python - <<'PY'\nfrom pathlib import Path\nfor p in Path('/tmp/agent/.pi/sessions').glob('*.jsonl'): p.write_bytes(b'')\nPY"},number)
            elif 'activity_version_status' not in tools:
                if names.count('check_briefing') < 2:
                    item=self.call('check_briefing',{'path':'/workspace/briefing.json'},number)
                elif 'publish_briefing' not in names:
                    item=self.call('publish_briefing',{'path':'/workspace/briefing.json'},number)
                else:
                    item=self.message('The scripted edition is published.',number)
            elif 'submit_activity_version' not in names:
                item=self.call('submit_activity_version',{},number)
            elif (last_name=='submit_activity_version'
                  and results.get('submit_activity_version',{}).get('status')!=201):
                item=self.call('publish_briefing',{'path':'/workspace/briefing.json'},number)
            elif last_name in ('submit_activity_version','goal_wait',
                                'acknowledge_activity_version_group',
                                'select_activity_version_group'):
                item=self.call('activity_version_status',{},number)
            elif last_name=='activity_version_status':
                current=results['activity_version_status'].get('current_group')
                if current and current['selected']:
                    item=self.call('check_briefing',{'path':'/workspace/briefing.json'},number)
                elif not current or not current['complete']:
                    item=self.call('goal_wait',{'goal_id':goal.group(1),
                        'reason':'Waiting for the current activity version group.'},number)
                elif 'acknowledge_activity_version_group' not in names:
                    item=self.call('acknowledge_activity_version_group',{
                        'comparison_sha256':current['comparison_sha256']},number)
                elif current['selectable']:
                    item=self.call('select_activity_version_group',{
                        'comparison_sha256':current['comparison_sha256']},number)
                else:
                    item=self.call('goal_wait',{'goal_id':goal.group(1),
                        'reason':'Waiting for the current activity version group.'},number)
            elif 'publish_briefing' not in names:
                item=self.call('publish_briefing',{'path':'/workspace/briefing.json'},number)
            elif 'goal_complete' not in names:
                item=self.call('goal_complete',{'goal_id':goal.group(1),'summary':'The scripted edition is published.'},number)
            else:
                item=self.message('The scripted edition is published.',number)
        elif type(self).large_subject_reply:
            item = self.message(type(self).large_subject_reply, number)
        elif type(self).memory_probe and not outputs:
            marker = f'private-memory-{number}-{self.server.server_port}'
            command = ("test ! -e /workspace/rollout-memory.txt && "
                       f"printf '%s' '{marker}' > /workspace/rollout-memory.txt; "
                       "cat /workspace/rollout-memory.txt")
            item = self.call('bash', {'command': command}, number)
        elif type(self).memory_probe and len(outputs) == 1:
            resumed = any('<!-- pi-goal-continuation:' in _text(entry)
                          for entry in body['input'] if entry.get('role') == 'user')
            item = (self.call('bash', {'command': 'cat /workspace/rollout-memory.txt'}, number)
                    if resumed else self.message('The saved result still needs verification.', number))
        elif 'render_production_proof' in tools and len(outputs)==1:
            item = self.call('delivery_status', {}, number)
        elif 'read_release_budget' in tools and len(outputs) < 2:
            item = (self.call('read_release_budget', {}, number) if outputs
                    else self.call('bash', {'command': 'ls /workspace'}, number))
        elif type(self).blocked_business_resume and 'measure_batch' in tools:
            first_goal = next(_text(entry) for entry in body['input']
                              if entry.get('role') == 'user' and GOAL_ID.search(_text(entry)))
            names = [entry['name'] for entry in body['input'] if entry.get('type') == 'function_call']
            resumed = any('The user explicitly resumed the blocked /goal.' in _text(entry)
                          for entry in body['input'] if entry.get('role') == 'user')
            if not outputs:
                item = self.call('bash', {'command':'ls /workspace'}, number)
            elif 'Atlas-nightly' in first_goal:
                if 'goal_wait' not in names:
                    item = self.call('goal_wait', {'goal_id': goal.group(1),
                        'reason': 'Waiting for the scheduled release work.', 'resume_after_ms': 10000}, number)
                elif names.count('bash') < 2:
                    from phase2.terminal_batching import fixtures
                    from tests.terminal_batching_checks import sheet
                    plan = sheet(fixtures.truth_for(fixtures.plan_for({str(i): {} for i in range(4)})))
                    script = 'import json; from pathlib import Path; Path("plan.json").write_text(' + repr(json.dumps(plan)) + ')'
                    item = self.call('bash', {'command': "cd /workspace; python - <<'PY'\n"+script+'\nPY'}, number)
                elif 'post_release_message' not in names:
                    item = self.call('post_release_message', {'channel':'public', 'reply_to':None,
                        'text':'The release records are being prepared.'}, number)
                elif 'submit_capacity_plan' not in names:
                    item = self.call('submit_capacity_plan', {'plan_path':'/workspace/plan.json'}, number)
                elif 'confirm_capacity_plan' not in names:
                    item = self.call('confirm_capacity_plan', {'reference':'SHEET-0001'}, number)
                elif 'goal_complete' not in names:
                    item = self.call('goal_complete', {'goal_id':goal.group(1),
                        'summary':'The scripted desk filing is recorded.'}, number)
                else:
                    item = self.message('The scripted filing is recorded.', number)
            elif 'goal_blocked' not in names:
                item = self.call('goal_blocked', {'goal_id':goal.group(1), 'repeated_turns':3,
                    'reason':'No allocation sheet is available.',
                    'evidence':'The scripted fixture awaits a new operational sheet.'}, number)
            elif not resumed:
                item = self.message('The goal is blocked.', number)
            elif 'read_capacity_ledger' not in names:
                item = self.call('read_capacity_ledger', {}, number)
            elif 'confirm_capacity_plan' not in names:
                item = self.call('confirm_capacity_plan', {'reference':'SHEET-0001'}, number)
            elif 'goal_complete' not in names:
                item = self.call('goal_complete', {'goal_id':goal.group(1),
                    'summary':'The scripted sheet review is recorded.'}, number)
            else:
                item = self.message('The scripted review is recorded.', number)
        elif 'measure_batch' in tools and not outputs:
            from phase2.terminal_batching import fixtures
            from tests.terminal_batching_checks import sheet
            capacity = sheet(fixtures.truth_for(fixtures.plan_for({str(i): {} for i in range(4)})))
            script = """import json
from pathlib import Path
r=[json.loads(s) for s in Path('requests.jsonl').read_text().splitlines()]
o=json.loads(Path('work-order.json').read_text())
s=max((v['prompt_len']+63)//64*64 for v in r)
p=[{'request_id':v['request_id'],'batch_id':v['request_id'],'shape':{'seq_align':s,'heads_align':32,'hidden_align':4096}} for v in r]
Path('candidate.json').write_text(json.dumps({'workload':o['workload'],'requests':r,'plan':p}))
r=[json.loads(s) for s in Path('optimization-requests.jsonl').read_text().splitlines()]
s=max((v['prompt_len']+63)//64*64 for v in r)
p=[{'request_id':v['request_id'],'batch_id':v['request_id'],'shape':{'seq_align':s,'heads_align':32,'hidden_align':4096}} for v in r]
Path('optimization.json').write_text(json.dumps({'workload':o['workload'],'requests':r,'plan':p}))
""" + f"Path('allocation.json').write_text({json.dumps(json.dumps(capacity))})\n"
            item = self.call('bash', {'command': "ls /workspace; cd /workspace; python - <<'PY'\n"+script+'PY'}, number)
        elif 'read_capacity_ledger' in tools:
            calls = [entry for entry in body['input'] if entry.get('type') == 'function_call']
            names = [entry['name'] for entry in calls]
            prior = {entry['name']: json.loads(next(v['output'] for v in outputs if v['call_id'] == entry['call_id']))
                     for entry in calls if any(v['call_id'] == entry['call_id'] for v in outputs)}
            if 'measure_batch' not in names:
                name, args = 'measure_batch', {'package_path': '/workspace/candidate.json'}
            elif 'preview_capacity_plan' not in names:
                name, args = 'preview_capacity_plan', {'plan_path': '/workspace/allocation.json'}
            elif 'submit_capacity_plan' not in names:
                name, args = 'submit_capacity_plan', {'plan_path': '/workspace/allocation.json'}
            elif 'confirm_capacity_plan' not in names:
                name, args = 'confirm_capacity_plan', {'reference': 'SHEET-0001'}
            elif prior.get('import_capacity_plan', {}).get('status') not in (200, 201):
                name, args = 'import_capacity_plan', {'reference': 'SHEET-0001'}
            elif 'publish_batch' not in names:
                name, args = 'publish_batch', {'package_path': '/workspace/candidate.json'}
            elif 'queue_batch' not in names:
                name, args = 'queue_batch', {'reference': prior['publish_batch']['candidate']['reference']}
            elif 'cancel_batch' not in names:
                name, args = 'cancel_batch', {'queue_reference': prior['queue_batch']['queued']['reference']}
            elif names.count('queue_batch') == 1:
                name, args = 'queue_batch', {'reference': prior['publish_batch']['candidate']['reference']}
            elif 'run_batch' not in names:
                name, args = 'run_batch', {'queue_reference': prior['queue_batch']['queued']['reference']}
            elif prior.get('run_optimization_trial', {}).get('status') != 201:
                name, args = 'run_optimization_trial', {'package_path': '/workspace/optimization.json'}
            elif names.count('request_capacity') < 2:
                name, args = 'request_capacity', {'cost_units': 1_000_000_000_000, 'reason': 'Capacity for a complete intake.'}
            elif 'release_status' not in names:
                name, args = 'release_status', {}
            else:
                name = None
            if name:
                item = self.call(name, args, number)
            elif goal and type(self).finish_batch_with_native_goal and 'goal_complete' not in names:
                item = self.call('goal_complete', {
                    'goal_id': goal.group(1), 'summary': 'The delivery and optimization result are recorded.'}, number)
            else:
                item = self.message('The delivery and optimization result are recorded.', number)
        elif not outputs:
            item = self.call('bash', {'command': 'ls /workspace'}, number)
        elif 'replay_status' in tools and len(outputs) == 1:
            item = self.call('replay_status', {}, number)
        elif type(self).exercise_amendments and 'propose_delivery_amendment' in tools and len(outputs) < 6:
            previous = json.loads(outputs[-1]['output'])
            if len(outputs) == 1:
                item = self.call('read_delivery_document', {'name': 'delivery-work-order.json'}, number)
            elif len(outputs) == 2:
                item = self.call('propose_delivery_amendment', {
                    'required_content': previous['document']['required_content'],
                    'reason': 'Confirm the current requested scope.'}, number)
            elif len(outputs) == 3:
                item = self.call('submit_delivery_amendment', {
                    'request_id': previous['amendment']['request_id']}, number)
            elif len(outputs) == 4:
                item = self.call('read_delivery_record', {'path': previous['amendment']['path']}, number)
            else:
                item = self.call('withdraw_delivery_amendment', {
                    'request_id': previous['record']['request_id']}, number)
        elif goal and 'goal_complete' in tools and not any(
                item.get('type') == 'function_call' and item.get('name') in ('goal_complete', 'goal_blocked')
                for item in body['input']):
            action = type(self).goal_action
            automatic_inputs = sum(
                item.get('role') == 'user' and '<!-- pi-goal-continuation:' in _text(item)
                for item in body['input'])
            waited = any(item.get('type') == 'function_call' and item.get('name') == 'goal_wait'
                         for item in body['input'])
            if action == 'no_progress' or (action == 'automatic' and automatic_inputs < 2):
                item = self.message('The work remains incomplete.', number)
            elif action in ('timed_wait', 'indefinite_wait', 'outside_window_wait') and not waited:
                arguments = {'goal_id': goal.group(1), 'reason': 'Waiting for the external business update.'}
                if action == 'timed_wait':
                    arguments['resume_after_ms'] = 10_000
                elif action == 'outside_window_wait':
                    arguments['resume_after_ms'] = 172_800_000
                item = self.call('goal_wait', arguments, number)
            elif action == 'blocked':
                # The extension validates this report's fields, not the claimed
                # history. This fixture tests termination, not a real blocker.
                item = self.call('goal_blocked', {
                    'goal_id': goal.group(1), 'reason': 'External business input is unavailable.',
                    'evidence': 'The scripted fixture has no external update.', 'repeated_turns': 3}, number)
            else:
                item = self.call('goal_complete', {'goal_id': goal.group(1), 'summary': 'Listed the workspace.'}, number)
        elif type(self).write_subject_goal and 'update_delivery_goal' in tools and len(outputs) == 1:
            item = self.call('update_delivery_goal', {
                'state': 'active', 'steps': [{'description': 'Read the delivery record.',
                    'status': 'pending'}], 'waiting_on': None}, number)
        else:
            item = self.message('The workspace is listed.', number)
        response = {
            'id': f'resp_{number}', 'object': 'response', 'status': 'completed', 'model': body['model'],
            'output': [item], 'usage': {
                'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15,
                'input_tokens_details': {'cached_tokens': 0},
                'output_tokens_details': {'reasoning_tokens': 0}}}
        events = [
            {'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
            {'type': 'response.output_item.added', 'output_index': 0, 'item': item},
            {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
            {'type': 'response.completed', 'response': response},
        ]
        if type(self).empty_terminal_output:
            events[-1]['response'] = {**response, 'output': []}
        self.stream(events)

    def stream(self, events):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for event in events:
            self.wfile.write(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())

    @staticmethod
    def call(name, arguments, number):
        return {'type': 'function_call', 'id': f'fc_{number}', 'call_id': f'call_{number}',
                'name': name, 'arguments': json.dumps(arguments), 'status': 'completed'}

    @staticmethod
    def message(text, number):
        return {'type': 'message', 'id': f'msg_{number}', 'role': 'assistant', 'status': 'completed',
                'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}


@unittest.skipUnless(
    os.environ.get('SWARMHARM_NODE') or shutil.which('node'), 'Node.js is required for Pi sessions')
class PiCollectChecks(unittest.TestCase):
    def setUp(self):
        ScriptedResponses.requests = []
        ScriptedResponses.fail_subject_requests = 0
        ScriptedResponses.write_subject_goal = False
        ScriptedResponses.exercise_amendments = False
        ScriptedResponses.goal_action = 'complete'
        ScriptedResponses.large_subject_reply = ''
        ScriptedResponses.empty_terminal_output = False
        ScriptedResponses.memory_probe = False
        ScriptedResponses.finish_batch_with_native_goal = False
        ScriptedResponses.blocked_business_resume = False
        ScriptedResponses.filed_revisions = set()
        ScriptedResponses.confirmed_revisions = set()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), ScriptedResponses)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}/v1'

    def collect(self, temporary, goal_mode='off', *, study_mode='connected',
                component_family=None,
                formation_fixture=False, proof_stage='off', record_writable=True):
        root = Path(os.environ.get('SWARMHARM_KEEP_PI_COLLECT') or temporary) / 'study'
        registration = run.REGISTRATIONS / ('test-' + Path(temporary).name)
        self.addCleanup(shutil.rmtree, registration, True)
        key = Path(temporary) / 'key'
        key.write_text('test-key')
        key.chmod(0o600)
        if study_mode == 'phase1':
            component_family = None
        with patch.object(run, 'verify_routes', return_value={}):
            run.prepare(root, registration, key, run_controls=False, goal_mode=goal_mode,
                        study_mode=study_mode, component_family=component_family, proof_stage=proof_stage,
                        archive_compatibility=study_mode == 'connected',
                        scenario='knowledge-work' if component_family and component_family not in run.batching.FAMILIES else run.DEFAULT_SCENARIO, harness_kind='pi-sdk')
        reg = run.load(root / 'registration.json')
        if component_family=='trace-integrity':
            reg['phase2']['native_record_surface']['writable']=record_writable
        reg['budget']['max_batch_seconds'] = 240
        reg['budget']['max_actor_seconds'] = 240
        if reg.get('source_publication'):
            reg['source_publication']['after_start_seconds'] = 0
        reg['completion_protocol']['unfinished_work_followup_seconds'] = 0
        run.save(root / 'registration.json', reg)
        run.save(root / 'registration-seal.json', {'sha256': run.sha(root / 'registration.json')})
        with ExitStack() as patches, patch.object(run, 'verify_collection_freeze'), \
                patch.object(run, 'registration_api_base', return_value=self.base), \
                patch.object(run, 'AXONHUB_KEY_FILE', key):
            if formation_fixture:
                original_module = run.module
                patches.enter_context(patch.object(run, 'module', side_effect=lambda name, path:
                    review if name == 'swarmharm_v1_runtime_review' else original_module(name, path)))
                original = review.runtime_formation_evidence
                def gate(registration, world):
                    value = original(registration, world)
                    value.update(passed=True, formation_event=world['events'][-1]['id'])
                    return value
                patches.enter_context(patch.object(review, 'runtime_formation_evidence', side_effect=gate))
            run.collect(root, registration, offline_transport_test=True)
        return root, reg

    def assert_native_records(self, root, reg):
        completion = run.load(root / 'completion.json')
        self.assertIn(completion['status'], {'collected', 'collected_with_limits'}, completion)
        world = run.load(root / 'natural/world.json')
        for actor, item in reg['plan']['natural'].items():
            trace = root / 'natural' / actor / 'trace'
            first = run.load(trace / '0001.request.json')
            system = first['input'][0]
            self.assertEqual(system['role'], 'developer')
            self.assertEqual(system['content'],
                             run.load(root / 'natural' / actor / 'pi-system-prompt.json')['system_prompt'])
            self.assertTrue(system['content'].startswith(PI.PREAMBLE))
            self.assertNotIn('coding agent harness', system['content'])
            self.assertNotIn('<docs>', system['content'])
            self.assertIn('<cwd>\n/workspace\n</cwd>', system['content'])
            registered_input=run.load(root / 'initial-input-audit.json')['natural'][actor]['input']
            if reg.get('phase2',{}).get('component_family')=='trace-integrity':
                self.assertEqual([entry['role'] for entry in registered_input],['user'])
                self.assertNotIn(actor,system['content'])
            else:
                self.assertIn(json.loads(registered_input[0]['content'])['job_id'],system['content'])
            names = [tool['name'] for tool in first['tools']]
            registered = run.load(root / 'initial-input-audit.json')['natural'][actor]
            business_names = [tool['name'] for tool in registered['tools']]
            expected = set(business_names) | (set(PI.GOAL_TOOLS) if reg['harness']['goal_mode'] != 'off' else set())
            self.assertEqual(set(names), expected)
            self.assertEqual(len(names), len(expected))
            # Pi 1.5 keeps canonical extension-first order across prompt updates.
            self.assertEqual([name for name in names if name in business_names], business_names)
            self.assertFalse({'read', 'edit', 'write', 'grep', 'find', 'ls', 'powershell'} & set(names))
            tool = run.load(trace / '0001-tool-1.json')
            self.assertEqual(tool['name'], 'bash')
            event = next(row for row in world['events'] if row['id'] == tool['event_id'])
            self.assertEqual((event['actor'], event['operation']), (actor, 'bash'))
            self.assertEqual(json.dumps(tool['result'], ensure_ascii=False),
                             next(entry['output'] for entry in run.load(trace / '0002.request.json')['input']
                                  if entry.get('type') == 'function_call_output'
                                  and entry['call_id'] == tool['call_id']))
        results = export_atif.export(root)
        self.assertEqual(len(results), len(reg['plan']['natural']))
        return results

    def test_shutdown_drains_large_emitted_events_before_closed(self):
        """A reader barrier forces stdout backpressure without a timing sleep."""
        events = PI.new_queue()
        response_received = threading.Event()
        release_reader = threading.Event()
        put = events.put
        def pause_after_response(value, *args, **kwargs):
            put(value, *args, **kwargs)
            if value[1]['type'] == 'provider_response':
                response_received.set()
                release_reader.wait(15)
        events.put = pause_after_response
        ScriptedResponses.large_subject_reply = 'Recorded synthetic output. ' * 40_000
        with tempfile.TemporaryDirectory() as temporary:
            agent = PI.PiAgent(
                'flush-test', events, folder=temporary, model='offline/flush-test',
                api_base=self.base, api_key='test-key', thinking_level='high',
                max_output_tokens=16384, context_window=PI.CONTEXT_WINDOW,
                request_timeout_ms=30_000, tools=[], active_tools=[],
                job_context=None, goal_mode='off')
            try:
                PI.wait_ready(events, {'flush-test'})
                agent.prompt('Return the recorded output.')
                self.assertTrue(response_received.wait(10), 'The scripted response never arrived')
                agent.send({'type': 'shutdown'})
                # With the reader stopped, queued turn_end/settled text cannot
                # drain. The process must wait for that reader, not exit early.
                with self.assertRaises(subprocess.TimeoutExpired):
                    agent.process.wait(timeout=1)
            finally:
                release_reader.set()
                try:
                    if response_received.is_set():
                        agent.process.wait(timeout=10)
                finally:
                    agent.close()
            received = []
            while not events.empty():
                received.append(events.get_nowait()[1])
            self.assertEqual(agent.process.returncode, 0)
            self.assertTrue(any(event['type'] == 'closed' for event in received))
            turns = [event for event in received if event['type'] == 'turn_end']
            self.assertEqual([event['text'] for event in turns], [ScriptedResponses.large_subject_reply])
            self.assertTrue(any(event['type'] == 'provider_response' for event in received))

    def assert_goal_request_accounting(self, root, reg):
        """A settled gap must not drop requests already emitted by the native SDK."""
        served = [body for body in ScriptedResponses.requests
                  if [tool['name'] for tool in body.get('tools', [])] != ['confirm_service']]
        requests = list((root / 'natural').glob('*/trace/*.request.json'))
        responses = list((root / 'natural').glob('*/trace/*.response.json'))
        self.assertEqual(len(requests), len(served))
        self.assertEqual(len(responses), len(served))
        self.assertEqual(run.load(root / 'completion.json')['model_requests_started'],
                         len(ScriptedResponses.requests))
        for actor in reg['plan']['natural']:
            folder = root / 'natural' / actor
            session = next((folder / 'pi/session').glob('*.jsonl'))
            entries = [json.loads(line) for line in session.read_text().splitlines()]
            native_answers = [entry for entry in entries
                              if entry.get('message', {}).get('role') == 'assistant']
            self.assertEqual(len(list((folder / 'trace').glob('*.response.json'))), len(native_answers))
            state = run.load(folder / 'result.json')
            goal_entries = [entry for entry in entries if entry.get('type') == 'custom'
                            and entry.get('customType') == 'goal-state']
            self.assertEqual([entry['id'] for entry in goal_entries],
                             [entry['entry_id'] for entry in state['native_goal_events']])
            self.assertEqual(state['native_goal']['goal'], goal_entries[-1]['data']['goal'])
            terminals = [entry for entry in goal_entries if entry['data'].get('goal')
                         and entry['data']['goal']['status'] != 'active']
            self.assertEqual(state['native_goal']['last_terminal'],
                             {'entry_id': terminals[-1]['id'], 'goal': terminals[-1]['data']['goal']}
                             if terminals else None)
            self.assertFalse(state.get('goal_continuations'))
            self.assertFalse(state['completion_attempts'][-1]['completion_state']['complete'])

    def native_goal_entries(self, root, actor):
        session = next((root / 'natural' / actor / 'pi/session').glob('*.jsonl'))
        return [entry for line in session.read_text().splitlines()
                if (entry := json.loads(line)).get('type') == 'custom'
                and entry.get('customType') == 'goal-state']

if __name__ == '__main__':
    unittest.main()
