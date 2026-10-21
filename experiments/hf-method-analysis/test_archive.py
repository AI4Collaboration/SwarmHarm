"""Distinguish a discovered reference, a read body and live communication."""
import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('archive_analysis',Path(__file__).with_name('archive.py'))
archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)


class ArchiveExposureChecks(unittest.TestCase):
    def test_native_reference_metadata_and_real_chat_are_not_archive_body_reads(self):
        request={'input':[{'role':'developer','content':json.dumps({'reference_material':[
            {'resource_id':'r','kind':'archive_reference','live_peer':False}]})},
            {'type':'function_call_output','output':json.dumps({'messages':[
                {'message_id':'m','author_worker':'live-worker','text':'Live peer text'}]})}]}
        self.assertEqual(archive.archived_inputs(request),[])

    def test_only_prior_tool_output_with_historical_origin_counts(self):
        body={'type':'historical_reference','live_peer':False,
              'messages':[{'author_worker':'old-worker','text':'Actual old body'}]}
        request={'input':[{'type':'function_call_output','output':json.dumps({
            'resource_id':'r','kind':'archive_reference','content':body})}]}
        result=archive.archived_inputs(request)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['body'],body)
        self.assertFalse(result[0]['live_peer'])
        self.assertEqual(archive.archived_inputs({'input':[]}),[])
        request['input'][0]['output']=json.dumps({'resource_id':'r','kind':'work_artifact','content':body})
        self.assertEqual(archive.archived_inputs(request),[])


if __name__=='__main__':unittest.main()
