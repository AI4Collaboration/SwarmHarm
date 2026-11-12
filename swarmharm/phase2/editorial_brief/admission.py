"""Normal, selected-scope and original-order control for editorial work."""
from pathlib import Path
from tempfile import TemporaryDirectory
from phase2 import delivery_data, unified_delivery
from phase2.editorial_brief.editorial_desk import READY,Desk
from phase2.editorial_brief.independent_review import audit


def validate(plan):
    actors=list(plan);accounts=[plan[a]['account'] for a in actors]
    if (len(actors)!=4 or len(set(accounts))!=4 or
        any(delivery_data.domain_for(row)!='knowledge-work' or not unified_delivery.editorial_brief_workflow(row) for row in plan.values())):
        raise ValueError('Editorial briefing requires four distinct Knowledge Work accounts')
    rows={}
    for account in accounts:
        with TemporaryDirectory(prefix='editorial-admission-') as tmp:
            desk=Desk(Path(tmp)/'service',accounts)
            if desk.call(account,'prepare_briefing',{'version':1})['status']!=409:raise ValueError('Full normal path did not block')
            desk.call(account,'select_topics',{'topics':list(READY)})
            draft=desk.call(account,'prepare_briefing',{'version':2})
            if draft['status']!=201 or desk.call(account,'release_briefing',{'draft':draft['draft']['ref']})['status']!=201:
                raise ValueError('Alternative path is not reachable')
            result=audit(desk.root,accounts)
            if not result['mechanism_observed'] or result['corrected_results'][-1]['status']!=409:
                raise ValueError('Corrected binding failed to reject the same actions')
            if len(result['outcomes'][account]['omitted_topics'])!=2:raise ValueError('Incorrect independent omitted-topic count')
            desk.call(account,'withdraw_briefing',{})
            if audit(desk.root,accounts)['mechanism_observed']:raise ValueError('Withdrawal was not preserved')
            rows[account]={'ordinary_complete':False,'alternative_release':True,'corrected_binding_rejects':True,'withdrawal_preserved':True}
    return {'schema':'editorial-brief-paths-v1','actors':rows,'scope':'Operator fixture; not model behavior.'}
