"""No-network regressions for durable, non-destructive future collection."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch
import run
import launch

RUNTIME=Path(__file__).parents[1]/'runtime'
def load(name):
    spec=importlib.util.spec_from_file_location('evidence_check_'+name,RUNTIME/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class Stream:
    headers={'x-request-id':'provider-header-id'}
    def __init__(self,events,fail=False):self.events=events;self.fail=fail
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def __iter__(self):
        for event in self.events:yield ('data: '+json.dumps(event)+'\n').encode()
        if self.fail:raise TimeoutError('fixture stream interrupted')

class RuntimeEvidenceChecks(unittest.TestCase):
    def transport(self):
        t=load('transport');t.configure('fixture-model','https://provider.invalid/v1',max_output_tokens=16);return t
    def test_no_model_post_is_retryable(self):
        self.assertEqual(run.BUDGET['max_transport_attempts_per_request'],1)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'error.json'
            for status in (429,500,503):
                run.save(p,{'http_status':status});self.assertFalse(run.retryable_transport_error(RuntimeError('accepted?'),p))
            p.unlink();self.assertFalse(run.retryable_transport_error(TimeoutError(),p))
    def test_launcher_rejects_wrong_harbor_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp)/'repo';candidate=repo.parent/'eval-readiness/harbor-0.24.0/bin/python'
            candidate.parent.mkdir(parents=True);candidate.touch()
            with patch.object(launch,'REPO',repo),patch.object(launch.subprocess,'run',return_value=Mock(returncode=1)):
                with self.assertRaisesRegex(RuntimeError,'exact Harbor 0.24.0'):launch.collector_python()
    def test_launcher_verifies_runtime_before_using_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp)/'repo';candidate=repo.parent/'eval-readiness/harbor-0.24.0/bin/python'
            candidate.parent.mkdir(parents=True);candidate.touch()
            with patch.object(launch,'REPO',repo),patch.object(launch.subprocess,'run',return_value=Mock(returncode=0)) as version_check:
                self.assertEqual(launch.collector_python(),str(candidate))
            self.assertEqual(version_check.call_args.args[0][0],str(candidate))
            self.assertIn('0.24.0',version_check.call_args.args[0][2])
    def test_recovery_retains_unknown_requests_and_tolerates_torn_append(self):
        t=self.transport()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'0001.journal.jsonl').write_text('{"kind":"request_unknown","local_request_id":"fixture"}\n{"unfinished"')
            self.assertEqual(t.request_outcome(p,'0001')['kind'],'request_unknown')
            self.assertEqual(t.request_outcome(p,'0001')['local_request_id'],'fixture')
    def test_durable_terminal_response_reconciles_missing_final_journal_append(self):
        t=self.transport()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);t.save(p/'0001.response.json',{'id':'known','status':'incomplete'})
            outcome=t.request_outcome(p,'0001')
            self.assertEqual(outcome['kind'],'response_saved');self.assertEqual(outcome['provider_response_id'],'known')
    def test_definitive_rejection_is_terminal_for_recovery(self):
        t=self.transport()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);t.atomic.append_jsonl(p/'0001.journal.jsonl',{'kind':'request_rejected','http_status':403})
            self.assertEqual(t.request_outcome(p,'0001')['kind'],'request_rejected')
    def test_partial_stream_and_received_identity_survive_timeout(self):
        t=self.transport();stream=Stream([{'type':'response.created','response':{'id':'generation-observed'}},{'type':'response.output_text.delta','delta':'partial'}],True)
        with tempfile.TemporaryDirectory() as tmp,patch.object(t,'key',return_value='fixture-secret'),patch.object(t.guardrails,'open_url',return_value=stream) as opening:
            p=Path(tmp)
            with self.assertRaises(TimeoutError):t.call({},p,'0001')
            opening.assert_called_once()
            frames=[json.loads(s) for s in (p/'0001.stream.jsonl').read_text().splitlines()]
            self.assertEqual(len(frames),2);self.assertIn('generation-observed',frames[0]['line'])
            journal=[json.loads(s) for s in (p/'0001.journal.jsonl').read_text().splitlines()]
            self.assertEqual(journal[1]['headers']['x-request-id'],'provider-header-id');self.assertEqual(journal[-1]['kind'],'request_unknown')
            self.assertFalse((p/'0001.response.json').exists());self.assertTrue((p/'0001.request.json').exists())
    def test_ambiguous_post_cannot_be_resent_under_existing_identity(self):
        t=self.transport()
        with tempfile.TemporaryDirectory() as tmp,patch.object(t,'key',return_value='fixture-secret'),patch.object(t.guardrails,'open_url',return_value=Stream([],True)) as opening:
            p=Path(tmp)
            with self.assertRaises(TimeoutError):t.call({},p,'0001')
            before=(p/'0001.request.json').read_bytes()
            with self.assertRaisesRegex(RuntimeError,'without resending'):t.call({'input':'replacement'},p,'0001')
            opening.assert_called_once();self.assertEqual((p/'0001.request.json').read_bytes(),before)
    def test_completed_response_is_durable_before_return(self):
        t=self.transport();response={'id':'completed-id','status':'completed','model':'fixture-model','output':[]}
        with tempfile.TemporaryDirectory() as tmp,patch.object(t,'key',return_value='fixture-secret'),patch.object(t.guardrails,'open_url',return_value=Stream([{'type':'response.completed','response':response}])):
            p=Path(tmp);self.assertEqual(t.call({},p,'0001'),response)
            journal=[json.loads(s) for s in (p/'0001.journal.jsonl').read_text().splitlines()]
            self.assertEqual(journal[-1]['provider_response_id'],'completed-id');self.assertEqual(journal[-1]['kind'],'response_saved')
    def test_native_incomplete_filter_is_not_transport_failure(self):
        t=self.transport();monitor=load('response_monitor')
        response={'id':'filtered','status':'incomplete','model':'fixture-model','output':[],'incomplete_details':{'reason':'content_filter'}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(t,'key',return_value='fixture-secret'),patch.object(t.guardrails,'open_url',return_value=Stream([{'type':'response.incomplete','response':response}])):
            p=Path(tmp)
            with self.assertRaises(RuntimeError):t.call({},p,'0001')
            self.assertEqual(monitor.classify(json.loads((p/'0001.error.json').read_text()),True)['status'],'provider_filter')
            self.assertEqual(json.loads((p/'0001.response.json').read_text()),response)
    def test_failed_native_filter_is_visible_through_saved_error_wrapper(self):
        t=self.transport();monitor=load('response_monitor')
        response={'id':'filtered-failure','status':'failed','model':'fixture-model','error':{'code':'content_filter','message':'filtered'},'output':[]}
        with tempfile.TemporaryDirectory() as tmp,patch.object(t,'key',return_value='fixture-secret'),patch.object(t.guardrails,'open_url',return_value=Stream([{'type':'response.failed','response':response}])):
            p=Path(tmp)
            with self.assertRaises(RuntimeError):t.call({},p,'0001')
            self.assertEqual(monitor.classify(json.loads((p/'0001.error.json').read_text()),True)['status'],'provider_filter')
            self.assertEqual(t.request_outcome(p,'0001')['kind'],'response_saved')
    def test_token_truncation_is_not_a_filter(self):
        monitor=load('response_monitor')
        self.assertEqual(monitor.classify({'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'}})['status'],'provider_error')
    def test_stream_error_redacts_credentials_in_saved_diagnostic(self):
        t=self.transport();stream=Stream([{'type':'error','error':{'message':'bad fixture-secret','code':'bad_request'}}])
        with tempfile.TemporaryDirectory() as tmp,patch.object(t,'key',return_value='fixture-secret'),patch.object(t.guardrails,'open_url',return_value=stream):
            p=Path(tmp)
            with self.assertRaises(RuntimeError):t.call({},p,'0001')
            self.assertNotIn('fixture-secret',(p/'0001.stream.jsonl').read_text());self.assertNotIn('fixture-secret',(p/'0001.error.json').read_text())
    def test_trusted_projection_retries_only_explicit_connection_refusal(self):
        w=load('workstation')
        with tempfile.TemporaryDirectory() as tmp:
            station=object.__new__(w.Workstation);station.root=Path(tmp);station.invocations=1
            args=['docker','exec','fixture','python','-I','-c',w.SCAN]
            error=subprocess.CalledProcessError(1,args,'',"cannot connect to the Docker daemon. Is 'docker daemon' running on this host?: dial unix /fixture.sock: connect: connection refused\n")
            done=subprocess.CompletedProcess(args,0,'{}','')
            with patch.object(station,'_run_once',side_effect=[error,done]) as command,patch.object(w.time,'sleep'):
                self.assertIs(station._run(args,retry_connection_failure=True),done)
            self.assertEqual(command.call_count,2);self.assertTrue((Path(tmp)/'1/not-admitted.json').exists())
    def test_business_commands_and_ambiguous_failures_never_retry(self):
        w=load('workstation')
        with tempfile.TemporaryDirectory() as tmp:
            station=object.__new__(w.Workstation);station.root=Path(tmp);station.invocations=1
            args=['docker','exec','fixture','bash','-lc','fixture-command']
            error=subprocess.CalledProcessError(1,args,'','Cannot connect to the Docker daemon at unix:///fixture.sock. Is the docker daemon running?')
            with patch.object(station,'_run_once',side_effect=error) as command:
                with self.assertRaises(subprocess.CalledProcessError):station._run(args)
            command.assert_called_once()
            error=subprocess.CalledProcessError(1,args,'','context canceled')
            with patch.object(station,'_run_once',side_effect=error) as command:
                with self.assertRaises(subprocess.CalledProcessError):station._run(args,retry_connection_failure=True)
            command.assert_called_once()
    def test_unknown_execution_is_not_killed_and_files_remain(self):
        w=load('workstation')
        with tempfile.TemporaryDirectory() as tmp:
            station=object.__new__(w.Workstation);station.root=Path(tmp);station.name='fixture-container';station.invocations=0;station.closed=False
            process=Mock(pid=1234);process.wait.side_effect=subprocess.TimeoutExpired('fixture',30)
            with patch.object(w.subprocess,'Popen',return_value=process) as spawn:
                with self.assertRaises(w.UnknownExecution):station._run(['fixture'])
            spawn.assert_called_once();process.kill.assert_not_called();process.terminate.assert_not_called();process.send_signal.assert_not_called()
            self.assertTrue((Path(tmp)/'1/unknown.json').exists());self.assertTrue((Path(tmp)/'1/stdout').exists())
            with patch.object(w.subprocess,'Popen') as spawn:
                station.pause();station.resume();result=station.close();spawn.assert_not_called()
            self.assertTrue(result['retained']);self.assertFalse(result['removed'])
    def test_live_background_writer_prevents_registry_refresh(self):
        w=load('workstation')
        with tempfile.TemporaryDirectory() as tmp:
            station=object.__new__(w.Workstation);station.root=Path(tmp);station.name='fixture'
            snapshot={'/workspace':{},'/registry':{},'/tmp':{},'background_processes':[{'pid':8,'comm':'fixture-writer'}]}
            with patch.object(station,'_run',return_value=Mock(stdout=json.dumps(snapshot))) as command:
                with self.assertRaises(w.UnknownExecution):station.hydrate({},True)
            command.assert_called_once();self.assertIn(w.SCAN,command.call_args.args[0])
    def test_startup_failure_preserves_stderr_without_cleanup_signals(self):
        w=load('workstation');process=Mock(pid=42);process.wait.return_value=1
        def popen(args,**kwargs):kwargs['stderr'].write(b'fixture image unavailable');return process
        with tempfile.TemporaryDirectory() as tmp,patch.object(w.subprocess,'Popen',side_effect=popen) as spawn:
            with self.assertRaisesRegex(RuntimeError,'fixture image unavailable'):w.Workstation({},Path(tmp)/'evidence')
            spawn.assert_called_once();process.kill.assert_not_called();process.terminate.assert_not_called()
            self.assertTrue((Path(tmp)/'evidence/workstation.json').exists())

if __name__=='__main__':unittest.main()
