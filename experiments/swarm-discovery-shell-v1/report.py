"""Matched-shell trial counts; unresolved tools and grades stay separate."""
import json
from pathlib import Path

def write(root,finished,admission,active,queued):
    rows=[]
    for model in ('deepseek','glm'):
        for arm in ('stock','fixed'):
            trials=[r for r in finished if r['cell']['model_name']==model and r['cell']['shell_arm']==arm]
            valid=[r['summary'] for r in trials if 'summary' in r and type(r['summary']['functional_communication_passed']) is bool]
            unknown=sum(any(w['stop']=='unknown_tool' for w in r.get('summary',{}).get('workers',{}).values()) for r in trials)
            rows.append({'model':model,'shell_arm':arm,'finished':len(trials),'valid':len(valid),'unscored':len(trials)-len(valid),'trials_with_unresolved_tool':unknown,'functional_passed':sum(s['functional_communication_passed'] for s in valid)})
    report={'status':'running' if active or admission=='open' else 'bounded_collection_ended','admission':admission,'active_trials':list(active),'queued_trials':len(queued),'finished_trials':len(finished),'cells':rows,'reported_finished_response_cost_usd':sum(float(r.get('summary',{}).get('reported_response_cost_usd',0)) for r in finished),'limits':'Two repetitions per cell, fixed business template and model/provider confounding. Unresolved tool processes retained; no replay. Ordinary cooperation is not harm or general alignment.'}
    from durability import save
    save(root/'report.json',report)
    text=['# Matched shell trials',f"Status: {report['status']}. Finished: {len(finished)}. Active: {len(active)}. Queued: {len(queued)}.",'','| Model | Shell | Functional / valid | Unscored | Unresolved tool trials |','| --- | --- | --- | --- | --- |']
    text += [f"| {r['model']} | {r['shell_arm']} | {r['functional_passed']} / {r['valid']} | {r['unscored']} | {r['trials_with_unresolved_tool']} |" for r in rows]
    text += ['',report['limits'],'','Exact initial messages/files/fixtures/plan, 900-second actor windows and 30-second no-kill shell waits are matched. Raw backups are on this Mac.']
    (root/'REPORT.md').write_text('\n'.join(text)+'\n')
