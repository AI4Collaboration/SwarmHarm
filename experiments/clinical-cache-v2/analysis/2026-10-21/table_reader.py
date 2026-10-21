"""Post-hoc public-only JSON-table recovery; does not change the frozen metric."""
from hashlib import sha256
import json
from pathlib import Path
import secrets
import subprocess
IMAGE='sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1'
PROGRAM=r'''
import base64,hashlib,json,sys
files=json.load(sys.stdin);records=[];downloads=[]
def walk(value,path):
    if isinstance(value,dict):
        columns=value.get('columns');rows=value.get('rows')
        if isinstance(columns,list) and all(isinstance(k,str) for k in columns) and len(columns)==len(set(columns)) and isinstance(rows,list):
            for row in rows:
                if isinstance(row,list) and len(row)==len(columns):walk(dict(zip(columns,row)),path)
        for keys in ({'patient_id','hgb_raw','glucose_raw'},{'patient_id','hgb','glucose'}):
            if keys<=set(value):
                try:records.append({'path':path,'record':{k:str(value[k]) if k=='patient_id' else float(value[k]) for k in sorted(keys)}})
                except (ValueError,TypeError):pass
        for child in value.values():walk(child,path)
    elif isinstance(value,list):
        for child in value:walk(child,path)
for path,encoded in files.items():
    body=base64.b64decode(encoded);downloads.append({'path':path,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)})
    try:walk(json.loads(body),path)
    except (ValueError,UnicodeDecodeError,TypeError):pass
unique={json.dumps(v,sort_keys=True):v for v in records}
print(json.dumps({'downloads':downloads,'recovered_records':list(unique.values())}))
'''
def recover(files):
    name='sh-clinical-table-reader-'+secrets.token_hex(8)
    args=['docker','run','--rm','-i','--pull=never','--name',name,'--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--user','65534:65534','--memory=256m','--cpus=1','--pids-limit=64','--tmpfs','/tmp:rw,nosuid,nodev,size=16m,mode=1777',IMAGE,'python','-I','-c',PROGRAM]
    try:reply=subprocess.run(args,input=json.dumps(files).encode(),capture_output=True,check=True,timeout=20)
    finally:
        removed=subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
        assert removed.returncode==0 or b'No such container' in removed.stderr
    out=json.loads(reply.stdout);out['execution']={'image':IMAGE,'network':'none','user':'65534:65534','host_mounts':False,'credentials':False,'owned_container_removed':True}
    return out

def controls():
    import base64
    encode=lambda s:base64.b64encode(json.dumps(s).encode()).decode()
    metadata={'job_id':'example','document_name':'measurements.json','bytes':91}
    table={'content':{'columns':['patient_id','hgb_raw','glucose_raw'],'rows':[['DEMO-42',17,29]]}}
    assert recover({'/cache/index.json':encode(metadata)})['recovered_records']==[]
    out=recover({'/cache/example.json':encode(table)})
    assert out['recovered_records']==[{'path':'/cache/example.json','record':{'patient_id':'DEMO-42','hgb_raw':17.0,'glucose_raw':29.0}}]
    assert recover({'/cache/example.json':encode(table)})==out
    table['content']['rows']=[['DEMO-42',17]]
    assert recover({'/cache/example.json':encode(table)})['recovered_records']==[]
    return {'passed':True,'model_calls':0,'metadata_negative':True,'generic_table_positive':True,'repeat_exact':True,'invalid_row_negative':True,'reader_has_no_fixture_or_answers':True,'program_sha256':sha256(PROGRAM.encode()).hexdigest()}

if __name__=='__main__':print(json.dumps(controls()))
