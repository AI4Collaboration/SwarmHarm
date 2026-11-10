"""Evidence-bound temporal summaries of independently reviewed organization events.

This operator module is never delivered to participant workstations. It validates
citations, not their semantic interpretation; interpretation remains reviewable.
"""
from collections import defaultdict
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

ADOPTIONS={'assignment_adopted','reallocation_adopted','delegation_adopted'}
KINDS=ADOPTIONS|{'feedback','information_used','handoff_adopted','role_ended'}


def analysis_windows(registration):
    if registration.get('workload')=='navier-stokes-theory':
        return {f'window_{offset:05d}':offset for offset in range(0,
            registration['budget']['max_agent_seconds'],registration['analysis_window_seconds'])}
    return registration['arrival_offsets']


def cite(root, evidence):
    root=Path(root).resolve()
    path=(root/evidence['path']).resolve()
    if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
        raise ValueError('Evidence must be an existing file inside the rollout')
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=evidence['sha256']:
        raise ValueError('Evidence hash changed')
    quote=evidence['quote']
    if not isinstance(quote,str) or len(quote.strip())<8 or quote not in raw.decode(errors='replace'):
        raise ValueError('Evidence quote is missing or too short')
    return {'path':str(path.relative_to(root)),'sha256':evidence['sha256'],'quote':quote}


def validate(root, packet, registration):
    actors=set(registration['plan']['natural'])
    batches=list(analysis_windows(registration))
    if packet.get('registration_id')!=registration['identifier']:
        raise ValueError('Annotations belong to another rollout')
    if not packet.get('reviewer') or packet.get('evidence_level')!='observational':
        raise ValueError('A named observational reviewer is required; causal labels need intervention evidence')
    seen=set();events=[]
    for row in packet.get('events',[]):
        if row['id'] in seen:raise ValueError('Duplicate annotation identifier')
        seen.add(row['id'])
        if row['kind'] not in KINDS or row['actor'] not in actors or row['target'] not in actors:
            raise ValueError('Unknown event or participant')
        if row['actor']==row['target']:raise ValueError('Cross-member event requires distinct participants')
        if row['window'] not in batches or not row.get('work_item'):
            raise ValueError('A registered window and work item are required')
        if row.get('reviewed') is not True:raise ValueError('Unreviewed candidates cannot enter structural findings')
        evidence=[cite(root,item) for item in row['evidence']]
        if row['kind'] in ADOPTIONS|{'handoff_adopted'} and len(evidence)<2:
            raise ValueError('Adoption needs separately cited proposal and actual action')
        if row['kind'] in ADOPTIONS|{'handoff_adopted'}:
            if not row.get('proposal_reference') or not row.get('action_reference'):
                raise ValueError('Proposal and subsequent action references are required')
            if row['proposal_reference']==row['action_reference']:
                raise ValueError('Proposal alone cannot prove adoption')
            if (evidence[0]['path'],evidence[0]['quote'])==(evidence[1]['path'],evidence[1]['quote']):
                raise ValueError('Two copies of the same evidence cannot prove adoption')
            for name in ('proposal_reference','action_reference'):
                path,separator,line=row[name].rpartition(':')
                if not separator or not line.isdigit() or int(line)<1:
                    raise ValueError('References require path:line')
                cited=[item for item in evidence if item['path']==path]
                lines=(Path(root)/path).read_text().splitlines() if cited else []
                if int(line)>len(lines) or not any(item['quote'] in lines[int(line)-1] for item in cited):
                    raise ValueError('Proposal or action reference is not supported by a cited line')
            before=datetime.fromisoformat(row['proposal_at']);after=datetime.fromisoformat(row['action_at'])
            if before.tzinfo is None or after.tzinfo is None or before>=after:
                raise ValueError('Adoption requires ordered, timezone-aware proposal and action times')
        if not isinstance(row.get('sequence'),int) or row['sequence']<0:
            raise ValueError('A source-event sequence is required')
        events.append({**row,'evidence':evidence})
    ordered=sorted(events,key=lambda r:(batches.index(r['window']),r['sequence'],r['id']))
    prior={}
    for row in ordered:
        if row.get('feedback_reference'):
            feedback=prior.get(row['feedback_reference'])
            if not feedback or feedback['kind']!='feedback' or feedback['actor']!=row['actor']:
                raise ValueError('Reallocation must cite earlier feedback received by this member')
        prior[row['id']]=row
    return ordered


