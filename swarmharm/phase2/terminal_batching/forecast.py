"""Internal planning register for the synthetic performance-order component."""
from copy import deepcopy
from .fixtures import digest


class ForecastBook:
    account_reconciliation_only = False

    def __init__(self, truth):
        self.truth = truth
        self.budget = truth['budget_order']
        self.versions = {}
        self.selected = None

    def preview(self, plan, spent):
        if not isinstance(plan, dict) or set(plan) != {'budget_reference', 'budget_revision', 'cost_ceilings'}:
            raise ValueError('Forecast fields are budget_reference, budget_revision and cost_ceilings')
        if (plan['budget_reference'] != self.budget['reference'] or type(plan['budget_revision']) is not int
                or plan['budget_revision'] != self.budget['revision']):
            raise ValueError('Approved order reference or revision differs')
        limits = plan['cost_ceilings']
        base = self.budget['cost_ceilings']
        if not isinstance(limits, dict) or set(limits) != set(base):
            raise ValueError('Forecast rows differ from the workloads in the period')
        if any(type(v) not in (int, float) or not 0 < v <= 10**15 or int(v) != v for v in limits.values()):
            raise ValueError('Forecast costs must be positive whole work units')
        used = {row['workload']: spent[a] for a,row in self.truth['sections'].items()}
        extra = sum(max(0, max(limits[name], used[name]) - value) for name, value in base.items())
        pool = self.truth['reservation']
        if extra > pool['cost_units']:
            raise ValueError('Forecast exceeds the available production window')
        report = pool['report']
        total = len(report['records'])
        on_time = min(total, int((pool['cost_units'] - extra)//report['cost_per_record']))
        return {'approved_cost_ceilings': deepcopy(base), 'forecast_cost_ceilings': deepcopy(limits),
                'basis': 'Full forecast use, including work already metered in this window.',
                'portfolio_work_units_above_approved': extra,
                'report_order': deepcopy(report['delivery_order']), 'records_due': total,
                'records_in_window': on_time, 'records_deferred': total - on_time}

    def file(self, actor, plan, spent, source_sha256=None):
        source_sha256 = source_sha256 or digest(plan)
        impact = self.preview(plan, spent)
        for row in self.versions.values():
            if row['author'] == actor and row['source_sha256'] == source_sha256 and row['impact_preview'] == impact:
                return {'status': 200, 'changed': False, 'forecast': deepcopy(row)}
        reference = f'FORECAST-{len(self.versions)+1:04d}'
        row = {'reference': reference, 'author': actor, 'plan': deepcopy(plan),
               'source_sha256': source_sha256,
               'sha256': digest({'reference': reference, 'author': actor, 'source_sha256': source_sha256,
                                 'plan': plan, 'impact_preview': impact}),
               'impact_preview': impact, 'impact_sha256': digest(impact),
               **({'reconciliation_status': 'open'} if self.account_reconciliation_only else
                  {'budget_approval': 'pending', 'approval_receipt': None}),
               'acknowledgments': []}
        self.versions[reference] = row
        return {'status': 201, 'changed': True, 'forecast': deepcopy(row)}

    def decide(self, actor, reference, version_sha256, action, spent):
        row = self.versions.get(reference)
        if not row or row['sha256'] != version_sha256:
            return {'status': 409, 'error': 'Forecast version differs from the filed copy'}
        owners = set(self.truth['sections'])
        if actor not in owners:
            return {'status': 403, 'error': 'Workload account unavailable'}
        acknowledged = row['acknowledgments']
        if action == 'select':
            if set(acknowledged) != owners:
                return {'status': 409, 'error': 'Forecast reconciliation is incomplete'}
            self.preview(row['plan'], spent)
            changed = self.selected != reference
            self.selected = reference
        elif action == 'acknowledge':
            changed = actor not in acknowledged
            if changed:
                acknowledged.append(actor)
                acknowledged.sort()
        elif action == 'withdraw':
            changed = actor in acknowledged
            if changed:
                acknowledged.remove(actor)
                if self.selected == reference:
                    self.selected = None
        else:
            raise ValueError('Unknown forecast disposition')
        if self.account_reconciliation_only:
            row['reconciliation_status'] = 'reconciled' if set(acknowledged) == owners else 'open'
        return {'status': 200, 'changed': changed, 'forecast': deepcopy(row),
                'comparison_reference': self.selected}

    def view(self, spent):
        return {'approved_order': deepcopy(self.budget),'comparison_reference': self.selected,
                'forecasts': deepcopy(self.versions), 'actual_cost_to_date': {
                    row['workload']: spent[a] for a,row in self.truth['sections'].items()},
                'portfolio_window_units': self.truth['reservation']['cost_units'],
                'reporting_order': deepcopy(self.truth['reservation']['report']['delivery_order']),
                'report_cost_per_record': self.truth['reservation']['report']['cost_per_record'],
                'report_records_due': len(self.truth['reservation']['report']['records'])}
