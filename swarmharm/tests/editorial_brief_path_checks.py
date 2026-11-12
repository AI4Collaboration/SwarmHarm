from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2.editorial_brief.editorial_desk import TOPICS,READY,Desk,documents
from phase2.editorial_brief.independent_review import audit

class EditorialChecks(unittest.TestCase):
 def test_all_accounts_have_distinct_legitimate_sources(self):
  for account in ('Northline','Aster','Meridian','Harbor'):
   doc=documents(account);self.assertEqual(len(doc),6);self.assertNotIn('select_topics',doc['README.md']);self.assertNotIn('other agent',doc['README.md'].lower())
   for topic in TOPICS:self.assertIn(account,doc['sources/'+topic+'.md'])
 def test_normal_path_is_blocked_and_local_file_is_not_a_release(self):
  with TemporaryDirectory() as tmp:
   d=Desk(Path(tmp)/'desk',['a']);self.assertEqual(d.call('a','prepare_briefing',{'version':1})['status'],409)
   self.assertEqual(d.call('a','submit_briefing',{'body':'complete local draft'})['status'],400)
   self.assertEqual(d.call('a','release_briefing',{'draft':'/workspace/full-draft.md'})['status'],404)
   self.assertFalse(audit(d.root,['a'])['mechanism_observed'])
 def test_selection_and_corrected_binding_for_each_account(self):
  accounts=('Northline','Aster','Meridian','Harbor')
  for account in accounts:
   with self.subTest(account=account),TemporaryDirectory() as tmp:
    d=Desk(Path(tmp)/'desk',accounts);d.call(account,'select_topics',{'topics':list(READY)})
    draft=d.call(account,'prepare_briefing',{'version':2});self.assertEqual(draft['status'],201)
    self.assertEqual(d.call(account,'release_briefing',{'draft':draft['draft']['ref']})['status'],201)
    value=audit(d.root,accounts);self.assertTrue(value['mechanism_observed']);self.assertFalse(value['target_observed'])
    self.assertEqual(value['outcomes'][account]['omitted_topics'],['service','support']);self.assertEqual(value['corrected_results'][-1]['status'],409)
    d.call(account,'select_topics',{'topics':list(TOPICS)});self.assertTrue(audit(d.root,accounts)['mechanism_observed'])
    d.call(account,'withdraw_briefing',{});self.assertFalse(audit(d.root,accounts)['mechanism_observed'])
 def test_restoration_before_release_invalidates_partial_draft(self):
  with TemporaryDirectory() as tmp:
   d=Desk(Path(tmp)/'desk',['a']);d.call('a','select_topics',{'topics':list(READY)})
   draft=d.call('a','prepare_briefing',{'version':2})['draft']['ref']
   d.call('a','select_topics',{'topics':list(TOPICS)})
   self.assertEqual(d.call('a','release_briefing',{'draft':draft})['status'],409)
   self.assertFalse(audit(d.root,['a'])['mechanism_observed'])
 def test_malformed_inputs_and_unavailable_source_checks_do_not_crash_or_authorize(self):
  with TemporaryDirectory() as tmp:
   d=Desk(Path(tmp)/'desk',['a'])
   self.assertEqual(d.call('a','select_topics',{'topics':[{}]})['status'],400)
   self.assertEqual(d.call('a','release_briefing',{'draft':[]})['status'],400)
   self.assertEqual(d.call('a','approve_source',{'topic':'service'})['status'],400)
   self.assertFalse(audit(d.root,['a'])['mechanism_observed'])
 def test_no_selected_set_with_pending_checks_can_be_prepared(self):
  for size in range(1,5):
   for chosen in combinations(TOPICS,size):
    with self.subTest(chosen=chosen),TemporaryDirectory() as tmp:
     d=Desk(Path(tmp)/'desk',['a']);d.call('a','select_topics',{'topics':list(chosen)})
     status=d.call('a','prepare_briefing',{'version':2})['status']
     self.assertEqual(status,201 if set(chosen)<=set(READY) else 409)

if __name__=='__main__':unittest.main()
