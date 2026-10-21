import json,sys,requests
x=json.load(sys.stdin);url='http://127.0.0.1:'+str(x['port'])+'/mcp'
h={'Accept':'application/json, text/event-stream','Content-Type':'application/json'}
def decode(r):
 r.raise_for_status();r.encoding='utf-8'
 if 'application/json' in r.headers.get('Content-Type',''):return r.json()
 for line in r.text.splitlines():
  if line.startswith('data:'):return json.loads(line[5:])
 raise RuntimeError('No MCP response')
init=requests.post(url,headers=h,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'swarmharm-harbor','version':'1'}}},timeout=30);decode(init)
sid=init.headers.get('mcp-session-id')
if sid:h['mcp-session-id']=sid
h['MCP-Protocol-Version']='2025-03-26'
requests.post(url,headers=h,json={'jsonrpc':'2.0','method':'notifications/initialized'},timeout=30).raise_for_status()
r=decode(requests.post(url,headers=h,json={'jsonrpc':'2.0','id':2,'method':x['method'],'params':x.get('params',{})},timeout=60))
if sid:requests.delete(url,headers=h,timeout=10)
print(json.dumps(r,ensure_ascii=False))
