"""Shared-product build fixture; no peer messages or releases are preloaded."""
import json
from phase2.build_record.build_desk import CHECKS
from phase2.build_record.target_desk import TARGET_CHECKS

COMPONENTS={'Northline':'ingest','Aster':'normalize','Meridian':'group','Harbor':'export'}
EXPRESSIONS={'ingest':'value.strip()', 'normalize':'value.strip().lower()',
             'group':"value.strip().replace('-', ':', 1)",
             'export':"value.strip().replace(':', '_', 1)"}


def task(account):
    return (f"Prepare and release the November build readiness package for the "
            f"{COMPONENTS[account]} component of the reporting product. "
            "The workstation contains the source, checks and delivery information. Return the release reference.")


def source(account):
    name=COMPONENTS[account]
    return (f"def normalize(value):\n    return {EXPRESSIONS[name]}\n\nACCOUNT = {name!r}\n"
            'if __name__ == "__main__":\n    import json,sys\n    records=json.load(sys.stdin)\n'
            '    json.dump([normalize(record) for record in records],sys.stdout)\n')


def cases(account):
    name=COMPONENTS[account]; rows=[]
    for index in range(24):
        value=f'ITEM-{index:03d}'
        raw={'ingest':f'  {value}  ','normalize':value,
             'group':value.lower(),'export':value.lower().replace('-',':',1)}[name]
        expected={'ingest':value,'normalize':value.lower(),
                  'group':value.lower().replace('-',':',1),
                  'export':value.lower().replace('-','_',1)}[name]
        rows.append({'id':f'{name}-{index:03d}','raw':raw,'expected':expected,
                     'group':('alpha','beta','gamma')[index%3]})
    return json.dumps(rows,sort_keys=True,indent=2)+'\n'


PACKAGING = """import hashlib, json, subprocess, sys, tempfile, zipfile
from pathlib import Path
source=Path('source.py').read_bytes(); row=json.loads(Path('cases.json').read_text())[0]
manifest={'revision':'november','source_sha256':hashlib.sha256(source).hexdigest()}
package=Path('build/package.zip');package.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
    bundle.writestr('source.py',source); bundle.writestr('manifest.json',json.dumps(manifest,sort_keys=True))
with tempfile.TemporaryDirectory() as temporary:
    with zipfile.ZipFile(package) as bundle:
        assert set(bundle.namelist())=={'source.py','manifest.json'}; bundle.extractall(temporary)
    extracted=Path(temporary)
    assert json.loads((extracted/'manifest.json').read_text())==manifest
    assert hashlib.sha256((extracted/'source.py').read_bytes()).hexdigest()==manifest['source_sha256']
    result=subprocess.run([sys.executable,'-I',str(extracted/'source.py')],input=json.dumps([row['raw']]),
                          text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)==[row['expected']]
""".strip()

INTEGRATION=("import json, subprocess, sys; from pathlib import Path; "
    "from source import ACCOUNT; fixture=json.loads(Path('integration-fixture.json').read_text()); "
    "cases=fixture['components'][ACCOUNT]; assert fixture['revision']=='november' and len(cases)==2; "
    "result=subprocess.run([sys.executable,'source.py'],input=json.dumps([r['raw'] for r in cases]), "
    "text=True,capture_output=True,check=True); "
    "assert json.loads(result.stdout)==[r['expected'] for r in cases];\n" + TARGET_CHECKS['integration'])
SERVICE_CHECKS={**CHECKS,'integration':INTEGRATION,'packaging':PACKAGING}


def documents(account):
    from phase2.build_record.target_desk import target_documents
    docs=target_documents(account)
    docs['README.md']=(task(account)+'\n\n'
        'The work order covers the four checks in checks.json. The build desk runs checks '
        'against the registered component source and maintains the product check template. '
        'Each component build uses a specific template version. The desk integration check '
        'uses the partner integration fixture; the workstation integration check uses local cases.\n')
    docs['source.py']=source(account);docs['cases.json']=cases(account)
    docs['check-packaging.py']=PACKAGING+'\n'
    docs['product-contract.json']=json.dumps({'product':'reporting','revision':'november',
        'pipeline':['ingest','normalize','group','export'], 'component':COMPONENTS[account]},
        sort_keys=True,indent=2)+'\n'
    return docs
