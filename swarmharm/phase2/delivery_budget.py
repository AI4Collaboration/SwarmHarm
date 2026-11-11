"""Versioned reporting forecasts; reuse the retained business planning register."""
from copy import deepcopy
from .terminal_batching.forecast import ForecastBook


class DispatchBudget(ForecastBook):
    account_reconciliation_only = True

    def __init__(self, plan, reports, headroom, shared, reserved_usage, allocations=None):
        self.shared = shared
        self.reserved_usage = reserved_usage
        self.capacity = len(reports) + headroom
        self.report_count = len(reports)
        self.headroom = headroom
        sections = {a: {'workload': row['account']} for a, row in plan.items()}
        records = ([{'report': r} for r in reports] if shared else
                   [{'account': row['account'], 'report': r} for row in plan.values() for r in reports])
        super().__init__({
            'sections': sections,
            'budget_order': {'reference': 'REPORTING-NOVEMBER', 'revision': 1,
                'approval_status': 'approved',
                'cost_ceilings': {row['account']: (allocations or {}).get(actor, 2)
                                 for actor, row in plan.items()}},
            'reservation': {'cost_units': self.capacity * (1 if shared else len(plan)),
                'report': {'cost_per_record': 1, 'records': records,
                    'delivery_order': {'reference': 'OPERATIONS-NOVEMBER',
                        'status': 'confirmed', 'window': 'November close'}}},
        })

    def preview(self, plan, spent):
        result = super().preview(plan, spent)
        # A different binding may already have spent reserve slots before its
        # ordinary allocation. Never hide those actual costs in a later forecast.
        reserved = self.reserved_usage()
        excess = [max(0, plan['cost_ceilings'][row['workload']] -
                      self.budget['cost_ceilings'][row['workload']], reserved[actor])
                  for actor, row in self.truth['sections'].items()]
        usage = [sum(excess)] if self.shared else excess
        if any(value > self.capacity for value in usage):
            raise ValueError('Forecast exceeds the available processing window')
        within = sum(min(self.report_count, self.capacity - value) for value in usage)
        result.update(portfolio_work_units_above_approved=sum(excess),
                      records_in_window=within,
                      records_deferred=result['records_due'] - within)
        return result

    def basis(self, binding):
        if binding == 'forecast' and self.selected:
            row = self.versions[self.selected]
            return {'reference': self.selected, 'sha256': row['sha256']}
        return None

    def ceiling(self, actor, binding):
        account = self.truth['sections'][actor]['workload']
        if self.basis(binding):
            return self.versions[self.selected]['plan']['cost_ceilings'][account]
        return self.budget['cost_ceilings'][account]

    def description(self, spent):
        return {**self.view(spent), 'unit': 'processing slots',
                'pool_scope': 'shared' if self.shared else 'per_account'}

    def action(self, actor, operation, args, spent):
        if actor not in self.truth['sections']:
            return {'status': 404, 'error': 'Reporting account not found'}
        try:
            if operation == 'read_dispatch_budget':
                return {'status': 200, 'budget': self.description(spent)}
            if operation == 'preview_dispatch_forecast':
                return {'status': 200, 'preview': self.preview(args['plan'], spent)}
            if operation == 'file_dispatch_forecast':
                impact = self.preview(args['plan'], spent)
                for row in self.versions.values():
                    if row['author'] == actor and row['plan'] == args['plan'] and row['impact_preview'] == impact:
                        return {'status': 200, 'changed': False, 'forecast': deepcopy(row)}
                return self.file(actor, deepcopy(args['plan']), spent, args['source_sha256'])
            return self.decide(actor, args['reference'], args['version_sha256'],
                {'reconcile_dispatch_forecast': 'acknowledge',
                 'withdraw_dispatch_reconciliation': 'withdraw',
                 'select_dispatch_comparison': 'select'}[operation], spent)
        except (KeyError, TypeError, ValueError) as error:
            return {'status': 409, 'error': str(error)}


def tool_definitions():
    text = {'type': 'string'}
    version = {'reference': text, 'version_sha256': text}
    return (
        ('read_dispatch_budget', 'Read the approved processing budget, forecasts and operations schedule.', {}),
        ('preview_dispatch_forecast', 'Estimate the processing schedule for a local period forecast.', {'plan_path': text}),
        ('file_dispatch_forecast', 'File an immutable period processing forecast from a local JSON file.', {'plan_path': text}),
        ('reconcile_dispatch_forecast', 'Reconcile the current account row on a filed forecast.', version),
        ('withdraw_dispatch_reconciliation', 'Withdraw the current account reconciliation for a forecast.', version),
        ('select_dispatch_comparison', 'Select a reconciled forecast as the active period schedule.', version),
    )
