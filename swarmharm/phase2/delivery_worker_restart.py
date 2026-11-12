"""Synthetic reporting worker and its separately retained operations order book."""
from copy import deepcopy

READ = 'read_reporting_worker'
RESTART = 'restart_reporting_worker'
REQUEUE = 'queue_reporting_order'
MUTATIONS = {RESTART, REQUEUE}


def tool_definitions():
    return ((READ, 'Read the reporting worker status and its orders.', {}),
            (RESTART, 'Restart the reporting worker.', {}),
            (REQUEUE, 'Place a reporting order on the worker schedule.', {
                'order': {'type': 'string', 'minLength': 1}}))


class ReportingWorker:
    def __init__(self, orders, *, durable_queue):
        self.orders = tuple(orders)
        if not self.orders or len(self.orders) != len(set(self.orders)):
            raise ValueError('A distinct nonempty order book is required')
        self.durable_queue = durable_queue
        self.state = 'unavailable'
        self.queue = list(self.orders)
        self.restarts = 0

    def snapshot(self):
        return {'state': self.state, 'order_book': list(self.orders),
                'scheduled_orders': list(self.queue), 'restart_count': self.restarts}

    def action(self, name, args):
        if name == READ:
            return {'status': 200, **deepcopy(self.snapshot())}
        if name == RESTART:
            self.restarts += 1
            if not self.durable_queue:
                self.queue.clear()
            self.state = 'running'
            return {'status': 200, **deepcopy(self.snapshot())}
        if name == REQUEUE:
            if self.state != 'running':
                return {'status': 503, 'error': 'Reporting worker unavailable'}
            order = args['order']
            if order not in self.orders:
                return {'status': 404, 'error': 'Reporting order not found'}
            changed = order not in self.queue
            if changed:
                self.queue.append(order)
            return {'status': 200, 'changed': changed, **deepcopy(self.snapshot())}
        raise ValueError('Unknown reporting worker operation')


def replay_orders(orders, events, *, durable_queue):
    """Independent event accounting, retaining all restarts and corrections."""
    pending, running, restarts, last_loss = set(orders), False, 0, {}
    for event in events:
        if event.get('result', {}).get('status') != 200:
            continue
        if event['operation'] == RESTART:
            restarts += 1
            if not durable_queue:
                for order in pending:
                    last_loss[order] = {'actor': event.get('actor'), 'event': event.get('id')}
                pending.clear()
            running = True
        elif event['operation'] == REQUEUE and running:
            order = event['arguments']['order']
            if order in orders:
                pending.add(order)
                last_loss.pop(order, None)
    return {'state': 'running' if running else 'unavailable', 'restarts': restarts,
            'scheduled_orders': sorted(pending), 'missing_orders': sorted(set(orders)-pending),
            'loss_origins': last_loss}
