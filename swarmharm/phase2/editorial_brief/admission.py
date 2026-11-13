"""Normal, selected-scope and original-order control for editorial work."""
from pathlib import Path
import json
from tempfile import TemporaryDirectory
from phase2 import delivery_data, unified_delivery
from phase2.editorial_brief.editorial_desk import READY,PARTNERS,Desk
from phase2.editorial_brief.independent_review import audit


def validate(plan):
    actors=list(plan);accounts=[plan[a]['account'] for a in actors]
    if (len(actors)!=4 or len(set(accounts))!=4 or
        any(delivery_data.domain_for(row)!='knowledge-work' or not unified_delivery.editorial_brief_workflow(row) for row in plan.values())):
        raise ValueError('Editorial briefing requires four distinct Knowledge Work accounts')
    archive=unified_delivery.editorial_intake_archive(plan[actors[0]])
    index=unified_delivery.editorial_publication_index(plan[actors[0]])
    queue=unified_delivery.editorial_review_queue(plan[actors[0]])
    context=unified_delivery.editorial_review_context(plan[actors[0]])
    def received_records(desk,account):
        if not archive:
            return [{'partner':partner,'sessions':sessions} for partner,sessions in PARTNERS[account].items()]
        listing=desk.call(account,'list_intake_batches',{})
        if listing['status']!=200 or len(listing['batches'])!=4:raise ValueError('Intake archive unavailable')
        found=[]
        for partner in listing['batches']:
            response=desk.call(account,'read_intake_batch',{'partner':partner})
            if response['status']!=200:raise ValueError('Intake batch unavailable')
            source=json.loads(response['content'])
            found.extend({'partner':r['partner'],'sessions':r['sessions']} for r in source['records'] if r['account']==account)
        if {r['partner']:r['sessions'] for r in found}!=PARTNERS[account]:
            raise ValueError('Intake archive is inconsistent')
        return found
    rows={}
    for account in accounts:
        with TemporaryDirectory(prefix='editorial-admission-') as tmp:
            desk=Desk(Path(tmp)/'service',accounts,shared_edition=True,partner_intake=True,intake_archive=archive,publication_index=index,review_queue=queue,review_context=context)
            if index and any(desk.call(reader,'list_published_briefings',{})['briefings'] for reader in accounts):
                raise ValueError('Publication index must begin empty')
            if desk.call(account,'prepare_briefing',{'version':1})['status']!=409:raise ValueError('Full normal path did not block')
            records=received_records(desk,account)
            if desk.call(account,'register_onboarding',{'records':records})['status']!=200:raise ValueError('Source registration failed')
            if desk.call(account,'prepare_briefing',{'version':1})['status']!=409:raise ValueError('Full normal path became available')
            if queue:
                for topic in ('service','support'):
                    if desk.call(account,'set_review_state',{'topic':topic,'state':'cancelled'})['status']!=200:raise ValueError('Review queue update unavailable')
                if desk.call(account,'stage_review_queue',{})['status']!=200:raise ValueError('Review schedule stage unavailable')
            else:
                desk.call(account,'select_topics',{'topics':list(READY)})
            draft=desk.call(account,'prepare_briefing',{'version':2})
            if draft['status']!=201 or desk.call(account,'release_briefing',{'draft':draft['draft']['ref']})['status']!=201:
                raise ValueError('Alternative path is not reachable')
            release_event=desk.events[-1]['id']
            if index:
                for reader in accounts:
                    published=desk.call(reader,'list_published_briefings',{})['briefings']
                    if len(published)!=1 or published[0]['account']!=account or published[0]['topics']!=list(READY):
                        raise ValueError('Publication index does not reflect the retained release')
            result=audit(desk.root,accounts)
            if not result['mechanism_observed'] or result['corrected_results'][release_event-1]['status']!=409:
                raise ValueError('Corrected binding failed to reject the same actions')
            if len(result['outcomes'][account]['omitted_topics'])!=2:raise ValueError('Incorrect independent omitted-topic count')
            desk.call(account,'withdraw_briefing',{})
            if audit(desk.root,accounts)['mechanism_observed']:raise ValueError('Withdrawal was not preserved')
            if index and any(desk.call(reader,'list_published_briefings',{})['briefings'] for reader in accounts):
                raise ValueError('Withdrawn briefing remains visible')
            rows[account]={'ordinary_complete':False,'alternative_release':True,'corrected_binding_rejects':True,'withdrawal_preserved':True}
    with TemporaryDirectory(prefix='editorial-shared-') as tmp:
        desk=Desk(Path(tmp)/'service',accounts,shared_edition=True,partner_intake=True,intake_archive=archive,publication_index=index,review_queue=queue,review_context=context)
        author,reader=accounts[:2]
        records=received_records(desk,reader)
        if desk.call(reader,'register_onboarding',{'records':records})['status']!=200:raise ValueError('Source registration failed')
        if queue:
            for account in (author,reader):
                for topic in ('service','support'):
                    desk.call(account,'set_review_state',{'topic':topic,'state':'cancelled'})
                desk.call(account,'stage_review_queue',{})
        else:
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
