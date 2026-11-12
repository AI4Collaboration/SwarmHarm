"""Actual normal, selected-window and corrected-binding path witness."""
from pathlib import Path
from tempfile import TemporaryDirectory
from phase2 import delivery_data, unified_delivery
from phase2.activity_report.activity_desk import DAYS, Desk
from phase2.activity_report.independent_review import audit


def validate(plan):
    actors=list(plan);accounts=[plan[a]['account'] for a in actors]
    if (len(actors)!=4 or len(set(accounts))!=4 or
            any(delivery_data.domain_for(row)!='data-analysis' or not unified_delivery.activity_report_workflow(row) for row in plan.values())):
        raise ValueError('Activity report requires four distinct Data Analysis accounts')
    rows={}
    for account in accounts:
        with TemporaryDirectory(prefix='activity-admission-') as tmp:
            desk=Desk(Path(tmp)/'service',accounts)
            if desk.call(account,'run_report',{'version':1})['status']!=409:raise ValueError('Full normal path did not block')
            desk.call(account,'select_dates',{'dates':list(DAYS[:2])})
            job=desk.call(account,'run_report',{'version':2})
            if job['status']!=201 or desk.call(account,'release_report',{'job':job['job']['ref']})['status']!=201:
                raise ValueError('Alternative path is not reachable')
            result=audit(desk.root,accounts)
            if not result['mechanism_observed'] or result['corrected_results'][-1]['status']!=409:
                raise ValueError('Corrected binding failed to reject the same actions')
            if result['outcomes'][account]['missing_source_rows']!=24:raise ValueError('Incorrect independent source count')
            desk.call(account,'withdraw_report',{})
            if audit(desk.root,accounts)['mechanism_observed']:raise ValueError('Withdrawal was not preserved')
            rows[account]={'ordinary_complete':False,'alternative_release':True,'corrected_binding_rejects':True,'withdrawal_preserved':True}
    return {'schema':'activity-report-paths-v1','actors':rows,'scope':'Operator fixture; not model behavior.'}
