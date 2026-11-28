"""Protected service capture with persistent state and loss-preserving teardown."""
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from swarmform.workstation import DockerWorkstation
from swarmform import workstation
from atomic import atomic_json


class ServiceWorkstation(DockerWorkstation):
    volume_targets = ("/var/tmp/exports", "/workspace")

    def __init__(self,initial_files,*,archive,**kwargs):
        self.service_archive=Path(archive).resolve();self.service_archive.mkdir(parents=True,exist_ok=False)
        self.service_capture_count=0
        self.terminal_captured=False
        initial=dict(initial_files)
        initial['/workspace/.service-observer.py']=base64.b64encode(Path(workstation.__file__).with_name('workstation_observer.py').read_bytes()).decode()
        super().__init__(initial,**kwargs)

    def capture_frozen(self,phase,*,resume_inline=False):
        code=Path(__file__).with_name('service_capture.py').read_text()
        self.service_capture_count+=1
        raw_path=self.service_archive/f'{self.service_capture_count:06d}.bin'
        error_path=raw_path.with_suffix('.stderr')
        with raw_path.open('xb') as output,error_path.open('xb') as errors:
            process=subprocess.run(['docker','exec',self.name,'python','-I','-c',code],stdout=output,stderr=errors,timeout=180)
            output.flush()
            os.fsync(output.fileno())
            errors.flush()
            os.fsync(errors.fileno())
        if process.returncode:raise RuntimeError('Service capture failed; retained '+str(raw_path))
        with raw_path.open('rb') as stream:
            line=stream.readline()
            if not line.endswith(b'\n'):raise RuntimeError('Service capture header is incomplete')
            header=json.loads(line)
            values={key:value for key,value in header.items() if key!='files'}
            values.update({root:{} for root in ('/workspace','/registry','/var/tmp/exports')})
            values['temporary_files']={};hashes={}
            for item in header['files']:
                data=stream.read(item['bytes'])
                if len(data)!=item['bytes']:raise RuntimeError('Service capture is incomplete')
                root='temporary_files' if item['root'] in ('/tmp','/private/tmp') else item['root']
                values[root][item['path']]=base64.b64encode(data).decode();hashes[item['path']]=sha256(data).hexdigest()
            if stream.read(1):raise RuntimeError('Unexpected bytes after service capture')
        with raw_path.open('rb') as stream:
            import hashlib
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        index={'phase':phase,'raw':raw_path.name,'raw_sha256':digest,'bytes':header['bytes'],'files':hashes}
        atomic_json(raw_path.with_suffix('.json'), index)
        values['service_observation_reference']=index
        if self.observation_sink is not None:values['observation_reference']=self.observation_sink(phase,values)
        return values

    def capture_terminal(self):
        if self.initialized and not self.terminal_captured:
            self.capture_frozen('terminal')
            self.terminal_captured = True

    def retire(self):
        if self.closed:
            return
        if self.initialized and not self.terminal_captured:
            raise RuntimeError('Service terminal capture missing; originals retained')
        workstation.remove_workstation(self.name)
        self.closed = True

    def close(self):
        self.capture_terminal()
        self.retire()
