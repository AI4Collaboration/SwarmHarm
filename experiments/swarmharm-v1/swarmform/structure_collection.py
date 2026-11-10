"""Observed resource limits and time-window inventories, without subject nudges."""
from datetime import datetime
import json
from pathlib import Path
import shutil
import time

from swarmform.collection import Collection, save


class StructureCollection(Collection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.usage = {}
        self.budget_stop = None
        self.last_space_check = 0

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

    def handle(self, actor, message, deployment):
        if message['type'] == 'tool_call':
            if self.states[actor]['tools'] >= self.reg['budget']['max_tools_per_agent']:
                self.stop_for_budget(actor, 'tools', self.states[actor]['tools'])
        super().handle(actor, message, deployment)
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
