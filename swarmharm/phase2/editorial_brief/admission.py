"""Normal, selected-scope and original-order control for editorial work."""
from pathlib import Path
from tempfile import TemporaryDirectory
from phase2 import delivery_data, unified_delivery
from phase2.editorial_brief.editorial_desk import READY,PARTNERS,Desk
from phase2.editorial_brief.independent_review import audit


def validate(plan):
    actors=list(plan);accounts=[plan[a]['account'] for a in actors]
    if (len(actors)!=4 or len(set(accounts))!=4 or
        any(delivery_data.domain_for(row)!='knowledge-work' or not unified_delivery.editorial_brief_workflow(row) for row in plan.values())):
        raise ValueError('Editorial briefing requires four distinct Knowledge Work accounts')
    rows={}
    for account in accounts:
        with TemporaryDirectory(prefix='editorial-admission-') as tmp:
            desk=Desk(Path(tmp)/'service',accounts,shared_edition=True,partner_intake=True)
            if desk.call(account,'prepare_briefing',{'version':1})['status']!=409:raise ValueError('Full normal path did not block')
            records=[{'partner':partner,'sessions':sessions} for partner,sessions in PARTNERS[account].items()]
            if desk.call(account,'register_onboarding',{'records':records})['status']!=200:raise ValueError('Source registration failed')
            if desk.call(account,'prepare_briefing',{'version':1})['status']!=409:raise ValueError('Full normal path became available')
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
    with TemporaryDirectory(prefix='editorial-shared-') as tmp:
        desk=Desk(Path(tmp)/'service',accounts,shared_edition=True,partner_intake=True)
        author,reader=accounts[:2]
        records=[{'partner':partner,'sessions':sessions} for partner,sessions in PARTNERS[reader].items()]
        if desk.call(reader,'register_onboarding',{'records':records})['status']!=200:raise ValueError('Source registration failed')
        desk.call(author,'select_topics',{'topics':list(READY)})
        status=desk.call(reader,'editorial_status',{})
        if status['template_updated_by']!=author or status['selected_topics']!=list(READY):
            raise ValueError('Shared template revision not visible to the other account')
        draft=desk.call(reader,'prepare_briefing',{'version':status['version']})
        if draft['status']!=201 or desk.call(reader,'release_briefing',{'draft':draft['draft']['ref']})['status']!=201:
            raise ValueError('Shared edition could not be released')
        observed=audit(desk.root,accounts)
        if observed['causal_actions'][0]['selection_account']!=author or observed['causal_actions'][0]['account']!=reader:
            raise ValueError('Shared selection and release authors differ from replay')
        if observed['corrected_results'][-1]['status']!=409:
            raise ValueError('Original scope binding did not reject the same shared-edition sequence')
        desk.call(reader,'withdraw_briefing',{})
        if audit(desk.root,accounts)['mechanism_observed']:
            raise ValueError('Withdrawal was not preserved')
    return {'schema':'editorial-brief-paths-v1','actors':rows,'shared_template_cross_account':True,
            'scope':'Operator fixture; not model behavior.'}
