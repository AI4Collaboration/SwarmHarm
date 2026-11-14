"""Protected service capture with persistent state and loss-preserving teardown."""
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from workstation import DockerWorkstation
import workstation
from atomic import atomic_json


class ServiceWorkstation(DockerWorkstation):
    def __init__(self,initial_files,*,archive,**kwargs):
        self.service_archive=Path(archive).resolve();self.service_archive.mkdir(parents=True,exist_ok=False)
        self.service_capture_count=0
        initial=dict(initial_files)
        initial['/workspace/.service-observer.py']=base64.b64encode(Path(workstation.__file__).with_name('workstation_observer.py').read_bytes()).decode()
        super().__init__(initial,**kwargs)

    def capture_frozen(self,phase):
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

    def close(self):
        if self.closed:return
        if not self.initialized:return super().close()
        # A failed capture must retain the service, not remove its only original state.
        self.capture_frozen('terminal')
        removed=subprocess.run(['docker','rm','-f',self.name],capture_output=True,timeout=20)
        if removed.returncode and b'No such container' not in removed.stderr:raise RuntimeError('Service removal unconfirmed')
        self.closed=True
