"""Independent processing service with scoped accounts and private client networks."""
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


class JobStation(ObservedFileStation):
    def command_argv(self, command):
        return [value + ",%network" if value == "trace=%file,%desc,%process,%memory" else value
                for value in super().command_argv(command)]


class JobDeployment(FileDeployment):
    observed_station_class=JobStation
    connection_path="/workspace/processing.json"
    service_url="http://processor:8080"
    service_alias="processor"

    def service_files(self, accounts, profile):
        return {'/workspace/job_service.py': Path(__file__).with_name('job_service.py').read_text(),
                '/workspace/server.py': 'from job_service import serve\nserve()\n',
                '/workspace/accounts.json': json.dumps(accounts), '/workspace/profile.txt':profile}

    def __init__(self,startup,*,shared=True,profile='content',observation_sink=None,observation_archive=None):
        if len(startup)!=3 or profile not in ('content','metadata','state','events','timing') or type(shared) is not bool:
            raise ValueError('Expected three business workstations and a known processing profile')
        self.resources=ExitStack();self.closed=False;self.stations={};self.volumes={}
        self.locks={a:threading.RLock() for a in startup}
        self.networks={};accounts={};self.terminal_service=None
        try:
            for actor,files in startup.items():
                config=json.loads(files[self.connection_path])
                if config['url']!=self.service_url:raise ValueError('Unexpected processing address')
                if config['key'] in accounts:raise ValueError('Account identities must differ')
                accounts[config['key']]={'actor':actor,'scope':'office' if shared else actor}
                network='office-network-'+secrets.token_hex(8)
                command(['docker','network','create','--internal','--label','org.swarmharm.managed=true',network])
                self.resources.callback(self._remove_network,network);self.networks[actor]=network
            initial=self.service_files(accounts,profile)
            first=next(iter(self.networks.values()))
            self.service_volume=self._volume()
            if observation_archive is None:raise ValueError('Processing service requires an external observation directory')
            self.service=ServiceWorkstation({p:base64.b64encode(t.encode()).decode() for p,t in initial.items()},
                archive=Path(observation_archive)/'_service',
                named_volumes=((self.service_volume,'/var/tmp/exports'),),
                network=first,process_lifecycle='continuous',environment=WORKSTATION_ENVIRONMENT)
            # Added before the station callbacks: their removal happens first.
            self.resources.callback(self._close_service)
            command(['docker','network','disconnect',first,self.service.name])
            for network in self.networks.values():command(['docker','network','connect','--alias',self.service_alias,network,self.service.name])
            result,_=self.service.execute('python server.py </dev/null >/workspace/service.log 2>&1 &',{})
            if result['exit_code']!=0:raise RuntimeError(result)
            for actor,files in startup.items():
                sink=(lambda phase,value,actor=actor:observation_sink(actor,phase,value)) if observation_sink else None
                cls,extra=FileStation,{}
                if observation_archive is not None:cls,extra=self.observed_station_class,{'archive':Path(observation_archive)/actor}
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
                    raise RuntimeError('Client network must contain only its workstation and the processing')
                namespace_code="import os,json; print(json.dumps({n:os.readlink('/proc/self/ns/'+n) for n in ('pid','ipc','mnt','net')}))"
                namespaces=json.loads(command(['docker','exec',station.name,'python','-I','-c',namespace_code]).stdout)
                self.bindings[actor]={'container':station.name,'network':self.networks[actor],
                    'ip':network[self.networks[actor]]['IPAddress'],'private_export_volume':self.volumes[actor],'shared_job_scope':shared,
                    'processing_profile':profile,'workstation_environment':WORKSTATION_ENVIRONMENT,
                    'image':row['Image'],'user':row['Config']['User'],'namespaces':namespaces,
                    'observer_enabled':station.trace_commands,'container_cap_add':sorted(caps),
                    'read_only_root':host['ReadonlyRootfs'],'private_ipc':host['IpcMode'],
                    'service_state_volume':self.service_volume,'service_state_path':'/var/tmp/exports/jobs.sqlite',
                    'memory_bytes':host['Memory'],'nano_cpus':host['NanoCpus'],'pids_limit':host['PidsLimit']}
            for namespace in ('pid','ipc','mnt','net'):
                if len({v['namespaces'][namespace] for v in self.bindings.values()})!=3:
                    raise RuntimeError('Processing workstations unexpectedly share '+namespace)
        except BaseException:
            self.close();raise

    def _retained_service(self):
        service=getattr(self,'service',None)
        return service is not None and not service.closed

    def _remove_network(self,name):
        if self._retained_service():
            self.retained_resources=getattr(self,'retained_resources',[])+[{'kind':'network','name':name}]
            return
        command(['docker','network','rm',name])

    def _remove_volume(self,name):
        if name==getattr(self,'service_volume',None) and self._retained_service():
            self.retained_resources=getattr(self,'retained_resources',[])+[{'kind':'volume','name':name}]
            return
        FileDeployment._remove_volume(self,name)

    def _close_service(self):
        try:
            if not self.service.closed and self.service.initialized:
                command(['docker','exec',self.service.name,'python','-c',
                    "from pathlib import Path; Path('/workspace/.close-service').touch()"])
                deadline=time.monotonic()+10
                while subprocess.run(['docker','exec',self.service.name,'test','-f',
                        '/workspace/.service-closed'],capture_output=True).returncode:
                    if time.monotonic()>deadline:
                        raise RuntimeError('Processing request handlers did not close')
                    time.sleep(.05)
                self.terminal_service=self.service.observe()
        finally:
            self.service.close()

    def close(self):
        if not self.closed:
            if getattr(self,'cleanup_failure',None):
                raise RuntimeError('Previous processing cleanup was not confirmed: '+self.cleanup_failure)
            try:
                self.resources.close()
            except BaseException as error:
                self.cleanup_failure=repr(error)
                raise
            self.closed=True
