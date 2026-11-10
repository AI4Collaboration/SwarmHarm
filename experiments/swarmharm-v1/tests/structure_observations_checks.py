"""Reject path-only, future-read and incomplete-source evidence in operator reviews."""
import base64
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'experiments/structure'/f'{name}.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


communication=module('communication_inventory');timeline=module('artifact_use_timeline')


def hexed(text):return ''.join('\\x%02x'%v for v in text.encode())


class StructureObservationChecks(unittest.TestCase):
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
