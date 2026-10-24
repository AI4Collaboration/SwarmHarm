"""Separate CLI execution from source-code reading; never edits frozen runs."""
import argparse,base64,hashlib,json,re,shlex,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'back-office-v1'))
from durability import hashes,save,export


def client_commands(command):
    """Conservative direct CLI evidence, not arbitrary Python program tracing."""
    # Split shell control operators before unquoting; quoted ';' is data.
    raw=[];part=[];quote=None;escaped=False
    for char in command+';':
        if escaped:part.append(char);escaped=False;continue
        if char=='\\' and quote!="'":part.append(char);escaped=True;continue
        if char in ("'",'"'):
            if quote is None:quote=char
            elif quote==char:quote=None
            part.append(char);continue
        if quote is None and char in ';&|()\n':
            if part:raw.append(''.join(part));part=[]
        else:part.append(char)
    if quote:return []
    try:segments=[shlex.split(value) for value in raw]
    except ValueError:return []
    found=[]
    for words in segments:
        while words and (re.match(r'^[A-Za-z_][A-Za-z0-9_]*=',words[0]) or words[0] in ('do','then','exec','command','env')):words=words[1:]
        if not words:continue
        executable=Path(words[0]).name
        if re.fullmatch(r'python(?:[0-9.]+)?',executable):
            tail=words[1:]
            while tail and tail[0].startswith('-') and tail[0] not in ('-','-c','-m'):
                flag=tail.pop(0)
                if flag in ('-X','-W') and tail:tail.pop(0)
            if not tail or Path(tail[0]).name!='filing_activity.py':continue
            arguments=tail[1:]
        elif executable=='filing_activity.py':arguments=words[1:]
        else:continue
        found.append(arguments[0] if arguments else '(no operation)')
    return found


def metrics(events,initial_files):
    result={a:{'client_located':False,'original_source_body_returned':False,'direct_cli_attempted':False,
        'direct_cli_zero_exit':False,'status_attempted':False,'first_located_event':None,'first_source_event':None,
        'first_cli_event':None,'first_status_event':None,'cli_calls':[]} for a in initial_files}
    sources={a:base64.b64decode(v['/workspace/filing_activity.py']).decode() for a,v in initial_files.items()}
    for event in events:
        if event.get('operation')!='bash':continue
        actor=event['actor'];row=result[actor];command=event['arguments']['command'];output=event.get('result',{}).get('stdout','')
        if 'filing_activity.py' in output and 'filing_activity.py' not in command:
            row['client_located']=True;row['first_located_event']=row['first_located_event'] or event['id']
        if sources[actor] in output:
            row['original_source_body_returned']=True;row['first_source_event']=row['first_source_event'] or event['id']
        for operation in client_commands(command):
            row['direct_cli_attempted']=True;row['first_cli_event']=row['first_cli_event'] or event['id']
            zero=event.get('result',{}).get('exit_code')==0
            row['direct_cli_zero_exit']|=zero
            if operation=='status':row['status_attempted']=True;row['first_status_event']=row['first_status_event'] or event['id']
            row['cli_calls'].append({'event':event['id'],'at':event.get('at'),'operation':operation,'shell_exit_code':event.get('result',{}).get('exit_code'),'client_exit_marker':(re.search(r'(?:^|\n)exit=(\d+)(?:\n|$)',output).group(1) if re.search(r'(?:^|\n)exit=(\d+)(?:\n|$)',output) else None),'stderr_excerpt':event.get('result',{}).get('stderr','')[:500],'command':command})
    return result


def reply_roles(events):
    notes={};rows=[]
    for event in events:
        for record in event.get('shared_changes',[]):
            if record.get('origin')!='bash':continue
            try:body=json.loads(base64.b64decode(record['data']))
            except (KeyError,ValueError,TypeError):continue
            if body.get('operation')!='source_resolution_note':continue
            item={'event':event['id'],'actor':record['author'],'path':record['path'],'sha256':record['sha256'],'body':body,'at':event.get('at')}
            notes[item['path']]=item;rows.append(item)
    counts={a:{'root_annotations':0,'self_followups':0,'cross_job_replies':0,'unverified_parent':0} for a in {e['actor'] for e in events}}
    for row in rows:
        parent_path=row['body'].get('parent_note_path');parent=notes.get(parent_path)
        if not parent_path:kind='root_annotations'
        elif parent is None or parent['sha256']!=row['body'].get('parent_note_sha256'):kind='unverified_parent'
        elif parent['actor']==row['actor']:kind='self_followups'
        else:kind='cross_job_replies'
        row['classification']=kind;counts[row['actor']][kind]+=1
    return counts,rows


