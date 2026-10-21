import subprocess,time,json
from pathlib import Path
for i,srv in enumerate(json.loads(Path('/opt/mimo/manifest.json').read_text())['mcp_servers']):
 log=open('/var/lib/mimo/'+srv['name']+'.log','w')
 subprocess.Popen(['python3','/opt/mimo/mcp_http.py','--tools-path','/work/tools/'+srv['name']+'.py','--server-name',srv['name'],'--port',str(39101+i)],stdout=log,stderr=log)
while True:time.sleep(60)
