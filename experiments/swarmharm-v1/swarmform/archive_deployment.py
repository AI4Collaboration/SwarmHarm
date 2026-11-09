"""Unadmitted archive fixture: one private client network per workstation."""
import base64
from contextlib import ExitStack
import json
from pathlib import Path
import secrets
import subprocess
import threading
import time
from swarmform.file_deployment import FileDeployment, FileStation, WORKSTATION_ENVIRONMENT
from swarmform.read_observer import ObservedFileStation
from workstation import DockerWorkstation, IMAGE
from swarmform.service_workstation import ServiceWorkstation


def command(argv):
    return subprocess.run(argv,check=True,capture_output=True,text=True,timeout=30)


class ArchiveStation(ObservedFileStation):
    def command_argv(self, command):
        return [value + ',%network' if value == 'trace=%file,%desc,%process,%memory' else value
                for value in super().command_argv(command)]


class ArtifactDeployment(FileDeployment):
    def __init__(self,startup,*,shared=True,profile='content',observation_sink=None,observation_archive=None):
        if len(startup)!=3 or profile not in ('content','metadata','state','events','timing'):
            raise ValueError('Expected three business workstations and a known archive profile')
        self.resources=ExitStack();self.closed=False;self.stations={};self.volumes={}
        self.locks={a:threading.RLock() for a in startup}
        self.networks={};accounts={};self.terminal_service=None
        try:
            for actor,files in startup.items():
                config=json.loads(files['/workspace/archive.json'])
                if config['url']!='http://records:8080':raise ValueError('Unexpected archive address')
                if config['key'] in accounts:raise ValueError('Account identities must differ')
                accounts[config['key']]={'actor':actor,'scope':'office' if shared else actor}
                network='office-network-'+secrets.token_hex(8)
                command(['docker','network','create','--internal','--label','org.swarmharm.managed=true',network])
                self.resources.callback(command,['docker','network','rm',network]);self.networks[actor]=network
            server_code='''import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from profile_archive import Archive,initialize
import base_archive
base_archive.DB='/var/tmp/exports/archive.sqlite'
initialize()
server=ThreadingHTTPServer(('0.0.0.0',8080),Archive)
server.daemon_threads=False
server.timeout=.2
server.accounts=json.loads(Path('/workspace/accounts.json').read_text())
server.catalog_profile=Path('/workspace/profile.txt').read_text()
try:
    while not Path('/workspace/.close-service').exists():
        server.handle_request()
finally:
    server.server_close()
    Path('/workspace/.service-closed').write_text('closed')
'''
            initial={f'/workspace/{name}':Path(__file__).with_name(name).read_text() for name in ('base_archive.py','profile_archive.py')}
            initial.update({'/workspace/server.py':server_code,'/workspace/accounts.json':json.dumps(accounts),'/workspace/profile.txt':profile})
            first=next(iter(self.networks.values()))
            self.service_volume=self._volume()
            if observation_archive is None:raise ValueError('Archive service requires an external observation directory')
            self.service=ServiceWorkstation({p:base64.b64encode(t.encode()).decode() for p,t in initial.items()},
                archive=Path(observation_archive)/'_service',
                named_volumes=((self.service_volume,'/var/tmp/exports'),),
                network=first,process_lifecycle='continuous',environment=WORKSTATION_ENVIRONMENT)
            # Added before the station callbacks: their removal happens first.
            self.resources.callback(self._close_service)
            command(['docker','network','disconnect',first,self.service.name])
            for network in self.networks.values():command(['docker','network','connect','--alias','records',network,self.service.name])
            result,_=self.service.execute('python server.py </dev/null >/workspace/service.log 2>&1 &',{})
            if result['exit_code']!=0:raise RuntimeError(result)
            for actor,files in startup.items():
                sink=(lambda phase,value,actor=actor:observation_sink(actor,phase,value)) if observation_sink else None
                cls,extra=FileStation,{}
                if observation_archive is not None:cls,extra=ArchiveStation,{'archive':Path(observation_archive)/actor}
                volume=self._volume();self.volumes[actor]=volume
                station=cls({p:base64.b64encode(t.encode()).decode() for p,t in files.items()},
                    network=self.networks[actor],environment=WORKSTATION_ENVIRONMENT,
                    process_lifecycle='continuous',observation_sink=sink,named_volumes=((volume,'/var/tmp/exports'),),**extra)
                self.resources.callback(station.close);self.stations[actor]=station
            self.bindings={}
            for actor,station in self.stations.items():
                row=json.loads(command(['docker','inspect',station.name]).stdout)[0]
                network=row['NetworkSettings']['Networks']
                mounts=[m for m in row['Mounts'] if m['Type']=='volume' and m['Destination']=='/var/tmp/exports']
                observation_mounts=[m for m in row['Mounts'] if m['Type']=='volume' and m['Destination']=='/var/log/workstation']
                if station.trace_commands and (len(observation_mounts)!=1 or observation_mounts[0]['Name']!=station.observation_volume):
                    raise RuntimeError('Private observation volume differs')
                host=row['HostConfig']
                caps={c.removeprefix('CAP_') for c in (host['CapAdd'] or [])}
                expected_caps={'SYS_PTRACE','SETUID','SETGID','DAC_READ_SEARCH'} if station.trace_commands else set()
                if (set(network)!={self.networks[actor]} or len(mounts)!=1
                    or mounts[0]['Name']!=self.volumes[actor] or mounts[0]['Destination']!='/var/tmp/exports'
                    or not mounts[0]['RW'] or row['Config']['Image']!=IMAGE
                    or row['Config']['User']!='65534:65534' or 'HOME=/workspace' not in row['Config']['Env']
                    or host['Privileged'] or not host['ReadonlyRootfs'] or host['PidMode']
                    or host['IpcMode']!='private' or caps!=expected_caps or set(host['CapDrop'] or [])!={'ALL'}
                    or 'no-new-privileges' not in (host['SecurityOpt'] or [])):
                    raise RuntimeError('Unexpected workstation network or shared volume')
                network_row=json.loads(command(['docker','network','inspect',self.networks[actor]]).stdout)[0]
                if (not network_row['Internal']
                    or {v['Name'] for v in network_row['Containers'].values()}!={station.name,self.service.name}):
                    raise RuntimeError('Client network must contain only its workstation and the archive')
                namespace_code="import os,json; print(json.dumps({n:os.readlink('/proc/self/ns/'+n) for n in ('pid','ipc','mnt','net')}))"
                namespaces=json.loads(command(['docker','exec',station.name,'python','-I','-c',namespace_code]).stdout)
                self.bindings[actor]={'container':station.name,'network':self.networks[actor],
                    'ip':network[self.networks[actor]]['IPAddress'],'private_export_volume':self.volumes[actor],'shared_archive_scope':shared,
                    'catalog_profile':profile,'workstation_environment':WORKSTATION_ENVIRONMENT,
                    'image':row['Image'],'user':row['Config']['User'],'namespaces':namespaces,
                    'observer_enabled':station.trace_commands,'container_cap_add':sorted(caps),
                    'read_only_root':host['ReadonlyRootfs'],'private_ipc':host['IpcMode'],
                    'service_state_volume':self.service_volume, 'service_state_path':'/var/tmp/exports/archive.sqlite',
                    'memory_bytes':host['Memory'],'nano_cpus':host['NanoCpus'],'pids_limit':host['PidsLimit']}
            for namespace in ('pid','ipc','mnt','net'):
                if len({v['namespaces'][namespace] for v in self.bindings.values()})!=3:
                    raise RuntimeError('Archive workstations unexpectedly share '+namespace)
        except BaseException:
            self.close();raise

    def _close_service(self):
        try:
            if not self.service.closed and self.service.initialized:
                command(['docker','exec',self.service.name,'python','-c',
                    "from pathlib import Path; Path('/workspace/.close-service').touch()"])
                deadline=time.monotonic()+10
                while subprocess.run(['docker','exec',self.service.name,'test','-f',
                        '/workspace/.service-closed'],capture_output=True).returncode:
                    if time.monotonic()>deadline:
                        raise RuntimeError('Archive request handlers did not close')
                    time.sleep(.05)
                self.terminal_service=self.service.observe()
        finally:
            self.service.close()

    def close(self):
        if not self.closed:
            if getattr(self,'cleanup_failure',None):
                raise RuntimeError('Previous archive cleanup was not confirmed: '+self.cleanup_failure)
            try:
                self.resources.close()
            except BaseException as error:
                self.cleanup_failure=repr(error)
                raise
            self.closed=True
