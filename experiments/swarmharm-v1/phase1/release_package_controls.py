"""Operator-only ordinary package publication; no communication codebook here."""
import time
from phase1 import release_packages as packages, release_workflow
from phase1 import engineering_carriers as carriers


def source_from_returns(witness, actor):
    if release_workflow.enabled(witness.world.plan[actor]):
        status = witness.call(actor, 'release_package_status', {})
        return 'RELEASE = ' + repr(packages.expected(witness.world.plan[actor], status['filing']['submissions'])) + '\n'
    rows = {}
    for e in witness.world.events:
        if e['actor'] == actor and e['operation'] == 'submit_review' and e['result']['status'] == 202:
            rows[e['arguments']['check_id']] = {**e['arguments'],
                'confirmation_reference':e['result']['confirmation_reference']}
    item = witness.world.plan[actor]
    body = {'release_id':item['business_pressure']['contract_reference'], 'batch_id':item['batch_id'],
            'checks':[rows[k] for k in sorted(rows)]}
    return 'RELEASE = ' + repr(body) + '\n'


def publish(witness, actor, source=None, *, mode='clean', consume=True, package=packages.PACKAGE, stage_candidate=True):
    if stage_candidate and package == packages.PACKAGE and packages.staged(witness.world.plan[actor]):
        publish(witness,actor,source,mode=mode,consume=consume,package=packages.CANDIDATE)
    source = source_from_returns(witness, actor) if source is None else source
    call = lambda op, **args:witness.call(actor,op,args)
    saved = call('save_build_artifact',name='release-config',content=source)
    if saved['status'] != 200: raise RuntimeError('Package artifact was not saved')
    if carriers.inventory_enabled(witness.world.plan[actor]):
        page, found = 1, None
        while found is None:
            inventory = call('list_build_artifacts',page=page,per_page=30)
            found = next((row for row in inventory['artifacts'] if row['name']=='release-config'), None)
            if page*30 >= inventory['total_count']: break
            page += 1
        if found != {'name':'release-config','size_in_bytes':len(source.encode()),'sha256':saved['sha256']}:
            raise RuntimeError('Saved package is absent or changed in the artifact inventory')
    build = call('submit_build',component='release-config',source=source,mode=mode)
    if build['status'] != 202: raise RuntimeError('Package build was not admitted')
    deadline = time.monotonic()+35
    while time.monotonic()<deadline:
        state = call('build_status',build_id=build['build_id'])['state']
        if state in ('completed','failed'): break
        time.sleep(.01)
    else: raise TimeoutError('Package build did not finish')
    if consume:
        while True:
            report = call('read_build_result')['report']
            if report is None: raise RuntimeError('Package compiler report was not available')
            if report['build_id'] == build['build_id']: break
    lease = call('acquire_release_lock',package=package)
    if not lease.get('acquired'): raise RuntimeError('Package release lock was not acquired')
    try:
        result = call('publish_build_artifact',name='release-config',lease=lease['lease'])
    finally:
        call('release_release_lock',lease=lease['lease'])
    if result['status'] != 201: raise RuntimeError('Package bytes were not published')
    return result


def publish_all(witness):
    results = {a:publish(witness,a) for a in witness.world.plan}
    return {**({'ready_candidates':sum(witness.world.release_packages.candidate_status(a)['state']=='ready'
                                      for a in witness.world.plan)}
               if packages.staged(next(iter(witness.world.plan.values()))) else {}),
            'ready_packages':sum(r['release_package']['state']=='ready' for r in results.values()),
            'publications':results}
