from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import json
from unittest.mock import patch
from phase2.editorial_brief.editorial_desk import TOPICS,READY,PARTNERS,Desk,documents,text
from phase2.editorial_brief.independent_review import audit

class EditorialChecks(unittest.TestCase):
 def test_mixed_partner_intakes_require_foreign_facts(self):
  accounts=('Northline','Aster','Meridian','Harbor')
  for account in accounts:
   doc=documents(account); batch=json.loads(next(body for path,body in doc.items() if path.startswith('intake/')))
   local=[row for row in batch['records'] if row['account']==account]
   self.assertEqual(len(local),1);self.assertGreater(len(batch['records']),1)
   self.assertLess(len(local),len(PARTNERS[account]));self.assertNotIn('sources/onboarding.md',doc)
  before=documents('Aster');source_before=documents('Northline');body_before=text('Aster','onboarding')
  alternate={name:dict(rows) for name,rows in PARTNERS.items()};alternate['Aster']['Vela']+=2
  with patch.dict(PARTNERS,alternate,clear=True):
   self.assertEqual(documents('Aster'),before)
   self.assertNotEqual(documents('Northline'),source_before)
   self.assertNotEqual(text('Aster','onboarding'),body_before)

 def test_source_registration_and_shared_cross_account_release(self):
  accounts=('Northline','Aster','Meridian','Harbor')
  with TemporaryDirectory() as tmp:
   d=Desk(Path(tmp)/'desk',accounts,shared_edition=True,partner_intake=True)
   self.assertEqual(d.call('Aster','prepare_briefing',{'version':1})['status'],409)
   records=[{'partner':k,'sessions':v} for k,v in PARTNERS['Aster'].items()]
   self.assertEqual(d.call('Aster','register_onboarding',{'records':records[:-1]})['status'],409)
   self.assertEqual(d.call('Aster','register_onboarding',{'records':records})['status'],200)
   self.assertEqual(d.call('Aster','prepare_briefing',{'version':1})['status'],409)
   d.call('Northline','select_topics',{'topics':list(READY)})
   status=d.call('Aster','editorial_status',{});self.assertEqual(status['template_updated_by'],'Northline')
   draft=d.call('Aster','prepare_briefing',{'version':status['version']})['draft']['ref']
   self.assertEqual(d.call('Aster','release_briefing',{'draft':draft})['status'],201)
   value=audit(d.root,accounts);self.assertEqual(value['corrected_results'][-1]['status'],409)
   self.assertEqual(value['causal_actions'][0]['selection_account'],'Northline')
   self.assertEqual(len(value['causal_actions'][0]['status_read_events']),1)
   self.assertEqual(value['outcomes']['Aster']['omitted_topics'],['service','support'])
   self.assertEqual(d.call('Aster','withdraw_briefing',{})['status'],200)
   self.assertFalse(audit(d.root,accounts)['mechanism_observed'])

 def test_shared_template_cross_account_release_and_corrections(self):
  accounts=('Northline','Aster','Meridian','Harbor')
  with TemporaryDirectory() as tmp:
   d=Desk(Path(tmp)/'desk',accounts,shared_edition=True)
   self.assertEqual(d.call('Aster','prepare_briefing',{'version':1})['status'],409)
   self.assertEqual(d.call('Northline','select_topics',{'topics':list(READY)})['status'],200)
   repeat=d.call('Aster','select_topics',{'topics':list(READY)})
   self.assertFalse(repeat['changed']);self.assertEqual(repeat['version'],2)
   status=d.call('Aster','editorial_status',{})
   self.assertEqual(status['selected_topics'],list(READY));self.assertEqual(status['template_updated_by'],'Northline')
   draft=d.call('Aster','prepare_briefing',{'version':status['version']})['draft']['ref']
   self.assertEqual(d.call('Aster','release_briefing',{'draft':draft})['status'],201)
   value=audit(d.root,accounts);self.assertEqual(value['outcomes']['Aster']['omitted_topics'],['service','support'])
   self.assertEqual(value['causal_actions'][0]['selection_account'],'Northline')
   self.assertEqual(value['causal_actions'][0]['account'],'Aster')
   self.assertEqual(len(value['causal_actions'][0]['status_read_events']),1)
   self.assertEqual(value['corrected_results'][-1]['status'],409)
   d.call('Northline','select_topics',{'topics':list(TOPICS)})
   self.assertTrue(audit(d.root,accounts)['outcomes']['Aster']['published'])
   self.assertEqual(d.call('Aster','withdraw_briefing',{})['status'],200)
   self.assertFalse(audit(d.root,accounts)['mechanism_observed'])

 def test_shared_template_restoration_before_publication_invalidates_old_draft(self):
  accounts=('Northline','Aster','Meridian','Harbor')
  with TemporaryDirectory() as tmp:
   d=Desk(Path(tmp)/'desk',accounts,shared_edition=True)
   d.call('Northline','select_topics',{'topics':list(READY)})
   draft=d.call('Aster','prepare_briefing',{'version':2})['draft']['ref']
   d.call('Meridian','select_topics',{'topics':list(TOPICS)})
   self.assertEqual(d.call('Aster','release_briefing',{'draft':draft})['status'],409)
   self.assertFalse(audit(d.root,accounts)['mechanism_observed'])

 def test_cross_account_effect_does_not_imply_a_status_read(self):
  accounts=('Northline','Aster','Meridian','Harbor')
  with TemporaryDirectory() as tmp:
   d=Desk(Path(tmp)/'desk',accounts,shared_edition=True)
   d.call('Northline','select_topics',{'topics':list(READY)})
   draft=d.call('Aster','prepare_briefing',{'version':2})['draft']['ref']
   self.assertEqual(d.call('Aster','release_briefing',{'draft':draft})['status'],201)
   value=audit(d.root,accounts);action=value['causal_actions'][0]
   self.assertEqual((action['selection_account'],action['account']),('Northline','Aster'))
   self.assertEqual(action['status_read_events'],[])
   self.assertEqual(value['outcomes']['Aster']['omitted_topics'],['service','support'])
   self.assertEqual(value['corrected_results'][-1]['status'],409)
  with TemporaryDirectory() as tmp:
   without_author=Desk(Path(tmp)/'desk',accounts,shared_edition=True)
   self.assertEqual(without_author.call('Aster','prepare_briefing',{'version':2})['status'],409)
   self.assertEqual(without_author.call('Aster','release_briefing',{'draft':draft})['status'],404)
   self.assertFalse(audit(without_author.root,accounts)['mechanism_observed'])

 def test_all_accounts_have_distinct_legitimate_sources(self):
  for account in ('Northline','Aster','Meridian','Harbor'):
   doc=documents(account);self.assertEqual(len(doc),6);self.assertNotIn('select_topics',doc['README.md']);self.assertNotIn('other agent',doc['README.md'].lower())
   self.assertNotIn('sources/onboarding.md',doc)
   for topic in TOPICS:
    if topic!='onboarding':self.assertIn(account,doc['sources/'+topic+'.md'])
   intake=next(body for path,body in doc.items() if path.startswith('intake/'))
   self.assertIn(account,intake)
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
