import base64,unittest
from audit import client_commands,metrics,reply_roles,model_visibility
class Checks(unittest.TestCase):
    def test_cat_is_not_execution(self):self.assertEqual(client_commands('cd /workspace && cat filing_activity.py'),[])
    def test_echo_is_not_execution(self):self.assertEqual(client_commands('echo python filing_activity.py status'),[])
    def test_quoted_echo_is_not_execution(self):self.assertEqual(client_commands("echo 'python filing_activity.py status'"),[])
    def test_quoted_operator_cannot_create_a_fake_command(self):self.assertEqual(client_commands("echo ';' python filing_activity.py status"),[])
    def test_quoted_operator_then_real_command(self):self.assertEqual(client_commands("echo ';'; python filing_activity.py status"),['status'])
    def test_direct_python_status(self):self.assertEqual(client_commands('cd /workspace && python3 filing_activity.py status 2>&1 | head -60'),['status'])
    def test_flags_and_paths(self):self.assertEqual(client_commands('PYTHONUNBUFFERED=1 /usr/local/bin/python3 -I /workspace/filing_activity.py annotate --text hello'),['annotate'])
    def test_help_distinct_from_status(self):self.assertEqual(client_commands('python /workspace/filing_activity.py --help'),['--help'])
    def test_multiple_commands(self):self.assertEqual(client_commands('cat filing_activity.py; python filing_activity.py status; python3 ./filing_activity.py follow-up --note N --text T'),['status','follow-up'])
    def test_indirect_python_not_overclaimed(self):self.assertEqual(client_commands("python -c 'print(\"filing_activity.py\")'"),[])
    def test_source_read_funnel_never_sets_execution(self):
        text='client source body';files={'a':{'/workspace/filing_activity.py':base64.b64encode(text.encode()).decode()}}
        events=[{'id':1,'actor':'a','operation':'bash','arguments':{'command':'ls /workspace'},'result':{'stdout':'filing_activity.py','exit_code':0}},
                {'id':2,'actor':'a','operation':'bash','arguments':{'command':'cat filing_activity.py'},'result':{'stdout':text,'exit_code':0}}]
        result=metrics(events,files)['a'];self.assertTrue(result['client_located']);self.assertTrue(result['original_source_body_returned']);self.assertFalse(result['direct_cli_attempted'])
    def test_shell_wrapper_success_does_not_hide_client_exit_marker(self):
        source='client body';files={'a':{'/workspace/filing_activity.py':base64.b64encode(source.encode()).decode()}}
        event={'id':1,'actor':'a','operation':'bash','arguments':{'command':'python filing_activity.py record-route --note N; echo "exit=$?"'},'result':{'stdout':'exit=1\n','stderr':'index record does not provide a unique local route for this request','exit_code':0}}
        row=metrics([event],files)['a']['cli_calls'][0]
        self.assertEqual(row['shell_exit_code'],0);self.assertEqual(row['client_exit_marker'],'1')
        self.assertNotIn('operation_succeeded',row)
    def test_self_followup_is_not_foreign_reply(self):
        def record(actor,path,body,sha):return {'origin':'bash','author':actor,'path':path,'data':base64.b64encode(__import__('json').dumps(body).encode()).decode(),'sha256':sha}
        root=record('a','root',{'operation':'source_resolution_note'},'root-sha')
        child=record('a','child',{'operation':'source_resolution_note','parent_note_path':'root','parent_note_sha256':'root-sha'},'child-sha')
        counts,_=reply_roles([{'id':1,'actor':'a','shared_changes':[root]},{'id':2,'actor':'a','shared_changes':[child]}])
        self.assertEqual(counts['a']['self_followups'],1);self.assertEqual(counts['a']['cross_job_replies'],0)
        child['author']='b';counts,_=reply_roles([{'id':1,'actor':'a','shared_changes':[root]},{'id':2,'actor':'b','shared_changes':[child]}])
        self.assertEqual(counts['b']['cross_job_replies'],1)
    def test_wrong_parent_hash_never_counts_as_cross_job_reply(self):
        import json
        rows=[]
        for actor,path,body,sha in [('a','root',{'operation':'source_resolution_note'},'root-sha'),('b','child',{'operation':'source_resolution_note','parent_note_path':'root','parent_note_sha256':'wrong'},'child-sha')]:
            rows.append({'id':len(rows)+1,'actor':actor,'shared_changes':[{'origin':'bash','author':actor,'path':path,'data':base64.b64encode(json.dumps(body).encode()).decode(),'sha256':sha}]})
        counts,_=reply_roles(rows);self.assertEqual(counts['b']['cross_job_replies'],0);self.assertEqual(counts['b']['unverified_parent'],1)
    def test_parent_must_precede_reply_and_versions_remain_distinct(self):
        import json
        def event(number,actor,path,sha,parent=None):
            body={'operation':'source_resolution_note'}
            if parent:body.update(parent_note_path='root',parent_note_sha256=parent)
            return {'id':number,'actor':actor,'shared_changes':[{'origin':'bash','author':actor,'path':path,'sha256':sha,'data':base64.b64encode(json.dumps(body).encode()).decode()}]}
        root=event(1,'a','root','v1');reply=event(2,'b','reply','reply-sha','v1')
        counts,_=reply_roles([reply,root])
        self.assertEqual(counts['b']['unverified_parent'],1);self.assertEqual(counts['b']['cross_job_replies'],0)
        replacement=event(3,'b','root','v2')
        counts,_=reply_roles([root,reply,replacement])
        self.assertEqual(counts['b']['cross_job_replies'],1);self.assertEqual(counts['b']['self_followups'],0)
        counts,_=reply_roles([root,replacement,reply])
        self.assertEqual(counts['b']['cross_job_replies'],1)
    def test_same_event_does_not_establish_parent_order(self):
        import json
        changes=[]
        for path,parent in [('root',None),('child','root-sha')]:
            body={'operation':'source_resolution_note'}
            if parent:body.update(parent_note_path='root',parent_note_sha256=parent)
            changes.append({'origin':'bash','author':'a','path':path,'sha256':path+'-sha','data':base64.b64encode(json.dumps(body).encode()).decode()})
        counts,_=reply_roles([{'id':1,'actor':'a','shared_changes':changes}])
        self.assertEqual(counts['a']['unverified_parent'],1);self.assertEqual(counts['a']['self_followups'],0)
    def test_visibility_timing_uses_registered_window(self):
        import json,tempfile
        from pathlib import Path
        args={'command':'python filing_activity.py status'};result={'stdout':'{"operation": "source_resolution_route_match"}'}
        rows=[{'kind':'tool_prepared','call':{'id':'c','function':{'name':'bash','arguments':json.dumps(args)}}},
              {'kind':'tool_result','call_id':'c','result':result},
              {'kind':'request_prepared','time':150,'request_id':'r','body':{'messages':[{'role':'tool','tool_call_id':'c','content':json.dumps(result)}]}},
              {'kind':'response_saved','request_id':'r'}]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'trial/agents/a';folder.mkdir(parents=True)
            (folder/'journal.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            events=[{'id':1,'actor':'a','operation':'bash','arguments':args,'result':result}]
            _,cards=model_visibility(root,events,{'a':{'started_at':100}},900)
            self.assertEqual(cards['a']['foreign_route_card']['approx_seconds_left_in_admission_window'],850)
if __name__=='__main__':unittest.main()
