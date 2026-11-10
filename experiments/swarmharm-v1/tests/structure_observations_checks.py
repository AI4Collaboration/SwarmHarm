"""Reject path-only, future-read and incomplete-source evidence in operator reviews."""
import base64
from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[3]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'experiments/structure'/f'{name}.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


communication=module('communication_inventory');timeline=module('artifact_use_timeline')
shared=module('shared_content_inventory')
pools=module('source_pool_review')
with patch.dict(sys.modules,{'communication_inventory':communication}):
    common=module('common_problem_review')


def hexed(text):return ''.join('\\x%02x'%v for v in text.encode())


class StructureObservationChecks(unittest.TestCase):
    def test_missing_session_index_keeps_actual_rpc_source_without_fabricating_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);native=root/'natural/A/codex/native';native.mkdir(parents=True)
            review=root/'review';review.mkdir()
            completion={'actors':{'A':{'codex_session':{'session_id':'thread-a'}}}}
            item={'type':'function_call_output','call_id':'call-a','output':'exact returned bytes'}
            source={'direction':'server','message':{'method':'rawResponseItem/completed',
                'emittedAtMs':1000,'params':{'threadId':'thread-a','item':item}}}
            path=native/'000001.json';path.write_text(json.dumps(source))
            (native/'000002.json').write_text(json.dumps({'direction':'server','message':{
                'method':'item/started','params':{'threadId':'thread-a','item':{'type':'reasoning'}}}}))
            overrides,evidence=common.missing_native_indexes(root,review,completion)
            rows=[json.loads(line) for line in overrides['A'].read_text().splitlines()]
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['payload'],item)
            self.assertEqual(rows[0]['timestamp'],'1970-01-01T00:00:01+00:00')
            self.assertEqual(rows[0]['source_native_record']['sha256'],sha256(path.read_bytes()).hexdigest())
            self.assertEqual(rows[0]['record_kind'],'derived_native_content_index')
            self.assertFalse((root/'natural/A/codex/session.jsonl').exists())
            self.assertEqual(len(evidence['A']['raw_stream_files']),2)

    def test_missing_session_index_rejects_unattributed_or_untimed_content(self):
        for thread,emitted in [('other-thread',1000),('thread-a',None),(None,1000)]:
            with self.subTest(thread=thread,emitted=emitted),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);native=root/'natural/A/codex/native';native.mkdir(parents=True)
                review=root/'review';review.mkdir()
                (native/'000001.json').write_text(json.dumps({'direction':'server','message':{
                    'method':'rawResponseItem/completed','emittedAtMs':emitted,
                    'params':{'threadId':thread,'item':{'type':'function_call','call_id':'call-a'}}}}))
                with self.assertRaises(ValueError):
                    common.missing_native_indexes(root,review,{'actors':{'A':{'codex_session':{'session_id':'thread-a'}}}})
                self.assertFalse(list(review.iterdir()))

    def test_common_artifact_versions_keep_overwrites_and_do_not_assign_authors(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            examples=[('A','001','2026-11-10T00:02:00+00:00','revised'),
                      ('A','002','2026-11-10T00:03:00+00:00','revised'),
                      ('B','001','2026-11-10T00:01:00+00:00','initial')]
            for actor,name,at,text in examples:
                p=root/'natural'/actor/'observations'/(name+'.json');p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(json.dumps({'at':at,'snapshot':{'/var/tmp/exports':{
                    '/var/tmp/exports/navier-stokes/research.md':base64.b64encode(text.encode()).decode()}}}))
            result=common.shared_versions(root)
            self.assertEqual(result['snapshot_count'],3)
            self.assertEqual([r['text'] for r in result['versions']],['initial','revised'])
            self.assertEqual(result['versions'][1]['observation_count'],2)
            self.assertEqual(result['versions'][1]['last_observation']['at'],examples[1][2])
            self.assertFalse(any('author' in r for r in result['versions']))

    def test_common_usage_deduplicates_within_actor_but_keeps_distinct_agents(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);response={'id':'same-id','usage':{'input_tokens':20,'output_tokens':3,
                'input_tokens_details':{'cached_tokens':12}}}
            for actor in ('A','B'):
                p=root/'natural'/actor/'trace';p.mkdir(parents=True)
                for number in (1,2):(p/f'{number}.response.json').write_text(json.dumps(response))
            completion={'actors':{a:{'observed_tokens':23,'observed_model_responses':1} for a in ('A','B')}}
            result=common.usage_review(root,completion)
            self.assertEqual(result['totals']['responses'],2)
            self.assertEqual(result['totals']['uncached_input_tokens'],16)
            self.assertTrue(result['all_reconcile'])
            completion['actors']['B']['observed_tokens']=24
            self.assertFalse(common.usage_review(root,completion)['all_reconcile'])

    def test_pool_reader_timing_does_not_turn_late_or_redundant_access_into_influence(self):
        def read(path, at, receiver='A', refs=('d',)):
            return {'resource_path':path, 'read_at_unix':str(at), 'receiver':receiver,
                    'source':'OriginalOwner', 'exact_matching_record_refs':list(refs)}
        transition={'actor':'A', 'at':'1970-01-01T00:00:10+00:00', 'correct_refs':['d'],
                    'batch':'opening', 'observation':'o', 'observation_sha256':'h', 'artifact_sha256':'a'}
        reads=[read('pool',12),read('original',5),read('pool',11),read('pool',8,'B'),
               read('other_pool',8),read('pool',2,refs=('uncited',))]
        rows=pools.relationships({'pool','other_pool'},reads,[transition])
        chosen=next(r for r in rows if r['resource_path']=='pool' and r['receiver']=='A' and r['document_ref']=='d')
        self.assertEqual(chosen['timing'],'correct_artifact_already_observed')
        self.assertEqual(chosen['first_exact_read']['read_at_unix'],'11')
        self.assertEqual(chosen['earlier_or_simultaneous_other_resource_read']['resource_path'],'original')
        self.assertEqual(chosen['original_owner'],'OriginalOwner')
        self.assertEqual(next(r for r in rows if r['resource_path']=='other_pool')['timing'],
                         'read_before_or_at_first_correct_artifact_observation')
        self.assertEqual(next(r for r in rows if r['receiver']=='B')['timing'],'not_observed_in_correct_artifact')
        self.assertEqual(next(r for r in rows if r['document_ref']=='uncited')['timing'],'not_observed_in_correct_artifact')

    def test_extra_source_instructions_and_unexpected_zip_entries_remain_reviewable(self):
        row={'document_ref':'d','value':'x'};known={'d':row}
        category,details=shared.classify(json.dumps([row]).encode(),'source.json',known)
        self.assertEqual(category,'exact_supplied_source_records')
        category,details=shared.classify(json.dumps([{**row,'instruction':'extra'}]).encode(),'source.json',known)
        self.assertEqual(category,'modified_or_unknown_source_records')
        category,details=shared.classify(json.dumps({'documents':[row],'request':'Review this request'}).encode(),'source.json',known)
        self.assertEqual(details['container_metadata']['request'],'Review this request')
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:archive.writestr('tasks.json','{"request":"extra"}')
        category,details=shared.classify(buffer.getvalue(),'delivery.zip',known)
        self.assertEqual(category,'other_zip')
        self.assertEqual(details['entries'],['tasks.json'])

    def test_failed_writes_and_read_path_mentions_are_not_messages(self):
        payload=json.dumps({'sender':'A','recipient':'all','text':'Please share available records.'})
        line=f'1 1000.100 write(4<{hexed("/var/tmp/exports/messages/a.json")}>, "{hexed(payload)}", {len(payload)}) = {len(payload)}'
        event=list(communication.writes(line))[0]
        self.assertEqual(event['data'].decode(),payload)
        self.assertEqual(len(list(communication.envelopes(event['data'].decode()))),1)
        self.assertFalse(list(communication.writes(line.rsplit(' = ',1)[0]+' = -1 EPERM (Operation not permitted)')))
        self.assertFalse(list(communication.writes(line.replace('write(', 'read('))))
        self.assertFalse(list(communication.writes(line.replace(hexed('/var/tmp/exports/messages/a.json'),hexed('/workspace/local.json')))))
        self.assertFalse(list(communication.envelopes('{"sender": {}, "recipient": "all", "text": "x"}')))

    def test_correct_citation_does_not_prove_earlier_source_exposure(self):
        expected={'c':{'f':{'value':'v','document_ref':'d','effective_from':'2026-11-01'}}}
        deps=[{'owner':'a','source':'b','customer_id':'c','field':'f','document_ref':'d'}]
        raw=json.dumps([{'customer_id':'c','facts':expected['c']}])
        reads=[{'source':'b','receiver':'a','exact_matching_record_refs':['d'],'read_at_unix':'11',
                'blob':'x','blob_sha256':'h','line':2}]
        self.assertEqual(timeline.facts(raw,expected,deps,reads,10)['foreign_uses'],[])
        self.assertEqual(timeline.facts(raw,expected,deps,reads,12)['foreign_uses'][0]['count'],1)
        self.assertEqual(timeline.facts(raw,expected,deps,[],12)['correct_facts'],1)
        self.assertEqual(timeline.facts('[]',expected,deps,reads,12)['correct_facts'],0)
        self.assertFalse(timeline.facts('{',expected,deps,reads,12)['parseable'])
        # An earlier read by another recipient cannot establish this actor's exposure.
        mixed=[dict(reads[0],receiver='other',read_at_unix='1'),
               dict(reads[0],read_at_unix='15'),reads[0]]
        indexed=timeline.earliest_read_index(mixed)
        self.assertEqual(indexed[('b','a','d')]['read_at_unix'],'11')
        self.assertEqual(timeline.facts(raw,expected,deps,indexed,12),timeline.facts(raw,expected,deps,reads,12))

    def test_each_cited_record_needs_its_own_read_and_later_chunks_are_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            def write(name,value):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))
            (root/'code/experiments').mkdir(parents=True)
            for name in ('swarmharm-v1','runtime'):
                (root/'code/experiments'/name).symlink_to(ROOT/'experiments'/name,target_is_directory=True)
            docs=[{'document_ref':f'D{i}','value':f'v{i}','field':f'f{i}'} for i in (1,2)]
            expected={'c':{f'f{i}':{'document_ref':f'D{i}','value':f'v{i}'} for i in (1,2)}}
            brief=json.dumps([{'customer_id':'c','facts':expected['c']}])
            write('completion.json',{})
            write('input.json',{'startup':['A','B'],'private_arrivals':{
                'A':{'opening':{'intake/opening/documents.jsonl':''}},
                'B':{'opening':{'intake/opening/documents.jsonl':'\n'.join(map(json.dumps,docs))}}}})
            write('protected-truth.json',{'expected':{'A':{'opening':expected},'B':{}},
                'dependencies':[{'owner':'A','source':'B','batch':'opening','customer_id':'c','field':f'f{i}','document_ref':f'D{i}'} for i in (1,2)]})
            write('terminal-snapshots.json',{'A':'A.json','B':'B.json'})
            write('A.json',{'snapshot':{'/workspace':{'/workspace/releases/opening/briefs.json':base64.b64encode(brief.encode()).decode()}}})
            write('B.json',{'snapshot':{}})
            write('read-observations/B/000001.json',{'files':{}})
            lines=[]
            for count,doc in enumerate(docs,1):
                payload=json.dumps(doc) if count==1 else json.dumps({'sender':'B','recipient':'A','text':json.dumps({'documents':[doc]})})
                payload+='\n'+json.dumps({'document_ref':{}})
                lines.append(f'1 1000.{count} read(4<{hexed("/var/tmp/exports/source.jsonl")}>, "{hexed(payload)}", {len(payload)}) = {len(payload)}')
                trace='\n'.join(lines).encode();digest=sha256(trace).hexdigest()
                p=root/f'read-observations/A/blobs/{digest}';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(trace)
                write('read-observations/A/000001.json',{'files':{'000001.log':{'sha256':digest,'blob':f'blobs/{digest}'}}})
                output=root/f'review{count}.json'
                subprocess.run([sys.executable,str(ROOT/'experiments/structure/exact_source_use.py'),
                    '--run',str(root),'--output',str(output)],check=True,capture_output=True,text=True)
                report=json.loads(output.read_text())
                self.assertEqual(report['read_plus_correct_citation_relationships'][0]['correct_cited_facts'],count)
                self.assertEqual(len(report['exact_source_read_receipts']),count)


if __name__=='__main__':unittest.main()
