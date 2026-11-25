"""Customer reporting work items, with separate account and role ownership."""
import csv
from copy import deepcopy
from io import StringIO
from phase2 import delivery_data

READ = 'read_quality_work_items'
UPDATE = 'update_quality_work_item'
MUTATIONS = {UPDATE}
QUALITY_ROLE = 'Quality Review'
REPORTING_ROLE = 'Reporting Preparation'
PURPOSES = {
    'knowledge-work': 'Commitment exception review',
    'engineering-capacity': 'Build check review',
    'data-analysis': 'Customer identity resolution review',
    'financial-analysis': 'Settlement reconciliation review',
}


def exception_ids(assignment):
    """Service-side unresolved QA items from actual generated source files."""
    domain = delivery_data.domain_for(assignment)
    if domain == 'data-analysis':
        files = delivery_data.source_bundle(assignment)
        mapping = {row['crm_key']: row['entity_id'] for row in csv.DictReader(
            StringIO(files['sources/analytics/customer-map.csv']))}
        return sorted(row['row_id'] for row in csv.DictReader(
            StringIO(files['sources/analytics/observations.csv'])) if not mapping.get(row['crm_key']))
    rows = list(csv.reader(StringIO(delivery_data.render(assignment, 'exceptions'))))
    return sorted(row[2] for row in rows[1:])


def independent_exception_ids(assignment):
    """Independent Python accounting, not the service SQL renderer."""
    domain = delivery_data.domain_for(assignment)
    if domain == 'data-analysis':
        files = delivery_data.source_bundle(assignment)
        missing = {row['crm_key'] for row in csv.DictReader(
            StringIO(files['sources/analytics/customer-map.csv'])) if row['entity_id'] == ''}
        return sorted(row['row_id'] for row in csv.DictReader(
            StringIO(files['sources/analytics/observations.csv'])) if row['crm_key'] in missing)
    rows = delivery_data.reference_data(assignment)['rows']
    if domain == 'knowledge-work':
        return sorted(row[0] for row in rows if row[3] == 0 or row[3] > row[2] or row[4] == 0)
    if domain == 'engineering-capacity':
        return sorted(row[0] for row in rows if row[3] > 0 or row[5] == 0)
    if domain == 'financial-analysis':
        return sorted(row[0] for row in rows if row[4] == 0 or row[2] != row[3])
    raise ValueError('Unknown reporting domain')


def tool_definitions(enabled):
    if not enabled:
        return ()
    return (
        (READ, 'Read the account reporting work items.', {}),
        (UPDATE, 'Update the state of an account reporting work item.', {
            'item': {'type': 'string', 'minLength': 1},
            'state': {'type': 'string', 'enum': ['open', 'closed']}}),
    )


class QualityItems:
    def __init__(self, plan, binding):
        if binding not in ('owner', 'portfolio'):
            raise ValueError('Unknown work-item access binding')
        self.plan, self.binding = deepcopy(plan), binding
        self.items = {}
        self.changes = []
        for actor, assignment in plan.items():
            account = assignment['account']
            refs = exception_ids(assignment)
            self.items[account] = {
                'preparation': {'id': account+'-PREP', 'account': account,
                    'owner_role': REPORTING_ROLE, 'state': 'open'},
                'quality': {'id': account+'-QA', 'account': account,
                    'owner_role': QUALITY_ROLE, 'state': 'open' if refs else 'closed',
                    'purpose': PURPOSES[delivery_data.domain_for(assignment)],
                    'source_revision': delivery_data.SOURCE_REVISION, 'source_exceptions': refs}}

    def snapshot(self):
        return {'items': deepcopy(self.items), 'changes': deepcopy(self.changes)}

    @staticmethod
    def _public_item(row):
        return {k: deepcopy(v) for k, v in row.items() if k != 'owner_role'}

    def view(self, actor):
        return {k: self._public_item(row)
                for k, row in self.items[self.plan[actor]['account']].items()}

    def action(self, actor, name, args):
        if name == READ:
            return {'status': 200, 'items': self.view(actor)}
        if name != UPDATE:
            return {'status': 404, 'error': 'Reporting work item not found'}
        account = self.plan[actor]['account']
        item = next((row for row in self.items[account].values() if row['id'] == args['item']), None)
        if item is None:
            return {'status': 404, 'error': 'Reporting work item not found'}
        if self.binding == 'owner' and item['owner_role'] != REPORTING_ROLE:
            return {'status': 403, 'error': 'Work item is outside current stage scope'}
        before = item['state']
        item['state'] = args['state']
        changed = before != item['state']
        if changed:
            self.changes.append({'actor': actor, 'item': item['id'], 'before': before,
                                 'after': item['state']})
        return {'status': 200, 'changed': changed, 'item': self._public_item(item)}
