"""Observer-only latency records. Delivery, reads and research adoption are distinct."""
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import time


def text_hash(text):
    return sha256(text.encode()).hexdigest()


class ResearchTiming:
    def __init__(self, root):
        self.path = Path(root) / 'research-latency.jsonl'
        self.queued = {}
        self.commands = set()
        self.sequence = 0

    def event(self, stage, actor=None, **values):
        self.sequence += 1
        row = {'sequence': self.sequence, 'stage': stage, 'actor': actor,
               'monotonic': time.monotonic(), 'at': datetime.now(timezone.utc).isoformat(), **values}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        return row

    def sync_queue(self, publications, actors, active):
        current = set()
        for actor in actors:
            for version in publications.pending(actor, limited=False):
                key = actor, version['path'], version['sha256']
                current.add(key)
                if key not in self.queued:
                    self.queued[key] = self.event('notice_queued', actor, version=version,
                        actor_busy=actor in active, version_timing=publications.version_times[key[1:]])['monotonic']
        for key in self.queued.keys() - current:
            self.event('notice_cancelled', key[0], path=key[1], sha256=key[2],
                       reason='replaced_removed_or_already_observed')
        self.queued = {key: value for key, value in self.queued.items() if key in current}

    def begin_notice(self, actor, text, *, delivery, versions=(), call_id=None, due=None):
        return self.event('notice_attempt', actor, delivery=delivery, versions=list(versions),
            text_sha256=text_hash(text), call_id=call_id, due=due,
            queued=[{'path': v['path'], 'sha256': v['sha256'],
                     'monotonic': self.queued.get((actor, v['path'], v['sha256']))} for v in versions])

    def end_notice(self, attempt, *, success):
        self.event('notice_handoff' if success else 'notice_dispatch_failed', attempt['actor'],
                   attempt=attempt['sequence'])
        if success:
            for v in attempt['versions']:
                self.queued.pop((attempt['actor'], v['path'], v['sha256']), None)

    def tool(self, actor, call, snapshot):
        key = actor, call['call_id']
        if key not in self.commands:
            self.commands.add(key)
            self.event('tool_service', actor, call_id=call['call_id'], turn=call['turn'],
                controller=snapshot.get('controller_tool_timing'),
                workstation=snapshot.get('workstation_service_timing'))


def _distribution(values):
    values = sorted(values)
    if not values:
        return {'samples': 0, 'p50_seconds': None, 'p95_seconds': None, 'max_seconds': None}
    return {'samples': len(values), 'p50_seconds': values[math.ceil(.5 * len(values)) - 1],
            'p95_seconds': values[math.ceil(.95 * len(values)) - 1], 'max_seconds': values[-1]}


def _native_events(root, actor):
    from codex_evidence import mcp_output_text
    events = []
    for path in sorted((root / 'natural' / actor / 'codex/native').glob('*.json')):
        row = json.loads(path.read_text())
        if row.get('direction') != 'server' or not isinstance(row.get('captured_monotonic'), (int, float)):
            continue
        message = row['message'];method = message.get('method');params = message.get('params') or {}
        item = params.get('item') or {}
        if method in ('thread/compacted', 'model/rerouted') or item.get('type') == 'contextCompaction':
            break  # Private compaction is not another research response.
        event = {'monotonic': row['captured_monotonic'], 'record': str(path.relative_to(root))}
        if method == 'rawResponseItem/completed':
            kind = item.get('type')
            if kind == 'message' and item.get('role') == 'user':
                text = '\n'.join(part.get('text', '') for part in item.get('content', []))
                events.append({**event, 'kind': 'input', 'text_sha256': text_hash(text)})
            elif kind == 'function_call_output':
                hashes = []
                try:
                    output = json.loads(mcp_output_text(item['output']))
                    if isinstance(output, dict):
                        hashes = [text_hash(text) for text in output.get('environment_notifications', [])
                                  if isinstance(text, str)]
                except (ValueError, TypeError, AssertionError, KeyError, IndexError):
                    pass
                events.append({**event, 'kind': 'tool_receipt', 'call_id': item.get('call_id'), 'text_hashes': hashes})
            elif kind in ('message', 'reasoning', 'function_call'):
                events.append({**event, 'kind': 'output'})
                if kind == 'function_call' and (item.get('namespace') == 'mcp__work'
                        or item.get('name', '').startswith('mcp__work__')):
                    events.append({**event, 'kind': 'tool_call', 'call_id': item['call_id']})
        elif method in ('item/agentMessage/delta', 'item/reasoning/textDelta', 'item/reasoning/summaryTextDelta') and params.get('delta'):
            events.append({**event, 'kind': 'output'})
    return events


