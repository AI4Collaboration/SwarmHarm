"""Descriptive trial-level denominators; errors are never negative successes."""
import json,math
from pathlib import Path

def write(root,finished,admission,active,queued):
    rows=[]
    for model in ('deepseek','glm'):
        for seconds in (300,900):
            for repaired in (False,True):
                trials=[r for r in finished if r['cell']['model_name']==model and r['cell']['seconds']==seconds and r['cell']['repaired']==repaired]
                valid=[r['summary'] for r in trials if 'summary' in r and type(r['summary']['functional_communication_passed']) is bool]
                n=len(valid);k=sum(r['functional_communication_passed'] for r in valid);ci=None
                if n:
                    z=1.96;p=k/n;den=1+z*z/n;center=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;ci=[max(0,center-half),min(1,center+half)]
                rows.append({'model':model,'seconds':seconds,'repaired':repaired,'finished':len(trials),'valid':n,'unscored':len(trials)-n,'successful':k,'descriptive_wilson_95':ci})
    report={'status':'running' if active or admission=='open' else 'bounded_collection_ended','admission':admission,'active_trials':list(active),'queued_trials':len(queued),'finished_trials':len(finished),'cells':rows,'reported_response_cost_usd':sum(float(r.get('summary',{}).get('reported_response_cost_usd',0)) for r in finished),'limits':'Fixed template, provider/model confounding, shared budget censoring, potentially correlated repeated calls. Intervals are descriptive; no harm or general alignment claim.'}
    from durability import save
    save(root/'report.json',report)
    lines=['# Parallel Stage 1 results',f"Status: {report['status']}. Finished trials: {len(finished)}. Active: {len(active)}. Queued: {len(queued)}.",'','| Model | Seconds | Repaired | Successful / valid | Unscored |','| --- | --- | --- | --- | --- |']
    lines += [f"| {r['model']} | {r['seconds']} | {r['repaired']} | {r['successful']} / {r['valid']} | {r['unscored']} |" for r in rows]
    lines += ['',report['limits'],'','Native traces, request identities, original scores and unresolved reservations remain preserved. Backups are on this Mac.']
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n')
