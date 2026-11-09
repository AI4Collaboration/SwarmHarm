"""Upload, list and retrieve office archive records."""
import argparse,base64,json
from pathlib import Path
import urllib.request
from urllib.parse import urlencode

def request(method,path,body=None):
    config=json.loads(Path('/workspace/archive.json').read_text())
    req=urllib.request.Request(config['url']+path,data=json.dumps(body).encode() if body is not None else None,method=method,
        headers={'Authorization':'Bearer '+config['key'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)

def upload(path,name=None,metadata=None):
    path=Path(path)
    return request('POST','/records',{'name':name or path.name,'metadata':metadata or {},'content_base64':base64.b64encode(path.read_bytes()).decode()})

def upload_batch(records):
    """Publish up to 500 files in one transaction."""
    values=[]
    for row in records:
        path=Path(row['file'])
        values.append({'name':row.get('name',path.name),'metadata':row.get('metadata',{}),
                       'content_base64':base64.b64encode(path.read_bytes()).decode()})
    return request('POST','/records-batch',{'records':values})

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    listing=sub.add_parser('list',help='List a page of accessible archive entries')
    listing.add_argument('--after',type=int,default=0);listing.add_argument('--limit',type=int,default=500)
    events=sub.add_parser('events',help='List archive activity')
    events.add_argument('--after',type=int,default=0);events.add_argument('--limit',type=int,default=500)
    put=sub.add_parser('upload',help='Publish a file');put.add_argument('file',type=Path);put.add_argument('--name');put.add_argument('--metadata',default='{}',help='JSON document properties')
    get=sub.add_parser('fetch',help='Save an archive file');get.add_argument('id',type=int);get.add_argument('output',type=Path)
    state=sub.add_parser('state',help='Update publication state');state.add_argument('id',type=int);state.add_argument('value',choices=['draft','ready','archived'])
    batch=sub.add_parser('upload-batch',help='Publish files from a JSON list of file paths, names and document properties');batch.add_argument('manifest',type=Path)
    states=sub.add_parser('state-batch',help='Apply a JSON list of record IDs and publication states in one transaction');states.add_argument('manifest',type=Path)
    args=parser.parse_args()
    if args.operation=='list':result=request('GET','/records?'+urlencode({'after':args.after,'limit':args.limit}))
    elif args.operation=='events':result=request('GET','/events?'+urlencode({'after':args.after,'limit':args.limit}))
    elif args.operation=='upload':result=upload(args.file,args.name,json.loads(args.metadata))
    elif args.operation=='state':result=request('POST','/record-state',{'id':args.id,'state':args.value})
    elif args.operation=='upload-batch':result=upload_batch(json.loads(args.manifest.read_text()))
    elif args.operation=='state-batch':result=request('POST','/record-states',{'records':json.loads(args.manifest.read_text())})
    else:
        result=request('GET','/record?id='+str(args.id));args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_bytes(base64.b64decode(result.pop('content_base64'),validate=True));result['file']=str(args.output)
    print(json.dumps(result))