def inventory(root, registration):
    """Join controller stages to timestamped native receipts after sessions close."""
    root = Path(root)
    rows = [json.loads(line) for line in (root / 'research-latency.jsonl').read_text().splitlines()]
    samples = defaultdict(list); per_actor = defaultdict(lambda: defaultdict(list)); anomalies = []

    def measure(name, start, end, actor=None):
        if start is None or end is None:
            return None
        value = end - start
        if value < 0:
            anomalies.append({'metric': name, 'actor': actor, 'start': start, 'end': end})
            return None
        samples[name].append(value)
        if actor is not None: per_actor[actor][name].append(value)
        return value

    for row in rows:
        if row['stage'] == 'publication_stable':
            timing = row['version_timing']
            measure('first_detection_to_stable', timing['first_seen'], timing['stable'])
        elif row['stage'] == 'notice_queued':
            measure('stable_to_queue', row['version_timing']['stable'], row['monotonic'], row['actor'])
        elif row['stage'] == 'scan_finished':
            timing = row['timing']
            measure('scan_lock_wait', timing['started'], timing['lock_acquired'])
            measure('scan_service', timing['lock_acquired'], timing['finished'])
        elif row['stage'] == 'tool_service':
            timing = row.get('controller') or {};station = row.get('workstation') or {};actor = row['actor']
            measure('tool_executor_queue', timing.get('submitted'), timing.get('worker_started'), actor)
            measure('tool_result_queue', timing.get('worker_finished'), timing.get('collector_received'), actor)
            measure('workstation_lock_wait', station.get('lock_requested'), station.get('lock_acquired'), actor)
            measure('workstation_service_including_evidence', station.get('lock_acquired'), station.get('service_finished'), actor)

    receipts = []; handoffs = {r['attempt']: r for r in rows if r['stage'] == 'notice_handoff'}
    native = {a: _native_events(root, a) for a in registration['plan']['natural']}
    for row in (r for r in rows if r['stage'] == 'tool_service'):
        actor = row['actor'];controller = row.get('controller') or {}
        handoff = next((r for r in rows if r['stage'] == 'tool_result_handoff' and r['actor'] == actor
                        and r['call_id'] == row['call_id'] and r['delivered']), None)
        receipt = next((e for e in native[actor] if e['kind'] == 'tool_receipt'
                        and e['call_id'] == row['call_id'].split('|', 1)[0]), None)
        measure('tool_completion_to_native_receipt', controller.get('worker_finished'),
                receipt['monotonic'] if receipt else None, actor)
        measure('tool_received_to_handoff', controller.get('collector_received'),
                handoff['monotonic'] if handoff else None, actor)
    used = set()
    accesses = [r for r in rows if r['stage'] == 'file_access_observed']
    for attempt in (r for r in rows if r['stage'] == 'notice_attempt'):
        actor = attempt['actor']; receipt = None
        for event in native[actor]:
            if event['monotonic'] < attempt['monotonic'] or (actor, event['record']) in used:
                continue
            matches = (event['kind'] == 'tool_receipt' and attempt['delivery'] == 'tool_result'
                and event.get('call_id') == (attempt.get('call_id') or '').split('|', 1)[0]
                and attempt['text_sha256'] in event.get('text_hashes', [])) or (
                event['kind'] == 'input' and attempt['delivery'] != 'tool_result'
                and event.get('text_sha256') == attempt['text_sha256'])
            if matches:
                receipt = event;used.add((actor, event['record']));break
        following = next((e for e in native[actor] if receipt and e['kind'] == 'tool_call'
                          and e['monotonic'] > receipt['monotonic']), None)
        result = {'attempt': attempt['sequence'], 'actor': actor, 'delivery': attempt['delivery'],
                  'controller_handoff': attempt['sequence'] in handoffs, 'native_receipt': receipt,
                  'next_tool_call': following, 'versions': attempt['versions']}
        receipts.append(result)
        for queued in attempt['queued']:
            measure('notification_queue_to_dispatch', queued['monotonic'], attempt['monotonic'], actor)
        measure('continuation_due_to_dispatch', attempt.get('due'), attempt['monotonic'], actor)
        measure('dispatch_to_native_receipt', attempt['monotonic'], receipt['monotonic'] if receipt else None, actor)
        measure('native_receipt_to_next_tool', receipt['monotonic'] if receipt else None,
                following['monotonic'] if following else None, actor)
        for version in attempt['versions']:
            read = next((r for r in accesses if receipt and r['actor'] == actor
                         and r['monotonic'] >= receipt['monotonic'] and r['operation'] in ('read', 'pread64')
                         and all(r[k] == version[k] for k in ('path', 'sha256'))), None)
            measure('native_receipt_to_read_observation', receipt['monotonic'] if receipt else None,
                    read['monotonic'] if read else None, actor)
    for row in (r for r in rows if r['stage'] == 'publication_stable'):
        seen = row['version_timing'].get('scan_observed_unix')
        writes = [r for r in accesses if r['operation'] in ('write', 'pwrite64')
                  and all(r[k] == row[k] for k in ('path', 'sha256')) and seen is not None and r['trace_unix'] <= seen]
        if writes:
            write = max(writes, key=lambda r: r['trace_unix'])
            measure('matching_write_trace_to_first_scan', write['trace_unix'], seen, write['actor'])
    for actor, events in native.items():
        ready = None
        for event in events:
            if event['kind'] in ('input', 'tool_receipt'): ready = event['monotonic']
            elif event['kind'] == 'output' and ready is not None:
                measure('native_input_or_tool_receipt_to_output', ready, event['monotonic'], actor);ready = None
    expected = ('first_detection_to_stable', 'stable_to_queue', 'notification_queue_to_dispatch',
        'dispatch_to_native_receipt', 'native_receipt_to_next_tool', 'native_receipt_to_read_observation',
        'matching_write_trace_to_first_scan', 'scan_lock_wait', 'scan_service', 'tool_executor_queue',
        'tool_result_queue', 'workstation_lock_wait', 'workstation_service_including_evidence',
        'continuation_due_to_dispatch', 'native_input_or_tool_receipt_to_output',
        'tool_completion_to_native_receipt', 'tool_received_to_handoff')
    completion_path = root / 'completion.json'
    completion = json.loads(completion_path.read_text()) if completion_path.exists() else {}
    return {'schema': 'research-latency-v1', 'condition': registration['condition'],
        'completion': {k: completion.get(k) for k in ('reason', 'failure', 'shutdown_errors', 'elapsed_seconds')},
        'policy': registration.get('sustained_research'),
        'clock': 'Host monotonic for controller/native receipt; Docker Unix for matching syscall/scan pairs.',
        'metrics': {k: _distribution(samples[k]) for k in expected},
        'actors': {a: {k: _distribution(v) for k, v in metrics.items()} for a, metrics in per_actor.items()},
        'notice_attempts': receipts, 'unconfirmed_native_receipts': sum(r['native_receipt'] is None for r in receipts),
        'cancelled_pending_versions': sum(r['stage'] == 'notice_cancelled' for r in rows),
        'clock_anomalies': anomalies,
        'limits': ['Temporal next tool call is not adoption or an interaction round.',
            'A matching scalar read receipt is not comprehension; its capture can lag the actual read.',
            'Write latency is available only for matching full-payload scalar writes at the exact path; timestamps are syscall trace times, not certified write completion.',
            'Native readiness-to-output includes transport, context processing and generation; it is not isolated model inference latency.',
            'Missing receipt or follow-up is censored, never a zero-second latency.']}
