"""Upload, list and retrieve office archive records."""
import argparse,base64,json
from pathlib import Path
import urllib.request

def request(method,path,body=None):
    config=json.loads(Path('/workspace/archive.json').read_text())
    req=urllib.request.Request(config['url']+path,data=json.dumps(body).encode() if body is not None else None,method=method,
        headers={'Authorization':'Bearer '+config['key'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)

def upload(path,name=None,metadata=None):
    path=Path(path)
    return request('POST','/records',{'name':name or path.name,'metadata':metadata or {},'content_base64':base64.b64encode(path.read_bytes()).decode()})

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    sub.add_parser('list',help='List accessible archive entries')
    put=sub.add_parser('upload',help='Publish a file');put.add_argument('file',type=Path);put.add_argument('--name');put.add_argument('--metadata',default='{}',help='JSON document properties')
    get=sub.add_parser('fetch',help='Save an archive file');get.add_argument('id',type=int);get.add_argument('output',type=Path)
    state=sub.add_parser('state',help='Update publication state');state.add_argument('id',type=int);state.add_argument('value',choices=['draft','ready','archived'])
    args=parser.parse_args()
    if args.operation=='list':result=request('GET','/records')
    elif args.operation=='upload':result=upload(args.file,args.name,json.loads(args.metadata))
    elif args.operation=='state':result=request('POST','/record-state',{'id':args.id,'state':args.value})
    else:
        result=request('GET','/record?id='+str(args.id));args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_bytes(base64.b64decode(result.pop('content_base64'),validate=True));result['file']=str(args.output)
    print(json.dumps(result))
