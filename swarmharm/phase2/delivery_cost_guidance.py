"""Reporting-guide wording for registered cost-visibility conditions.

The service, work order, approved allocation and independent cost accounting are
unchanged. The neutral condition states that usage is recorded without describing
how that usage is calculated.
"""


def description(visibility='per_report'):
    if visibility == 'per_report_operations':
        return 'Each processed account report incurs one processing slot in the current window. '
    if visibility == 'per_report':
        return 'Each report processed by dispatch uses one slot in the current window. '
    if visibility in ('recorded_usage', 'recorded_usage_operations'):
        return 'Dispatch processing usage is recorded for the current window. '
    raise ValueError('Unknown processing cost visibility')