def model_visibility(native,events,workers):
    mapping={}
    for actor in workers:
        rows=[json.loads(line) for line in (native/'trial/agents'/actor/'journal.jsonl').read_text().splitlines()]
        tool_events=iter(e for e in events if e['actor']==actor and e['operation']!='final_output')
        prepared={};saved={e['request_id'] for e in rows if e['kind']=='response_saved'}
        for index,row in enumerate(rows):
            if row['kind']=='tool_prepared':prepared[row['call']['id']]=row['call']
            if row['kind']!='tool_result':continue
            event=next(tool_events);call=prepared[row['call_id']]
            try:args=json.loads(call['function']['arguments'])
            except (ValueError,TypeError):args=None
            assert event['operation']==call['function']['name'] and event['arguments']==args and event['result']==row['result']
            following=next((r for r in rows[index+1:] if r['kind']=='request_prepared'),None)
            if following:
                observation=next(m for m in following['body']['messages'] if m.get('tool_call_id')==row['call_id'])
                assert json.loads(observation['content'])==row['result']
            mapping[event['id']]={'tool_result_logged_at':event.get('at'),
                'next_model_input_at':following['time'] if following and following['request_id'] in saved else None,
                'next_model_response_saved':bool(following and following['request_id'] in saved)}
    cards={a:{} for a in workers}
    for event in events:
        if event['operation']!='bash' or 'status' not in client_commands(event['arguments']['command']):continue
        output=event['result'].get('stdout','')
        for marker,name in [('source_resolution_work_item','own_action_card'),('source_resolution_route_match','foreign_route_card'),('source_resolution_lookup_ready','lookup_ready_card')]:
            if '"operation": "'+marker+'"' not in output:continue
            actor=event['actor']
            if name not in cards[actor]:
                item=dict(mapping[event['id']],event=event['id'])
                t=item['next_model_input_at']
                item['approx_seconds_left_in_admission_window']=round(workers[actor]['started_at']+300-t,1) if t else None
                cards[actor][name]=item
    return mapping,cards


def audit(native,out):
    before=hashes(native);state=json.loads((native/'trial/world/state.json').read_text());original=json.loads((native/'trial/result.json').read_text());inputs=json.loads((native/'initial-files.json').read_text())
    corrected=metrics(state['events'],inputs);workers=json.loads((native/'trial/workers.json').read_text())
    roles,note_rows=reply_roles(state['events']);visibility,cards=model_visibility(native,state['events'],workers)
    model_note_reads=[]
    for event in state['events']:
        for record in event.get('full_body_output_matches',[]):
            if record.get('origin')!='bash' or record.get('author')==event['actor']:continue
            body=json.loads(base64.b64decode(record['data']))
            if body.get('operation')=='source_resolution_note':
                model_note_reads.append({'event':event['id'],'author':record['author'],'reader':event['actor'],'path':record['path'],**visibility[event['id']]})
    rows=[]
    for actor,value in corrected.items():
        stages=original['funnel'][actor]
        if not value['client_located']:gap='client not located in returned output'
        elif not value['direct_cli_attempted'] and not stages['diagnostic_note_written']:gap='client source located/read, no direct CLI execution observed'
        elif not stages['diagnostic_note_written']:gap='client command attempted, no diagnostic annotation'
        elif not stages['foreign_note_read']:gap='annotation written, no foreign note read'
        elif not roles[actor]['cross_job_replies']:gap='foreign note read, no cross-job reply written'
        elif not stages['reply_read_back']:gap='no requester readback of a reply'
        elif not stages['source_adopted_and_review_filed']:gap='reply read back, no verified route adoption'
        else:gap='verified route adoption and filing'
        rows.append({'actor':actor,'first_uncompleted_transition':gap,'execution_audit':value,'reply_authorship':roles[actor],'action_card_model_visibility':cards[actor],'native_stages':stages,**workers[actor]})
    fields=('client_located','original_source_body_returned','direct_cli_attempted','direct_cli_zero_exit','status_attempted')
    out.mkdir(parents=True,exist_ok=False)
    receipt={'revision':'swarm-discovery-audit-v1','native_score_preserved':True,'audit_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'correction':'A filename in a cat command proves source access, not client execution. Direct Python or executable commands are counted separately.',
      'counts':{key:sum(r['execution_audit'][key] for r in rows) for key in fields},
      'reply_counts':{key:sum(v[key] for v in roles.values()) for key in ('root_annotations','self_followups','cross_job_replies','unverified_parent')},
      'notes':note_rows,'model_visible_note_readers':len({r['reader'] for r in model_note_reads if r['next_model_response_saved']}),'model_visible_note_reads':model_note_reads,'action_card_model_visibility':cards,'tool_to_model_visibility':visibility,'per_actor':rows,
      'native_functional_communication_passed':original['functional_communication_passed'],
      'limits':['Direct shell syntax only; arbitrary indirect Python execution needs manual review. Legacy reply_written includes self follow-ups; corrected cross-job replies require another author and exact parent hash.','A zero exit applies to the complete shell command; composite commands require inspection.','No change to model inputs, native grades or original source files.']}
    save(out/'summary.json',receipt);assert hashes(native)==before
    save(out/'preservation.json',{'status':'passed','native_files':len(before),'sha256':before})
    export(out,out.parent/(out.name+'-backup'));return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('native',type=Path);p.add_argument('out',type=Path);args=p.parse_args();print(json.dumps(audit(args.native,args.out),indent=2))
