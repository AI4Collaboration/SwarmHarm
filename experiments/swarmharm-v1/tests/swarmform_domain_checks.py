"""Round-trip protected truth and exact authored-package checks for all domains."""
import unittest
import base64
import io
import json
from pathlib import Path
import zipfile
from hashlib import sha256
from swarmform import domain_inputs as d,fulfillment,settlement,engineering,knowledge
from phase2.workload_sources import csv_text



class DomainChecks(unittest.TestCase):
    def test_json_roundtrip_and_changed_publication(self):
        results=[]
        for domain in d.DOMAINS:
         visible,truth,manifest=d.build('november',domain);disk_truth=json.loads(json.dumps(truth))
         module,filename,_=d.descriptor(domain)
         for actor in module.SITES:
          files={}
          if domain=='Engineering':
           _,versions,_,catalog,_=engineering.source_material('november')
           files={f'releases/{b}/decoder.py':engineering.compile_reference({k:v for k,v in versions[i].items() if k in catalog[actor]}) for i,b in enumerate(module.BATCHES)}
          elif domain=='Knowledge Work':
           files={f'releases/{b}/briefs.json':knowledge.brief(truth[actor][i]) for i,b in enumerate(module.BATCHES)}
          elif domain=='Financial Analysis':
           for i,b in enumerate(module.BATCHES):
            files[f'releases/{b}/ledger.csv']=csv_text(settlement.LEDGER,[(k,*v[:-1],'|'.join(v[-1])) for k,v in truth[actor][i].items()])
           inv=visible['private_arrivals'][actor]['opening']['intake/opening/invoices.csv']
           files['releases/cash-changes.csv']=csv_text(('account','currency','cash_base_change'),[(a,c,v) for (a,c),v in settlement.cash_changes(inv,*truth[actor][-2:]).items()])
          else:
           for i,b in enumerate(module.BATCHES):
            files[f'releases/{b}/ledger.csv']=csv_text(fulfillment.LEDGER,[(k,v[0],v[1],'|'.join(v[2])) for k,v in truth[actor][i].items()])
           files['releases/changes.csv']=csv_text(('order_id','net_change'),fulfillment.changes(*truth[actor][-2:]).items())
          snapshot={'/workspace':{'/workspace/'+p:base64.b64encode(v.encode()).decode() for p,v in files.items()},'/var/tmp/exports':{}}
          outcome=d.verify_business(domain,actor,snapshot,disk_truth,visible)
          assert all(v['complete'] if isinstance(v,dict) else v for v in outcome.values()),(domain,actor,outcome)
          # Package verification must check the exact authored bytes, not just a manifest.
          if domain!='Data Analysis':
           for b in module.BATCHES:
            value=files[f'releases/{b}/{filename}'].encode();out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as archive:
             archive.writestr(filename,value);archive.writestr('manifest.json',json.dumps({'office':actor,'batch':b,'file':filename,'sha256':sha256(value).hexdigest()}))
            snapshot['/var/tmp/exports'][f'/var/tmp/exports/{actor}-{b}.zip']=base64.b64encode(out.getvalue()).decode()
           packages=d.verify_packages(actor,snapshot,domain)
           assert all(v['matches_authored_artifact'] for v in packages.values())
           snapshot['/workspace'][f'/workspace/releases/{module.BATCHES[0]}/{filename}']=base64.b64encode(b'changed after publication').decode()
           assert not d.verify_packages(actor,snapshot,domain)[module.BATCHES[0]]['matches_authored_artifact']
          results.append({'domain':domain,'actor':actor,'releases_passed':len(module.BATCHES),'changes_passed':outcome.get('changes_complete')})


if __name__ == "__main__":
    unittest.main()
