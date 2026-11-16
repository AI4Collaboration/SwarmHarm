"""Check four-agent SwarmForm deployments and read capture without model calls."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import shlex
import subprocess

from swarmform import formation_inputs, program_reference
from swarmform.programbench_pilot import reference_path
from swarmform.__main__ import CHANNELS, runtime_info, seal_evidence, source_digest
from swarmform.formation_common import CommonWorkspace
from swarmform.formation_deployment import deployment
from swarmform.read_observer import observed_reads
from workstation import IMAGE

REPO = Path(__file__).resolve().parents[1]


def check(output, population=4, channels=CHANNELS):
    output = Path(output).resolve()
    if output.is_relative_to(REPO) or output.exists():
        raise ValueError('Choose a fresh software-check output outside the repository')
    output.mkdir(parents=True)
    truth = formation_inputs.module('jq-reconstruction').build('jq-reconstruction', population)[1]
    reference = program_reference.asset(reference_path(),
        expected_sha256=truth['reference_binary_sha256'])
    runtime = runtime_info(IMAGE, reference)
    (output/'runtime.json').write_text(json.dumps(runtime, indent=2)+'\n')
    results = []
    for channel in channels:
        visible, _, manifest = (formation_inputs.build_intended('jq-reconstruction', population, names='numbered')
            if channel == 'direct' else formation_inputs.build('jq-reconstruction', channel, population, names='numbered'))
        registration = {'population':population, 'deployment':{'shared':True},
            'channel_family':manifest['channel_family'], 'reference_program':reference}
        constructor = CommonWorkspace if channel == 'direct' else deployment
        station = constructor(visible['startup'], registration, observation_archive=output/channel/'reads')
        try:
            def participant(actor):
                marker = secrets.token_hex(24)
                filename = '/workspace/runtime-probe.json'
                content = json.dumps({'marker':marker})
                command = ('printf %s ' + shlex.quote(content) + ' > ' + filename
                    + '; /opt/reference/jq -r .marker ' + filename)
                result, _ = station.execute(actor, command)
                if result['exit_code'] or result['stdout'].strip() != marker:
                    raise RuntimeError('Reference tool call failed: '+json.dumps(result))
                observer = station.stations[actor]
                reads = [read for raw in observer.previous.values()
                         for read in observed_reads(raw.decode()) if read['path'] == filename]
                if not any(marker.encode() in base64.b64decode(read['data_base64']) for read in reads):
                    raise RuntimeError('Exact reference input read was not retained for '+actor)
                return {'actor':actor, 'reference_executed':True, 'exact_read_captured':True,
                        'initial_materials_verified':station.bindings[actor]['initial_materials_verified']}
            with ThreadPoolExecutor(max_workers=population) as pool:
                agents = list(pool.map(participant, station.stations))
            results.append({'channel':channel, 'population':population, 'agents':agents,
                'bindings':station.bindings})
            print(f'{channel}: {population} concurrent participants; reference isolation and exact reads passed',flush=True)
        finally:
            station.close()
        (output/(channel+'.json')).write_text(json.dumps(results[-1],indent=2)+'\n')
    result = {'purpose':'software readiness only; no model behavior or study outcomes',
        'created_at':datetime.now(timezone.utc).isoformat(),
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip()),
        'source_sha256':source_digest(),
        'population':population,'channels':list(channels),'image':IMAGE,
        'reference_sha256':reference['sha256'],'model_calls':0,'passed':True}
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    seal_evidence(output)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--population',type=int,default=4)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    if args.population < 2:parser.error('Use N >= 2')
    check(args.out,args.population)
