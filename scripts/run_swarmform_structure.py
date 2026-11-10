#!/usr/bin/env python3
"""Seal and collect role-neutral scalable SwarmForm business experiments."""
import argparse
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys

import run_swarmform as base
from swarmform.collection import save, utc
from swarmform.structure import (build, verify_solvability, verify_outputs, POPULATIONS, CONDITIONS, DEPLOYMENTS,
    WORKLOADS, build_theory, verify_theory_inputs, theory_output_inventory)
from swarmform.structure_collection import StructureCollection, time_inventory
from swarmform import sustained_research as research
from swarmform.inputs import digest
from swarmform.input_catalog import observation_registration
from guardrails import outside_repository, credential_file

ROOT=base.ROOT
REGISTRATIONS=ROOT/'experiments/structure/registrations'
LEDGER=ROOT/'docs/structure-rollout-status.json'


def write_tasks(output,visible,manifest,duration,deployment):
    theory=manifest.get('workload')=='navier-stokes-theory'
    records=base.write_tasks(output,visible,base.IMAGE,'Engineering' if theory else 'Knowledge Work',deployment,manifest)
    for name in records:
        if name.endswith('/task.toml'):
            path=output/name
            text=path.read_text().replace('execution_adapter = "scripts/run_swarmform.py"',
                'execution_adapter = "scripts/run_swarmform_structure.py"')
            text=text.replace(f'timeout_sec = {base.MAX_AGENT_SECONDS}',f'timeout_sec = {duration}')
            if theory:text=text.replace('Measurement decoder release','Navier-Stokes theoretical research')
            base.TaskConfig.model_validate(base.tomllib.loads(text))
            path.write_text(text);records[name]=base.sha(path)
    return records


