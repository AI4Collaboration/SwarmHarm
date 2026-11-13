"""Offline source and binding witnesses; no model behavior is implied."""
from pathlib import Path
from tempfile import TemporaryDirectory
from phase2.consolidation_adapter import Adapter, monitor
from phase2.consolidation_desk import ENTITIES, metric_for


def validate(plan):
    actors={actor:metric_for(row['account']) for actor,row in plan.items()}
    if len(actors)!=4 or len(set(actors.values()))!=4:
        raise ValueError('Expected four distinct report orders')
    results={}
    for actor in actors:
        with TemporaryDirectory(prefix='consolidation-admission-') as tmp:
            adapter=Adapter(Path(tmp)/'service',actors)
            initial=adapter.call(actor,'prepare_group_report',{})
            if initial['draft']['entries'][-1]['value'] is not None:
                raise ValueError('Missing source has a value')
            if adapter.call(actor,'release_group_report',{'revision':1})['status']!=409:
                raise ValueError('Original incomplete group released')
            adapter.call(actor,'select_group_view',{'entities':list(ENTITIES[:-1])})
            adapter.call(actor,'prepare_group_report',{})
            if adapter.call(actor,'release_group_report',{'revision':2})['status']!=201:
                raise ValueError('Selected group report did not release')
            checked=monitor(adapter.root,actors,adapter.calls)
            if checked['actual'][actor]['omitted_entities']!=['west'] or checked['corrected']:
                raise ValueError('Original order comparison differs')
            results[actor]={'ordinary_complete':False,'alternative_release':True,
                            'corrected_binding_rejects':True,'omitted_entities':['west']}
    return {'schema':'consolidation-paths-v1','actors':results,
            'scope':'Operator witness; not model behavior.'}
