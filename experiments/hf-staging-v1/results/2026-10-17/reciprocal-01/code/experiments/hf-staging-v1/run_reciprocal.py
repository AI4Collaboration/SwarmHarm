"""New sealed development round with reciprocal real source possession."""
import io
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run
from reciprocal import ReciprocalWorld
import checks_reciprocal


def main():
    original=run.actor_plan
    def complementary_plan(cell):
        plan=original(cell)
        if cell['mode']=='mixed':
            for job in plan.values():
                job['full_access']=False
                job['partition']='head' if job['wave']%2==0 else 'tail'
                job['analysis']='full' if job['partition']=='head' else 'aggregate'
        return plan
    run.actor_plan=complementary_plan;run.FleetWorld=ReciprocalWorld
    preparing='--phase' in sys.argv and sys.argv[sys.argv.index('--phase')+1]=='prepare'
    capture=io.StringIO()
    if preparing:
        result=unittest.TextTestRunner(stream=capture,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(checks_reciprocal))
        if not result.wasSuccessful():raise RuntimeError(capture.getvalue())
    run.main()
    if preparing:
        output=run.ACTIVE_OUTPUT
        run.save(output/'reciprocal-controls.json',{'passed':True,'test_methods':result.testsRun,'log':capture.getvalue(),'model_requests':0})
        reg=run.load(output/'registration.json')
        reg['family']='swarmharm/hf-staging-reciprocal-v1';reg['world_class']='ReciprocalWorld'
        reg['mixed_feasibility']='Every natural worker has a real complementary source slice and lacks its own supporting slice. Different legitimate analyses share exact original source records; no full-input helper exists.'
        reg['source_prompts']='Original full-analysis questions on head projections and explicitly derived aggregate questions on complementary tail projections. Source row values never change. Four arrivals are scheduling waves.'
        reg['input_hashes']['reciprocal-controls.json']=run.sha(output/'reciprocal-controls.json')
        run.save(output/'registration.json',reg)
        run.save(output/'registration-seal.json',{'sha256':run.sha(output/'registration.json'),'model_requests_at_sealing':0})


if __name__=='__main__':main()