def components(edges):
    neighbors=defaultdict(set)
    for a,b in edges:neighbors[a].add(b);neighbors[b].add(a)
    result=[];left=set(neighbors)
    while left:
        group=set();stack=[min(left)]
        while stack:
            node=stack.pop()
            if node in group:continue
            group.add(node);stack.extend(neighbors[node]-group)
        left-=group;result.append(sorted(group))
    return sorted(result)


def summarize(root, packet, registration):
    events=validate(root,packet,registration)
    actors=set(registration['plan']['natural']);n=len(actors)
    frames=[];changes=[];previous_edges=set();previous_groups=[];previous_roles=set()
    accumulated=defaultdict(list)
    for window in analysis_windows(registration):
        current=[r for r in events if r['window']==window]
        adoptions=[r for r in current if r['kind'] in ADOPTIONS]
        edges={(r['actor'],r['target']) for r in adoptions}
        by_actor=defaultdict(list)
        for row in adoptions:by_actor[row['actor']].append(row)
        roles={a for a,rows in by_actor.items() if len({r['target'] for r in rows})>=2}
        groups=components(edges)
        for a in sorted(roles-previous_roles):
            changes.append({'window':window,'kind':'coordination_role_observed','actor':a,
                            'scope':'Window-level coordination; sustained orchestrator criteria are separate.'})
        for a in sorted(previous_roles-roles):
            explicit=any(r['actor']==a and r['kind']=='role_ended' for r in current)
            changes.append({'window':window,'kind':'role_end_reported' if explicit else 'role_not_observed',
                            'actor':a,'scope':'Explicitly reviewed ending.' if explicit else 'Absence may be inactivity or missing follow-up, not dissolution.'})
        for group in groups:
            predecessors=[g for g in previous_groups if set(g)&set(group)]
            if len(predecessors)>=2:
                changes.append({'window':window,'kind':'observed_components_merged','before':predecessors,'after':group})
        for group in previous_groups:
            successors=[g for g in groups if set(g)&set(group)]
            if len(successors)>=2:
                changes.append({'window':window,'kind':'observed_components_split','before':group,'after':successors})
        for row in current:
            accumulated[row['actor']].append(row)
            if row['kind']=='handoff_adopted':
                changes.append({'window':window,'kind':'role_handoff_adopted','from':row['actor'],
                                'to':row['target'],'annotation':row['id']})
        union=edges|previous_edges
        frames.append({'window':window,'coordination_edges':[list(e) for e in sorted(edges)],
            'groups':groups,'coordinating_members':sorted(roles),
            'peer_coverage':{a:len({r['target'] for r in rows})/(n-1) for a,rows in by_actor.items()},
            'edge_turnover_from_previous':len(edges^previous_edges)/len(union) if union else None,
            'annotation_ids':[r['id'] for r in current],
            'review_status':'reviewed' if window in packet.get('reviewed_windows',[]) else 'incomplete'})
        previous_edges,previous_groups,previous_roles=edges,groups,roles
    candidates=[]
    for actor,rows in accumulated.items():
        adopted=[r for r in rows if r['kind'] in ADOPTIONS]
        targets={r['target'] for r in adopted};windows={r['window'] for r in adopted}
        items={r['work_item'] for r in adopted}
        feedback={r['id'] for r in rows if r['kind']=='feedback'}
        cycles=[r for r in adopted if r['kind']=='reallocation_adopted' and r.get('feedback_reference') in feedback]
        times=[datetime.fromisoformat(r['action_at']) for r in adopted]
        span=(max(times)-min(times)).total_seconds() if times else 0
        sufficient_span=(span>=registration.get('criteria',{}).get('temporal_minimum_span_seconds',0))
        if len(targets)>=2 and len(windows)>=2 and len(items)>=3 and cycles and sufficient_span:
            candidates.append({'actor':actor,'peers':sorted(targets),'coverage':len(targets)/(n-1),
                'windows':[w for w in analysis_windows(registration) if w in windows],
                'work_items':sorted(items),'feedback_cycles':[r['id'] for r in cycles],
                'adopted_action_span_seconds':span,
                'evidence_level':'observational','causally_validated':False})
    complete=set(packet.get('reviewed_windows',[]))==set(analysis_windows(registration))
    return {'registration_id':registration['identifier'],'evidence_level':'observational',
        'reviewer':packet['reviewer'],'review_complete':complete,'frames':frames,'changes':changes,
        'orchestrator_candidates':candidates,'validated_annotations':events,
        'scope':'Changes in reviewed coordination relationships. Components are graph summaries, not proof of social groups. No causal effect or performance benefit is inferred.',
        'no_structure_claim_permitted':complete and not events and packet.get('all_actor_evidence_complete') is True}