def register(args, *, source=None, runtime=None):
    if getattr(args,'context_maintenance',False):
        args.responsive_research=True
        if args.model != 'openai/gpt-6.1-sol':
            raise ValueError('Opaque context maintenance is validated for openai/gpt-6.1-sol only')
    research.resolve_limits(args)
    source=source or base.published_head()
    runtime=runtime or base.check_runtime()
    output=outside_repository(args.output,ROOT,'Structure output')
    if not base.re.fullmatch(r'[a-z0-9][a-z0-9-]{2,100}',args.identifier):
        raise ValueError('Invalid registration identifier')
    folder=REGISTRATIONS/args.identifier
    if output.exists() or folder.exists():raise FileExistsError('Use fresh registration and output paths')
    workload=getattr(args,'workload','knowledge-work');theory=workload=='navier-stokes-theory'
    sustained=getattr(args,'sustained_research',False)
    continuation=getattr(args,'publication_updates',False) or sustained
    if continuation and not theory:
        raise ValueError('Publication updates are currently scoped to the common-problem theory study')
    if theory:
        visible,truth,manifest=build_theory(args.dataset_key,args.population,args.condition,args.deployment,
                                          publication_updates=continuation, sustained_research=sustained,
                                          responsive_research=getattr(args,'responsive_research',False))
        verification=verify_theory_inputs(visible,truth,publication_updates=continuation, sustained_research=sustained)
    else:
        visible,truth,manifest=build(args.dataset_key,args.population,args.condition,args.deployment,
            spacing=args.spacing,customers_per_actor=args.customers,source_schedule=args.source_schedule)
        verification=verify_solvability(visible,truth)
    if not verification['passed']:raise ValueError('Task input verification failed')
    witness=json.loads(Path(args.witness).read_text())
    settling=getattr(args,'observation_settle_seconds',2)
    if type(settling) is not int or settling not in (2,10) or (args.deployment!='shared_files' and settling!=2):
        raise ValueError('Unsupported observation settling configuration')
    same_witness_source=(witness.get('source_commit')==source or witness.get('code_hashes')==
                         {p:base.sha(ROOT/p) for p in base.source_paths()})
    if (witness.get('passed') is not True or witness.get('population')!=args.population
            or witness.get('deployment')!=args.deployment or witness.get('image')!=base.IMAGE
            or not same_witness_source or witness.get('model_calls')!=0):
        raise ValueError('A matching offline runtime witness is required')
    if witness.get('observation_settle_seconds',2)!=settling:
        raise ValueError('Witness settling allowance differs from registration')
    if settling==10 and witness.get('concurrent_rounds')!=3:
        raise ValueError('Extended settling requires the concurrent workload witness')
    if theory and witness.get('workload')!=workload:
        raise ValueError('Common-problem task requires its own matched runtime witness')
    from codex_context import POLICY as CONTEXT_POLICY
    if getattr(args,'context_maintenance',False) and witness.get('context_policy') != CONTEXT_POLICY:
        raise ValueError('Context maintenance requires a matching offline protocol witness')
    output.mkdir(parents=True)
    design='README.md'  # Seal the maintained protocol, not a historical pointer.
    verification_name='input-verification.json' if theory else 'solvability.json'
    shutil.copy2(ROOT/design,output/'study-design.md')
    shutil.copy2(ROOT/'experiments/structure/temporal.py',output/'temporal-review.py')
    for name,value in [('input.json',visible),('protected-truth.json',truth),('input-manifest.json',manifest),
                       (verification_name,verification),('runtime-witness.json',witness)]:save(output/name,value)
    hashes={}
    for relative in base.source_paths():
        destination=output/'code'/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,destination);hashes[relative]=base.sha(destination)
    task_hashes=write_tasks(output,visible,manifest,args.duration,args.deployment)
    harness=base.codex_gateway.harness_registration('off',args.model,
        context_policy=CONTEXT_POLICY if getattr(args,'context_maintenance',False) else None)
    settings=manifest['effective_settings']
    domain='Mathematical Research' if theory else 'Knowledge Work'
    reg={'schema_version':1,'identifier':args.identifier,'created_at':utc(),
        'research_study':'SwarmForm Common Problem' if theory else 'SwarmForm Structure',
        'study_mode':'swarmform-structure','population':args.population,'workload':workload,
        'condition':args.condition,'domain':domain,'input_sha256':digest(manifest),'source_commit':source,
        'observation_settle_seconds':settling,
        'model':args.model,'models':{'openai':args.model},'reasoning':'high','harness':harness,
        'inference_gateway':'axonhub','api_base':base.codex_gateway.AXONHUB_BASE,
        'native_catalog':base.codex_gateway.gateway_catalog(args.model,'high'),
        'workstation_permissions':settings['native_workstation_permissions'],'runtime':runtime,'image':base.IMAGE,
        'deployment':{'kind':args.deployment,'shared':settings['shared'],'access_profile':'content','catalog_profile':'content'},
        'arrival_offsets':settings['arrival_offsets'],
        'budget':{'active_contexts_natural':args.population,'max_agent_seconds':args.duration,
            'max_batch_seconds':args.duration+1800,'request_timeout_seconds':getattr(args,'request_timeout_seconds',300),
            'max_tools_per_agent':args.max_tools,'max_responses_per_agent':args.max_responses,
            'max_observed_tokens_per_agent':args.max_tokens,
            'min_free_bytes':args.min_free_gib*1024**3,
            'stop_policy':'Any agent crossing a measured cap censors the whole rollout; in-flight work may overshoot.'},
        'observation':observation_registration(manifest,visible['startup']),
        'plan':{'natural':{a:{'provider':'openai','domain':domain} for a in visible['startup']}},
        'code_hashes':hashes,'input_hashes':{p:base.sha(output/p) for p in
            ('input.json','protected-truth.json','input-manifest.json',verification_name,'runtime-witness.json',
             'study-design.md','temporal-review.py')},
        'task_hashes':task_hashes,'criteria_source':design,
        'criteria':{'roles_instructed':False,'model_behavior_required':True,
            'temporal_events':['appearance','persistence','turnover','split','merge','role_shift','disappearance'],
            'negative_results_retained':True,'structural_annotations_require_event_references':True}}
    idle=getattr(args,'response_idle_timeout_seconds',None)
    if idle is not None:
        if not 0 < idle <= reg['budget']['request_timeout_seconds']:
            raise ValueError('Idle timeout must be positive and at most the completion limit')
        reg['budget']['response_idle_timeout_seconds']=idle
        reg['response_progress_watchdog']={
            'idle_seconds':idle,'completion_seconds':reg['budget']['request_timeout_seconds'],
            'progress':'nonempty native content deltas, completed items, response usage, turn start',
            'heartbeat_or_retry_extends_idle':False,'streaming_extends_completion_limit':False,
            'controller_restarts_or_followup_prompts':False}
    if theory:
        reg['analysis_window_seconds']=300
        reg['criteria'].update(common_problem=True,identical_initial_materials=True,
            supplied_decomposition=False,mathematical_claims_require_review=True,
            passive_time_windows=True,temporal_minimum_span_seconds=300)
    if continuation:
        reg['publication_updates']=settings['publication_updates']
        reg['criteria']['continuation_is_registered_environment_factor']=True
        if 'response_progress_watchdog' in reg:
            reg['response_progress_watchdog']['scope']='Timeout handling only; publication continuation is registered separately.'
    if sustained:
        reg['sustained_research']=settings['sustained_research']
        reg['criteria'].update(research_persistence_instructed=True, quiescence_is_stop=False)
        reg['response_progress_watchdog']['scope']='Timeout handling only; sustained research continuation is registered separately.'
        research.validate_policy(reg)
    save(output/'registration.json',reg);save(output/'registration-seal.json',{'sha256':base.sha(output/'registration.json')})
    folder.mkdir(parents=True)
    for name in ('registration.json','registration-seal.json'):shutil.copy2(output/name,folder/name)
    ledger_path=ROOT/'docs/structure-common-problem-status.json' if theory else LEDGER
    ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {'study':reg['research_study'],'runs':[]}
    ledger['updated_at']=utc();ledger['runs'].append({'identifier':args.identifier,'population':args.population,
        'condition':args.condition,'deployment':args.deployment,'dataset_key':args.dataset_key,
        'source_schedule':settings['source_schedule'],'workload':workload,'status':'prepared','registration':str(folder.relative_to(ROOT))})
    save(ledger_path,ledger)
    return {'prepared':args.identifier,'output':str(output),'model_calls':0}


