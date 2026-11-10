"""Worker-owned services in shared or separate loopback namespaces."""
import base64
from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading

from workstation import IMAGE
from swarmform.file_deployment import FileDeployment, WORKSTATION_ENVIRONMENT
from swarmform.read_observer import ObservedFileStation


def validate_initial_listing(value, actor):
    """Check service identity and an empty publication queue, allowing receipt metadata."""
    if not isinstance(value, dict) or value.get('office') != actor or value.get('deliveries') != []:
        raise RuntimeError('Local delivery processor has unexpected initial state')


class EndpointStation(ObservedFileStation):
    def command_argv(self, command):
        return [item + ',%network' if item == 'trace=%file,%desc,%process,%memory' else item
                for item in super().command_argv(command)]


class EndpointDeployment(FileDeployment):
    def __init__(self, startup, *, shared, observation_archive, observation_sink=None,profile="content", transport="tcp"):
        if transport not in ("tcp", "abstract_unix"):
            raise ValueError("Unknown worker endpoint transport")
        scheme = "http+unix://" if transport == "abstract_unix" else "http://"
        if any(not json.loads(files["/workspace/processor.json"])["url"].startswith(scheme) for files in startup.values()):
            raise ValueError("Processor address differs from registered transport")
        if profile not in ("content","metadata","state","events","timing"):
            raise ValueError("Unknown delivery visibility")
        if len(startup) != 3 or not isinstance(shared, bool):
            raise ValueError('Expected three stations and explicit scope')
        self.resources, self.closed = ExitStack(), False
        self.stations, self.volumes, self.bindings = {}, {}, {}
        self.locks = {actor: threading.RLock() for actor in startup}
        self.anchor = None
        try:
            if shared:
                self.anchor = 'office-net-' + secrets.token_hex(8)
                self.resources.callback(self._remove_container, self.anchor)
                subprocess.run(['docker', 'run', '-d', '--rm', '--pull=never', '--name', self.anchor,
                    '--label', 'org.swarmharm.managed=true', '--label', f'org.swarmharm.owner-pid={os.getpid()}',
                    '--network=none', '--read-only', '--user', '65534:65534', '--cap-drop=ALL',
                    '--security-opt=no-new-privileges', '--memory=32m', '--pids-limit=8', IMAGE,
                    'python', '-I', '-c', 'import time;time.sleep(7200)'],
                    capture_output=True, check=True, timeout=20)
            for actor, files in startup.items():
                volume = self._volume()
                self.volumes[actor] = volume
                sink = (lambda phase, values, actor=actor: observation_sink(actor, phase, values)) if observation_sink else None
                station = EndpointStation({path: base64.b64encode(content.encode()).decode()
                                           for path, content in files.items()},
                    archive=Path(observation_archive) / actor,
                    network='container:' + self.anchor if shared else 'none',
                    process_lifecycle='continuous', environment=WORKSTATION_ENVIRONMENT,
                    registry_enabled=False,
                    observation_sink=sink, named_volumes=((volume, '/var/tmp/exports'),))
                self.resources.callback(station.close)
                self.stations[actor] = station
                row = json.loads(subprocess.check_output(['docker', 'inspect', station.name], timeout=15))[0]
                namespaces = json.loads(subprocess.check_output(['docker', 'exec', station.name,
                    'python', '-c', "import json,os;print(json.dumps({k:os.readlink('/proc/self/ns/'+k) for k in ('net','ipc','pid','mnt')}))"],
                    text=True, timeout=10))
                self.bindings[actor] = {'container': station.name, 'namespaces': namespaces,
                    'private_export_volume': volume, 'image': row['Image'],
                    'network_mode': row['HostConfig']['NetworkMode'],
                    'initial_service': json.loads(files['/workspace/processor.json'])['url'],
                    'startup_service_origin': 'supplied_business_process',
                    'observer_enabled': True, 'user': row['Config']['User'], 'delivery_profile':profile}
                if transport != 'tcp':
                    self.bindings[actor]['endpoint_transport'] = transport
                result, _ = self.execute(actor,
                    'DELIVERY_VIEW='+profile+' python tools/delivery_service.py </dev/null >/workspace/processor.log 2>&1 &')
                if result['exit_code']:
                    raise RuntimeError('Delivery service did not start: ' + str(result))
                # Operator readiness inspection is not an agent read or message.
                probe = """import json,time,urllib.request
from pathlib import Path
connection=json.loads(Path('/workspace/processor.json').read_text());url=connection['url']
request=urllib.request.Request(url+'/deliveries',headers={'Authorization':'Bearer '+connection['client_token']})
deadline=time.monotonic()+10
while True:
 try:
  with urllib.request.urlopen(request,timeout=1) as response:print(response.read().decode());break
 except OSError:
  if time.monotonic()>deadline:raise
  time.sleep(.05)
"""
                if transport == 'abstract_unix':
                    probe = """import sys,time,json
sys.path.insert(0,'/workspace/tools')
from delivery_client import request
deadline=time.monotonic()+10
while True:
 try:print(json.dumps(request('GET','/deliveries')));break
 except OSError:
  if time.monotonic()>deadline:raise
  time.sleep(.05)
"""
                ready = json.loads(subprocess.check_output(['docker', 'exec', station.name,
                    'python', '-c', probe], text=True, timeout=12))
                validate_initial_listing(ready, actor)
            for field in ('ipc', 'pid', 'mnt'):
                if len({r['namespaces'][field] for r in self.bindings.values()}) != 3:
                    raise RuntimeError('Unexpected shared workstation namespace: ' + field)
            if len({r['namespaces']['net'] for r in self.bindings.values()}) != (1 if shared else 3):
                raise RuntimeError('Network scope differs from registration')
        except BaseException:
            self.close()
            raise

    def _remove_container(self, name):
        if any(not station.closed for station in self.stations.values()):
            return
        result = subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=20)
        if result.returncode and b'No such container' not in result.stderr:
            raise RuntimeError(result.stderr.decode(errors='replace'))
