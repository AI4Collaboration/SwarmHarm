"""Observed resource limits, time inventories and explicit continuation policies."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
import time

from swarmform.collection import Collection, save, utc
from swarmform.publication_updates import PublicationUpdates, policy, scan_publications, validate_policy
from swarmform import sustained_research as research


class StructureCollection(Collection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.usage = {}
        self.budget_stop = None
        self.last_space_check = 0
        try:
            self.sustained_research = research.validate_policy(self.reg)
            self.responsive_research = research.responsive(self.reg)
            self.publications = (PublicationUpdates(self.actors, self.reg['condition'], timed=self.responsive_research)
                                 if validate_policy(self.reg) else None)
        except Exception:
            self.pool.shutdown()
            raise
        self.publication_pool = None
        self.publication_scan = None
        self.publication_station = None
        self.publication_lock = None
        self.next_publication_scan = 0
        self.publication_scan_count = 0
        self.idle_since = None
        self.research_status = {a: research.ResearchStatus() for a in self.actors}
        self.research_due = {}
        self.publication_observer = None
        self.publication_scan_hint = False
        self.last_publication_scan_finished = 0
        self.dispatch_cursors = {}
        self.latency = None
        if self.responsive_research:
            from swarmform.research_timing import ResearchTiming
            self.latency = ResearchTiming(self.root)

    def start_continuation(self, deployment):
        if self.publications is None:
            return
        # This policy is restricted to the common, same-UID content volume.
        # One nonprivileged scan has the same file visibility for all members.
        bindings = list(deployment.bindings.values())
        if (len({b['volume'] for b in bindings}) != 1
                or len({b['user'] for b in bindings}) != 1
                or any(b['access_profile'] != 'content' for b in bindings)):
            raise ValueError('Publication continuation requires identical shared-file visibility')
        self.publication_station = deployment.stations[self.actors[0]]
        self.publication_lock = deployment.locks[self.actors[0]]
        if self.responsive_research:
            from swarmform.publication_observer import PublicationObserver
            self.publication_observer = PublicationObserver(bindings[0])
            save(self.root/'publication-observer.json', self.publication_observer.binding)
            self.latency.event('lifecycle_started', policy=self.reg['sustained_research'],
                               publication_policy=self.reg['publication_updates'])
        self.publication_pool = ThreadPoolExecutor(max_workers=1)
        save(self.root/'publication-continuation.json', {
            'policy': self.reg['publication_updates'], 'source': 'automatic_environment_file_change',
            'condition': self.reg['condition'],
            'scope': 'File availability notices, not peer authorship, content receipt, comprehension or adoption.'})
        for state in self.states.values():
            state.update(session_activations=1, publication_notices=0)
            if self.sustained_research:
                state.update(research_continuations=0, research_state={'state': 'working'})
        if self.sustained_research:
            save(self.root/'research-lifecycle.json', {'policy': self.reg['sustained_research'],
                'activated_at_monotonic': self.activated_at, 'deadline_monotonic': self.deadline,
                'scope': 'Imposed research commitment; no required messages, roles or semantic progress gate.'})

    def observe_tool_result(self, actor, result, snapshot):
        if self.publications is not None and (reference := snapshot.get('command_observation')):
            accesses = self.publications.accessed(actor, reference)
            if self.latency:
                for access in accesses:
                    self.latency.event('file_access_observed', actor, **access)
        if self.responsive_research:
            self.hint_publication_scan()
        if self.sustained_research and self.research_status[actor].observe(snapshot):
            status = self.research_status[actor]
            self.states[actor]['research_state'] = dict(status.value)
            self.record(actor, {'type': 'research_status_request', 'at': utc(),
                'private_status': status.value, 'invalid': status.error})

    def observe_tool_timing(self, actor, call, snapshot):
        if self.latency:
            self.latency.tool(actor, call, snapshot)

    def dispatch_order(self, route):
        if not self.responsive_research:
            return self.actors
        start = self.dispatch_cursors.get(route, 0)
        self.dispatch_cursors[route] = (start + 1) % len(self.actors)
        return self.actors[start:] + self.actors[:start]

    def hint_publication_scan(self):
        # A completed command is only a scheduling hint. Only scanned, stable
        # content can produce a notice; at most one scan is in flight.
        self.publication_scan_hint = True
        if self.publication_scan is None:
            self.next_publication_scan = max(self.last_publication_scan_finished +
                self.reg['publication_updates']['stable_confirmation_seconds'],
                min(self.next_publication_scan, time.monotonic()))

    def consume_publication_scan(self):
        if self.publication_scan is not None and self.publication_scan.done():
            scan = self.publication_scan.result()
            self.publication_scan = None
            self.retain_publication_scan(scan)
            delay = self.reg['publication_updates']['poll_seconds']
            if self.responsive_research and (not self.publications.ready or self.publication_scan_hint):
                delay = self.reg['publication_updates']['stable_confirmation_seconds']
            self.publication_scan_hint = False
            self.next_publication_scan = time.monotonic() + delay

    def finish_tool(self, actor, message, result, *, delivered):
        versions = []
        if delivered and self.sustained_research and time.monotonic() < self.deadline:
            # Deliver only already-observed real versions; never delay the tool
            # for a scan or interrupt/restart the active model response.
            self.consume_publication_scan()
            if self.latency:
                self.latency.sync_queue(self.publications, self.actors, self.active)
            versions = self.publications.pending(actor)
        if versions:
            notice = {'type': 'publication_notice', 'at': utc(), 'source': 'automatic_environment_file_change',
                'delivery': 'tool_result', 'call_id': message['call_id'], 'versions': versions,
                'text': self.publications.notice(versions), 'same_native_session': True}
            # Preserve raw shell streams/status and distinguish environmental
            # metadata in both the exact native result and the observer record.
            result = {**result, 'environment_notifications': [notice['text']]}
        attempt = (self.latency.begin_notice(actor, notice['text'], delivery='tool_result',
                   versions=versions, call_id=message['call_id']) if versions and self.latency else None)
        try:
            super().finish_tool(actor, message, result, delivered=delivered)
        except BaseException:
            if attempt: self.latency.end_notice(attempt, success=False)
            raise
        if self.latency:
            self.latency.event('tool_result_handoff', actor, call_id=message['call_id'], delivered=delivered)
            if attempt: self.latency.end_notice(attempt, success=True)
        if versions:
            # Failed native delivery leaves the versions pending.
            self.publications.acknowledge(actor, versions)
            self.research_status[actor].wake()
            state = self.states[actor]
            state['research_state'] = {'state': 'working'}
            state['publication_notices'] += 1
            state['notices'].append(notice)
            self.record(actor, notice)
            save(self.root/'natural'/actor/'notices.json', state['notices'])

    def may_continue(self):
        if not self.sustained_research:
            return True
        if time.monotonic() >= self.deadline:
            return False
        # Usage and calls accumulate across every activation in the same session.
        for actor, state in self.states.items():
            for field, limit in (('tools', 'max_tools_per_agent'),
                                 ('observed_model_responses', 'max_responses_per_agent'),
                                 ('observed_tokens', 'max_observed_tokens_per_agent')):
                if state.get(field, 0) >= self.reg['budget'][limit]:
                    self.stop_for_budget(actor, field, state[field])
        return True

    def resume_research(self):
        if not self.sustained_research:
            return
        for actor in self.dispatch_order('research'):
            if (actor in self.active or actor not in self.research_due
                    or time.monotonic() < self.research_due[actor]
                    or self.research_status[actor].value['state'] != 'working'):
                continue
            if not self.may_continue():
                return
            text = research.CONTINUATION + (research.STATUS_ERROR if self.research_status[actor].error else '')
            attempt = (self.latency.begin_notice(actor, text, delivery='research_continuation',
                       due=self.research_due[actor]) if self.latency else None)
            try:
                self.agents[actor].prompt(text)
            except BaseException:
                if attempt: self.latency.end_notice(attempt, success=False)
                raise
            if attempt: self.latency.end_notice(attempt, success=True)
            self.research_due.pop(actor, None)
            self.research_status[actor].wake()
            self.active.add(actor)
            state = self.states[actor]
            state.update(status='running', research_state={'state': 'working'},
                session_activations=state['session_activations']+1,
                research_continuations=state['research_continuations']+1)
            notice = {'type': 'research_continuation', 'at': utc(), 'source': 'registered_research_period',
                      'text': text, 'same_native_session': True}
            state['notices'].append(notice)
            self.record(actor, notice)
            save(self.root/'natural'/actor/'notices.json', state['notices'])

    def read_publications(self):
        # Do not let the station's command snapshot freeze an observer process
        # or present that observer as concurrent participant-authored work.
        started = time.monotonic()
        if self.publication_observer is not None:
            acquired = time.monotonic()
            result = self.publication_observer.scan()
        else:
            with self.publication_lock:
                acquired = time.monotonic()
                result = scan_publications(self.publication_station)
        result['observer_timing'] = {'started': started, 'lock_acquired': acquired, 'finished': time.monotonic()}
        return result

    def retain_publication_scan(self, scan):
        self.publication_scan_count += 1
        before = dict(self.publications.candidate)
        changes = self.publications.observe(scan)
        self.last_publication_scan_finished = (scan.get('observer_timing') or {}).get('finished', time.monotonic())
        if self.latency:
            if 'observer_timing' in scan:
                self.latency.event('scan_finished', scan=self.publication_scan_count,
                                   stable_read=scan['stable'], timing=scan['observer_timing'])
            for item in changes:
                self.latency.event('publication_stable', path=item['path'], sha256=item['sha256'],
                    version_timing=self.publications.version_times[item['path'], item['sha256']])
            if not self.stopping.is_set():
                self.latency.sync_queue(self.publications, self.actors, self.active)
        if not scan['stable'] or before != self.publications.candidate:
            self.idle_since = None
        folder = self.root/'publication-updates'
        blobs = folder/'blobs'
        blobs.mkdir(parents=True, exist_ok=True)
        versions = []
        for item in changes:
            raw = item.pop('data')
            blob = blobs/item['sha256']
            if not blob.exists():
                blob.write_bytes(raw)
            elif sha256(blob.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('Publication archive blob changed')
            versions.append({**item, 'blob': str(blob.relative_to(self.root))})
        save(folder/f'scan-{self.publication_scan_count:06d}.json', {
            'at': utc(), 'stable_read': scan['stable'], 'ready': self.publications.ready,
            'observed_files': self.publications.candidate, 'new_stable_versions': versions,
            'observer_timing': scan.get('observer_timing'), 'observed_unix': scan.get('observed_unix'),
            'source': 'nonprivileged_publication_scan', 'writer': 'not_inferred'})

    def poll_publications(self):
        if self.publication_pool is None:
            return
        now = time.monotonic()
        if self.active or self.jobs:
            self.idle_since = None
        self.consume_publication_scan()
        if self.latency:
            self.latency.sync_queue(self.publications, self.actors, self.active)
        for actor in self.dispatch_order('publication'):
            if actor in self.active:
                continue
            versions = self.publications.pending(actor)
            if not versions:
                continue
            if not self.may_continue():
                return
            text = self.publications.notice(versions)
            notice = {'type': 'publication_notice', 'at': utc(), 'source': 'automatic_environment_file_change',
                      'versions': versions, 'text': text, 'same_native_session': True,
                      'delivery': 'idle_session_prompt'}
            # Only acknowledge after dispatch succeeds; do not lose a pending update.
            attempt = (self.latency.begin_notice(actor, text, delivery='idle_session_prompt', versions=versions)
                       if self.latency else None)
            try:
                self.agents[actor].prompt(text)
            except BaseException:
                if attempt: self.latency.end_notice(attempt, success=False)
                raise
            if attempt: self.latency.end_notice(attempt, success=True)
            self.publications.acknowledge(actor, versions)
            self.active.add(actor)
            if self.sustained_research:
                self.research_status[actor].wake()
                self.research_due.pop(actor, None)
            state = self.states[actor]
            state.update(status='running', session_activations=state['session_activations']+1,
                         publication_notices=state['publication_notices']+1)
            if self.sustained_research:
                state['research_state'] = {'state': 'working'}
            state['notices'].append(notice)
            self.record(actor, notice)
            save(self.root/'natural'/actor/'notices.json', state['notices'])
            self.idle_since = None
        if self.publication_scan is None and now >= self.next_publication_scan:
            self.publication_scan_hint = False
            self.publication_scan = self.publication_pool.submit(self.read_publications)
            if self.responsive_research:
                self.publication_scan.add_done_callback(lambda done: self.events.put((None, {'type': 'publication_scan_ready'})))
            self.next_publication_scan = now + self.reg['publication_updates']['poll_seconds']

    def quiescence_ready(self):
        if self.sustained_research:
            return False
        if self.publications is None:
            return True
        now = time.monotonic()
        if self.idle_since is None:
            self.idle_since = now
        return (now-self.idle_since >= policy()['quiescence_seconds']
                and self.publication_scan is None and self.publications.ready
                and not any(self.publications.pending(a) for a in self.actors))

    def deadline_reason(self):
        if (self.sustained_research and
                time.monotonic() >= self.activated_at+self.reg['budget']['max_agent_seconds']):
            return 'research_window_elapsed'
        return super().deadline_reason()

    def close_continuation(self):
        try:
            self.close_publications()
        finally:
            if self.publication_observer is not None:
                try:
                    self.publication_observer.close()
                except BaseException as error:
                    self.shutdown_failure('PublicationObserverShutdown', error)

    def close_publications(self):
        if self.publication_pool is not None:
            self.publication_pool.shutdown(wait=True)
            if self.publication_scan is not None:
                # A failed last scan remains a runtime failure, never quiescence.
                self.retain_publication_scan(self.publication_scan.result())
                self.publication_scan = None
            for actor, state in self.states.items():
                state['lifecycle_at_close'] = state['status']
            save(self.root/'publication-continuation-terminal.json', {
                'at': utc(), 'scan_count': self.publication_scan_count,
                'versions_settled': self.publications.ready,
                'actors': {a: {'lifecycle': self.states[a]['status'],
                              'pending_next_batch': self.publications.pending(a),
                              'notified_versions': sorted(self.publications.notified[a])}
                           for a in self.actors}})

    def check_space(self, *, before_start=False):
        now = time.monotonic()
        if not before_start and now-self.last_space_check < 5:
            return
        self.last_space_check = now
        location = self.root if self.root.exists() else self.root.parent
        available = shutil.disk_usage(location).free
        minimum = self.reg['budget']['min_free_bytes']
        save(self.root/'storage-status.json', {'free_bytes':available,
             'minimum_free_bytes':minimum,'before_start':before_start})
        if available < minimum:
            self.stop_for_budget(None, 'free_storage_bytes', available)

    def notify_ready(self):
        # Check even while every participant is idle between real arrivals.
        self.check_space()
        super().notify_ready()
        self.poll_publications()
        self.resume_research()

    def handle(self, actor, message, deployment):
        if message['type'] == 'tool_call':
            if self.states[actor]['tools'] >= self.reg['budget']['max_tools_per_agent']:
                self.stop_for_budget(actor, 'tools', self.states[actor]['tools'])
        super().handle(actor, message, deployment)
        if self.publications is not None and message['type'] == 'settled':
            self.states[actor]['status'] = 'idle'
            if self.sustained_research:
                value = self.research_status[actor].value
                self.states[actor]['status'] = 'idle' if value['state'] == 'working' else value['state']
                self.research_due[actor] = time.monotonic()+self.reg['sustained_research']['resume_after_response_seconds']
                self.record(actor, {'type': 'research_response_ended', 'at': utc(),
                    'research_state': value, 'project_stopped': False})
        if message['type'] == 'provider_response':
            value = message['event']['response']
            self.usage[actor, value['id']] = value.get('usage', {})
            records = [u for (owner,_),u in self.usage.items() if owner==actor]
            tokens = sum((u.get('input_tokens') or 0)+(u.get('output_tokens') or 0) for u in records)
            self.states[actor].update(observed_model_responses=len(records), observed_tokens=tokens,
                missing_usage_records=sum(not u for u in records))
            save(self.root/'usage.json', {'actors':{a:{k:v for k,v in s.items() if k in
                ('observed_model_responses','observed_tokens','missing_usage_records')} for a,s in self.states.items()},
                'scope':'Observed native completed responses; opaque transport retries and in-flight calls may exceed these totals.'})
            if self.stopping.is_set():
                # Final response records still count, but a limit crossed while
                # retaining them must not relabel an earlier runtime failure.
                return
            if tokens >= self.reg['budget']['max_observed_tokens_per_agent']:
                self.stop_for_budget(actor, 'observed_tokens', tokens)
            if len(records) >= self.reg['budget']['max_responses_per_agent']:
                self.stop_for_budget(actor, 'observed_responses', len(records))

    def stop_for_budget(self, actor, metric, value):
        self.budget_stop = {'actor':actor,'metric':metric,'observed':value,'censored':True}
        save(self.root/'resource-budget-stop.json', self.budget_stop)
        raise RuntimeError('Registered structure-study resource budget reached')

    def run(self):
        # Refuse to consume a registration when the host cannot retain evidence.
        self.check_space(before_start=True)
        result = super().run()
        if self.budget_stop:
            # Preserve the underlying interruption alongside its experimental label.
            result['raw_reason'] = result['reason']
            result['reason'] = 'resource_budget'
            result['resource_budget'] = self.budget_stop
            save(self.root/'completion.json',result)
            save(self.root/'progress.json',{'status':'closed',**result})
        return result


def time_inventory(root, registration):
    """Descriptive events only. An empty annotation set is never a negative verdict."""
    root=Path(root)
    activation=root/'activation.json'
    if not activation.exists():
        return {'status':'not_activated','structural_review':'not_evaluable'}
    start=datetime.fromisoformat(json.loads(activation.read_text())['at'])
    theory=registration.get('workload')=='navier-stokes-theory'
    windows=([(f'window_{offset:05d}',offset) for offset in range(0,registration['budget']['max_agent_seconds'],registration['analysis_window_seconds'])]
             if theory else list(registration['arrival_offsets'].items()))
    rows={batch:{'batch':batch,'scheduled_offset_seconds':offset,'event_count':0,
                 'actors':{},'first_event':None,'last_event':None} for batch,offset in windows}
    for number,line in enumerate((root/'events.jsonl').read_text().splitlines(),1):
        event=json.loads(line)
        seconds=(datetime.fromisoformat(event['at'])-start).total_seconds()
        batch=next((batch for batch,offset in reversed(windows) if seconds>=offset),windows[0][0])
        row=rows[batch];row['event_count']+=1
        ref={'file':'events.jsonl','line':number,'at':event['at'],'seconds_after_activation':seconds}
        row['first_event']=row['first_event'] or ref;row['last_event']=ref
        if event.get('actor'):
            counts=row['actors'].setdefault(event['actor'],{})
            kind=event['type'];counts[kind]=counts.get(kind,0)+1
    return {'windows':list(rows.values()),'structural_review':'pending',
        'scope':('Passive elapsed-time analysis windows; no scheduled messages or task changes. Counts do not establish division of work, roles, adoption or communication.' if theory else
            'Scheduled business windows with actual event times; counts do not establish roles, adoption or communication. Actual delivery receipts remain in source-deliveries.json.')}