def verify_registration(folder,output):
    head=base.published_head()
    reg=json.loads((folder/'registration.json').read_text())
    seal=json.loads((folder/'registration-seal.json').read_text())['sha256']
    if base.sha(folder/'registration.json')!=seal:raise ValueError('Registration seal differs')
    for name in ('registration.json','registration-seal.json'):
        base.git('ls-files','--error-unmatch',str((folder/name).relative_to(ROOT)))
        if base.sha(output/name)!=base.sha(folder/name):raise ValueError('Prepared registration differs')
    source=reg['source_commit']
    if not base.re.fullmatch('[0-9a-f]{40}',source):raise ValueError('Expected a full source commit')
    base.git('merge-base','--is-ancestor',source,head)
    # The execution copy is compared with the committed historical bytes. Main
    # can advance while earlier registrations remain exactly reproducible.
    for name,expected in reg['code_hashes'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('Invalid code path')
        committed=subprocess.check_output(['git','show',source+':'+name],cwd=ROOT)
        if base.sha256(committed).hexdigest()!=expected or base.sha(output/'code'/name)!=expected:
            raise ValueError('Sealed code differs from committed source: '+name)
    for name,expected in {**reg['input_hashes'],**reg['task_hashes']}.items():
        if base.sha(output/name)!=expected:raise ValueError('Prepared input differs: '+name)
    if base.IMAGE!=reg['image'] or base.check_runtime()!=reg['runtime']:
        raise ValueError('Runtime differs from registration')
    base.codex_gateway.verify_runtime(reg['harness'])
    save(output/'collection-preflight.json',{'at':utc(),'local_remote_commit':head,
        'source_commit':source,'source_validation':'exact committed historical bytes and sealed execution copy',
        'registration_sha256':seal,'frozen_inputs_verified':True})
    return reg


def collect(args):
    output=outside_repository(args.output,ROOT,'Structure output')
    if not base.re.fullmatch(r'[a-z0-9][a-z0-9-]{2,100}',args.identifier):raise ValueError('Invalid registration identifier')
    with (output/'.collector.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (output/'started.json').exists():raise FileExistsError('Preserve the original attempt; do not reuse it')
        reg=verify_registration(REGISTRATIONS/args.identifier,output)
        if reg['study_mode']!='swarmform-structure':raise ValueError('Wrong study')
        # Continue from the sealed copy so unrelated main updates cannot change
        # lazy imports or finalization during a long-lived model collection.
        subprocess.run([sys.executable,str(output/'code/scripts/run_swarmform_structure.py'),
            'execute-frozen','--identifier',args.identifier,'--output',str(output),
            '--key-file',str(args.key_file.resolve())],check=True)
        return json.loads((output/'collection-summary.json').read_text())


def verify_execution_copy(output,identifier):
    if ROOT!=(output/'code').resolve():raise ValueError('Execute only from the sealed source copy')
    reg=json.loads((output/'registration.json').read_text())
    seal=json.loads((output/'registration-seal.json').read_text())['sha256']
    preflight=json.loads((output/'collection-preflight.json').read_text())
    if (reg['identifier']!=identifier or reg['study_mode']!='swarmform-structure'
            or base.sha(output/'registration.json')!=seal
            or preflight.get('registration_sha256')!=seal
            or preflight.get('frozen_inputs_verified') is not True):
        raise ValueError('Missing or mismatched committed registration verification')
    for name,expected in reg['code_hashes'].items():
        if base.sha(ROOT/name)!=expected:raise ValueError('Sealed code changed: '+name)
    for name,expected in {**reg['input_hashes'],**reg['task_hashes']}.items():
        if base.sha(output/name)!=expected:raise ValueError('Sealed input changed: '+name)
    return reg


def execute_frozen(args):
    output=args.output.resolve()
    reg=verify_execution_copy(output,args.identifier)
    if (output/'started.json').exists():raise FileExistsError('Preserve the original attempt')
    key=credential_file(args.key_file,ROOT).read_text().strip()
    visible=json.loads((output/'input.json').read_text())
    result=StructureCollection(output,reg,visible,api_key=key).run()
    return finalize(output,reg,visible,result)


def finalize(output,reg,visible,result):
    from swarmform.actor_evidence import finalize_actor_evidence, require_unfinalized, seal_collection
    require_unfinalized(output)
    failures=[]
    if result.get('failure') and result['reason']!='resource_budget':failures.append('collection')
    try:
        terminals=json.loads((output/'terminal-snapshots.json').read_text())
        snapshots={a:json.loads((output/p).read_text())['snapshot'] for a,p in terminals.items()}
        truth=json.loads((output/'protected-truth.json').read_text())
        if reg.get('workload')=='navier-stokes-theory':
            save(output/'research-output-inventory.json',theory_output_inventory(snapshots))
        else:save(output/'business-outcome.json',verify_outputs(visible,truth,snapshots))
    except Exception as error:
        failures.append('outcome');save(output/'outcome-error.json',{'error':repr(error)})
    try:
        save(output/'temporal-inventory.json',time_inventory(output,reg))
    except Exception as error:
        failures.append('temporal');save(output/'temporal-inventory-failure.json',{'error':repr(error)})
    if research.responsive(reg):
        try:
            from swarmform.research_timing import inventory as latency_inventory
            save(output/'research-latency-summary.json',latency_inventory(output,reg))
        except Exception as error:
            failures.append('latency');save(output/'research-latency-failure.json',{'error':repr(error)})
    coverage,evidence_failures=finalize_actor_evidence(output,reg)
    failures.extend(evidence_failures)
    summary={'closed':reg['identifier'],'reason':result['reason'],'failures':failures,
             'output':str(output),'structural_review':'pending','censored':result['reason'] != 'quiescence',
             'actor_evidence_complete':bool(coverage and coverage['actor_evidence_complete'])}
    if reg.get('sustained_research'):
        summary.update(planned_window_completed=result['reason']=='research_window_elapsed',
            early_termination=result['reason']!='research_window_elapsed',
            censoring_scope='Observation ends at a planned window or earlier limit; no claim of mathematical or structural completion.')
    return seal_collection(output,summary)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    preview=sub.add_parser('preview-sustained',help='Render exact inputs and policies without a registration or model call')
    preview.add_argument('--output',type=Path,required=True)
    responsive_preview=sub.add_parser('preview-responsive',help='Render instrumented responsive scheduling without a rollout')
    responsive_preview.add_argument('--output',type=Path,required=True)
    context_preview=sub.add_parser('preview-context',help='Render matched opaque context policy without a rollout')
    context_preview.add_argument('--output',type=Path,required=True)
    prepare=sub.add_parser('prepare');collect_parser=sub.add_parser('collect')
    worker=sub.add_parser('execute-frozen',help='Internal sealed execution after committed preflight')
    for command in (prepare,collect_parser,worker):
        command.add_argument('--identifier',required=True);command.add_argument('--output',type=Path,required=True)
    prepare.add_argument('--population',type=int,choices=POPULATIONS,required=True)
    prepare.add_argument('--workload',choices=WORKLOADS,default='knowledge-work')
    prepare.add_argument('--condition',choices=CONDITIONS,required=True)
    prepare.add_argument('--deployment',choices=DEPLOYMENTS,default='shared_files')
    prepare.add_argument('--model',choices=['openai/gpt-6.1-sol'],default='openai/gpt-6.1-sol')
    prepare.add_argument('--dataset-key',required=True);prepare.add_argument('--witness',type=Path,required=True)
    prepare.add_argument('--source-schedule',choices=['fixed','changing'],default='fixed')
    prepare.add_argument('--spacing',type=int,default=600);prepare.add_argument('--duration',type=int)
    prepare.add_argument('--customers',type=int,default=8);prepare.add_argument('--max-tools',type=int)
    prepare.add_argument('--max-responses',type=int);prepare.add_argument('--max-tokens',type=int)
    prepare.add_argument('--min-free-gib',type=int)
    prepare.add_argument('--request-timeout-seconds',type=int)
    prepare.add_argument('--response-idle-timeout-seconds',type=int)
    prepare.add_argument('--observation-settle-seconds',type=int,choices=[2,10],default=2)
    prepare.add_argument('--publication-updates', action='store_true',
                         help='Opt in to same-session continuation on actual changed publication content; theory only')
    prepare.add_argument('--sustained-research',action='store_true',
                         help='Use the fixed matched 90-minute theory policy; no quiescence exit')
    prepare.add_argument('--responsive-research',action='store_true',
                         help='Opt in to matched latency recording and responsive scheduling; implies sustained research')
    prepare.add_argument('--context-maintenance',action='store_true',
                         help='Opt in to matched opaque native compaction; implies responsive research')
    collect_parser.add_argument('--key-file',type=Path,required=True)
    worker.add_argument('--key-file',type=Path,required=True)
    args=parser.parse_args()
    if args.command in ('preview-sustained','preview-responsive','preview-context'):
        from swarmform.research_preview import write_preview
        print(json.dumps(write_preview(args.output,responsive=args.command!='preview-sustained',
            context_maintenance=args.command=='preview-context'),indent=2))
        return
    if args.command=='prepare':
        if args.context_maintenance:args.responsive_research=True
        try:research.resolve_limits(args)
        except ValueError as error:parser.error(str(error))
        if min(args.duration,args.max_tools,args.max_responses,args.max_tokens,args.min_free_gib,args.request_timeout_seconds)<1:
            parser.error('Budgets must be positive')
        if args.workload=='knowledge-work' and args.duration<=4*args.spacing:
            parser.error('Leave time after the last real intake')
        if args.workload=='navier-stokes-theory' and (args.population!=8 or args.condition=='isolated' or args.deployment!='shared_files'):
            parser.error('The common-problem theory study uses eight members and intended/unintended shared files')
    value=register(args) if args.command=='prepare' else collect(args) if args.command=='collect' else execute_frozen(args)
    print(json.dumps(value,ensure_ascii=False,indent=2))
    if value.get('failures'):raise SystemExit(1)


if __name__=='__main__':main()
