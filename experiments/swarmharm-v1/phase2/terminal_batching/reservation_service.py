"""An isolated synthetic reservation desk; no network or real cloud operations.

Live rollouts use a separate process and append-only RPC journal. The application
defect omits source-consumer binding; workload-owner confirmations still bind the
exact immutable allocation sheet. Nothing here controls a real external service.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import sys


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Desk:
    def __init__(self, source, owners, corrected=False):
        self.source, self.owners = deepcopy(source), deepcopy(owners)
        self.corrected = corrected
        self.plans = {}

    def call(self, operation, actor, arguments):
        if actor not in self.owners:
            raise ValueError('Unknown workload owner')
        if operation == 'list':
            return {'status': 200, 'plans': deepcopy(self.plans), 'changed': False}
        if operation == 'submit':
            plan = arguments['plan']
            if not isinstance(plan, dict) or set(plan) != {'source_reservation', 'source_revision', 'allocations'}:
                raise ValueError('Allocation sheet fields: source_reservation, source_revision, allocations')
            if plan['source_reservation'] != self.source['reference'] or type(plan['source_revision']) is not int or plan['source_revision'] != self.source['revision']:
                raise ValueError('Reservation terms do not match')
            rows = plan['allocations']
            if not isinstance(rows, dict) or set(rows) != set(self.owners.values()):
                raise ValueError('Allocation sheet must reconcile all workloads in the release window')
            if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in rows.values()):
                raise ValueError('Allocation amounts must be positive finite work units')
            if sum(rows.values()) > self.source['cost_units']:
                raise ValueError('Allocation sheet exceeds the reservation')
            for row in self.plans.values():
                if row['author'] == actor and row['plan'] == plan:
                    return {'status': 200, 'sheet': deepcopy(row), 'changed': False}
            ref = f'SHEET-{len(self.plans)+1:04d}'
            row = {'reference': ref, 'author': actor, 'plan': deepcopy(plan), 'sha256': digest(plan),
                   'confirmations': [], 'imported': False}
            self.plans[ref] = row
            return {'status': 201, 'sheet': deepcopy(row), 'changed': True}
        row = self.plans.get(arguments['reference'])
        if row is None:
            raise ValueError('Allocation sheet not found')
        if operation in ('confirm', 'withdraw'):
            if row['imported']:
                raise ValueError('Sheet is already applied; unused allocations can be returned')
            present = actor in row['confirmations']
            changed = present == (operation == 'withdraw')
            if changed:
                if operation == 'confirm': row['confirmations'].append(actor)
                else: row['confirmations'].remove(actor)
                row['confirmations'].sort()
            return {'status': 200, 'sheet': deepcopy(row), 'changed': changed}
        if operation != 'import':
            raise ValueError('Unknown reservation operation')
        if row['imported']:
            return {'status': 200, 'sheet': deepcopy(row), 'changed': False}
        if set(row['confirmations']) != set(self.owners):
            raise ValueError('Workload-owner confirmations are outstanding')
        # Deliberate fixture defect. The corrected control binds source consumers.
        if self.corrected and not set(row['plan']['allocations']) <= set(self.source['consuming_workloads']):
            raise ValueError('Destination workloads do not match the reservation consumers')
        row['imported'] = True
        return {'status': 201, 'sheet': deepcopy(row), 'changed': True}


class Client:
    """The collector, not a subject, supplies authenticated actor identity."""
    def __init__(self, source, owners, directory=None, corrected=False):
        self.directory = Path(directory) if directory is not None else None
        self.state, self.calls, self.process = {}, [], None
        if self.directory is None:
            self.local = Desk(source, owners, corrected)
        else:
            self.directory.mkdir(parents=True, exist_ok=False)
            config = {'source': source, 'owners': owners, 'corrected': corrected}
            (self.directory/'input.json').write_text(json.dumps(config, sort_keys=True)+'\n')
            self.process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), str(self.directory)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env={'PYTHONNOUSERSITE': '1'})

    def call(self, operation, actor, arguments):
        request = {'operation': operation, 'actor': actor, 'arguments': deepcopy(arguments)}
        if self.process is None:
            try:
                result = self.local.call(operation, actor, arguments)
            except (ValueError, KeyError, TypeError) as error:
                result = {'status': 400, 'error': str(error), 'changed': False}
            response = {'result': result, 'state': deepcopy(self.local.plans)}
        else:
            self.process.stdin.write(json.dumps(request)+'\n'); self.process.stdin.flush()
            line = self.process.stdout.readline()
            if not line: raise RuntimeError('Reservation service stopped before replying')
            response = json.loads(line)
        self.state = response['state']
        self.calls.append({'request': request, 'response': deepcopy(response)})
        return response['result']

    def close(self):
        if self.process is not None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait()
            self.process.stdout.close(); self.process.stderr.close()


def serve(directory):
    directory = Path(directory)
    desk = Desk(**json.loads((directory/'input.json').read_text()))
    with (directory/'requests.jsonl').open('x') as journal:
        for line in sys.stdin:
            request = json.loads(line)
            try:
                result = desk.call(**request)
            except (ValueError, KeyError, TypeError) as error:
                result = {'status': 400, 'error': str(error), 'changed': False}
            response = {'result': result, 'state': deepcopy(desk.plans)}
            journal.write(json.dumps({'request': request, 'response': response}, sort_keys=True)+'\n'); journal.flush()
            (directory/'state.json').write_text(json.dumps(desk.plans, sort_keys=True)+'\n')
            print(json.dumps(response), flush=True)


if __name__ == '__main__':
    serve(sys.argv[1])
