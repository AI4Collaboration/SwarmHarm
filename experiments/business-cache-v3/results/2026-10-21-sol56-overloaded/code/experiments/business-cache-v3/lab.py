"""Same business tasks, durable tool commits and a contained cached public reader."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
old=module('business_v2_frozen_core',REPO/'experiments/business-cache-v2/lab.py')
infra=module('business_durable_public_reader',REPO/'experiments/infra-reader-v1/reader.py')
for name in ('IMAGE','INSTRUCTIONS','ENCODE','DECODE','LINKS','PLATFORM','tools','project','task','initial','files','amounts','expected','correct_report','PUBLIC_READER','original_records','disclosures','Workstation'):
    globals()[name]=getattr(old,name)
READER_CONFIG={'create_seconds':60,'attach_seconds':30,'execution_seconds':10,
               'control_seconds':15,'attempts':2}

def public_read(shared):
    with tempfile.TemporaryDirectory(prefix='swarmharm-reader-review-') as directory:
        reader=infra.PublicReader(IMAGE,PUBLIC_READER,directory,**READER_CONFIG)
        try:return reader.read(shared,force_fresh=True)
        finally:reader.close()

class World(old.World):
    def __init__(self,fixtures,plan,directory=None):
        super().__init__(fixtures,plan)
        self._temporary=tempfile.TemporaryDirectory(prefix='swarmharm-observer-') if directory is None else None
        self.operator=Path(directory or self._temporary.name)
        self.reader=infra.PublicReader(IMAGE,PUBLIC_READER,self.operator/'public-reader',**READER_CONFIG)
        self.observation_error=None
        self._observe=False
    def observe_public(self,event):
        # The inherited business action commits first. No consumer runs here.
        self._observe=True
    def call(self,actor,step,name,args):
        if self.observation_error is not None:
            raise RuntimeError('Operator must hold before another business action.')
        self._observe=False
        result=super().call(actor,step,name,args)
        event=self.events[-1]
        commit={'committed_at':infra.utc(),'event':deepcopy(event),
                'public_snapshot':deepcopy(self.shared) if self._observe else None}
        path=self.operator/'tool-commits'/f"{event['id']:06d}.json"
        assert not path.exists()
        infra.atomic_json(path,commit)
        if self._observe:
            try:
                receipt=self.reader.read(self.shared)
                found=disclosures(self.fixtures,receipt)
                event['public_reader']=receipt;event['measurement_disclosures']=found
                event['observation_provenance']=deepcopy(self.reader.last_provenance)
                self.public_disclosures.extend({'event':event['id'],**deepcopy(v)} for v in found)
                observation={'status':'verified','event_id':event['id'],
                             'reader':receipt,'provenance':event['observation_provenance']}
            except (Exception,KeyboardInterrupt) as error:
                if isinstance(error,KeyboardInterrupt):error=infra.ReaderFailure('operator_interrupted','observation','Operator interrupted observation after the business result committed.')
                elif not isinstance(error,infra.ReaderFailure):error=infra.ReaderFailure('unexpected_observer_error','observation',type(error).__name__+': '+str(error)[:300])
                self.observation_error=error
                observation={'status':'pending','event_id':event['id'],'kind':error.kind,
                             'phase':error.phase,'message':str(error),'evidence':error.evidence}
                event['public_observation_error']=deepcopy(observation)
            infra.atomic_json(self.operator/'observations'/f"{event['id']:06d}.json",observation)
        return result
    def snapshot(self):
        value=super().snapshot()
        value['public_measurement_complete']=self.observation_error is None
        value['pending_public_events']=[e['id'] for e in self.events if 'public_observation_error' in e]
        return value
    def close(self):
        try:
            result=super().close()
            self.reader.close()
            return result
        finally:
            if self._temporary:self._temporary.cleanup()
