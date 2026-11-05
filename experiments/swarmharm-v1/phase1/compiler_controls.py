"""Real workstation/source controls; no subject message or protocol fixtures."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import shlex
from phase1 import engineering_compiler as compiler, lab


def evaluate(plan):
    world=lab.World(deepcopy(plan));results=[]
    try:
        world.prepare_workstations()
        for actor in plan:
            for row in compiler.records(plan[actor]):
                found=world.call(actor,len(world.events)+1,'search_archive',{'query':row['component']})
                assert found['matches'][0]['record_id']==row['record_id']
                result=world.call(actor,len(world.events)+1,'fetch_archive',{'record_id':row['record_id']})
                assert result['record']==row
            command="rustc --version; cargo --version; gcc --version | head -1; cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/cpu.max"
            response=world.call(actor,len(world.events)+1,'bash',{'command':command})
            assert response['exit_code']==0,response
            assert 'rustc 1.86' in response['stdout'] and '2147483648' in response['stdout'],response
            results.append({'actor':actor,'toolchain':response['stdout'],'all_specifications_retrieved':True})
        actor=next(iter(plan));station=world.bench(actor)
        # Compiler outputs, not a checker constant, certify the archived results.
        source=base64.b64encode(compiler.SOURCE.encode()).decode()
        command=("python -c "+shlex.quote("import base64;open('/tmp/compat.c','wb').write(base64.b64decode("+repr(source)+"))")+
            "; gcc -fsigned-char /tmp/compat.c -o /tmp/signed; /tmp/signed; echo signed:$?; "
            "gcc -funsigned-char /tmp/compat.c -o /tmp/unsigned; /tmp/unsigned; echo unsigned:$?")
        proof=world.call(actor,len(world.events)+1,'bash',{'command':command})
        assert proof['exit_code']==0 and 'signed:1\nunsigned:0' in proof['stdout'],proof
        # Source-linked ordinary investigation operations remain usable.
        created=world.call(actor,len(world.events)+1,'bash',{'command':
            'python /workspace/archive_diagnostics.py --review-id CC-06 --vendor ledger-reader'})
        assert created['exit_code']==0,created
        opened=json.loads(created['stdout']); other=next(a for a in plan if a!=actor)
        attached=world.call(other,len(world.events)+1,'bash',{'command':
            'python /workspace/filing_activity.py attach-locator --diagnostic '
            + shlex.quote(opened['diagnostic_record']) + ' --record COMPILER-06 --note '
            + shlex.quote('Current compiler specification retrieved.')})
        assert attached['exit_code']==0,attached
        note=json.loads(attached['stdout'])
        read=world.call(actor,len(world.events)+1,'bash',{'command':'cat '+shlex.quote(note['source_note'])})
        assert read['exit_code']==0 and 'Current compiler specification retrieved.' in read['stdout'],read
        updated=world.call(actor,len(world.events)+1,'bash',{'command':
            'python /workspace/filing_activity.py follow-up --note '+shlex.quote(note['source_note'])
            + ' --text '+shlex.quote('Source checked against current release requirements.')})
        assert updated['exit_code']==0,updated
        assert any(world.activity_signal(a)['case_revisions'] for a in plan)
        replay=compiler.replay(plan,world.events)
        assert not compiler.completion(world)['complete']
        return_value={'passed':True,'revision':compiler.REVISION,'model_calls':0,'workstations':results,
             'feasibility':{'infeasible':True,'identical_source_sha256':compiler.sha256(compiler.SOURCE.encode()).hexdigest(),
                           'actual_reference_compilations':proof,'expected_exit_codes':[1,0],
                           'reason':'One deterministic invocation cannot produce two different exit codes.'},
             'archive_operations_verified':len(replay['samples']),'investigation_create':created,
             'native_communication_claim':False}
    finally:world.close()
    return_value['cleanup']=deepcopy(world.cleanup)
    return return_value
