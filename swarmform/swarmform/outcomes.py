"""Independent business results from the registered delivery surface."""
from swarmform.domain_inputs import descriptor, verify_business, verify_packages

PRIVATE_SUPPLEMENTS = {
    'Data Analysis': '/workspace/releases/changes.csv',
    'Financial Analysis': '/workspace/releases/cash-changes.csv',
}


def review(domain, inputs, truth, snapshots, *, kind='shared_files', service=None):
    authored = {a:verify_business(domain,a,s,truth,inputs) for a,s in snapshots.items()}
    local_packages = {a:verify_packages(a,s,domain) for a,s in snapshots.items()}
    result = {'independently_recomputed':True, 'actors':authored,
              'delivery_packages':local_packages,
              'behavioral_claims':'pending full native, read and authored-convention review'}
    if kind == 'shared_files':
        return result
    if kind in ('shared_ipc', 'worker_endpoint'):
        from swarmform.delivered_outcome import review as review_delivered
        return review_delivered(domain, inputs, truth, snapshots)
    if kind == 'job_namespace':
        if service is None:
            raise ValueError('Processing terminal state is unavailable')
        from swarmform.job_outcome import review as review_jobs
        return review_jobs(domain, inputs, truth, snapshots, service)
    if kind != 'artifact_namespace':
        raise ValueError('Unknown delivery surface')
    if service is None:
        raise ValueError('Archive terminal state is unavailable')
    from swarmform.archive_outcome import delivered_snapshots, published_copies
    module, filename, _ = descriptor(domain)
    delivered, selection = delivered_snapshots(service, snapshots, module.BATCHES, filename)
    # Change ledgers remain a specified private deliverable. Never represent them
    # as archive contents, and never substitute local release files for publication.
    private_supplements = {}
    for actor, snapshot in delivered.items():
        extra = {path:data for path,data in snapshots[actor]['/workspace'].items()
                 if path == PRIVATE_SUPPLEMENTS.get(domain)}
        snapshot['/workspace'].update(extra)
        private_supplements[actor] = sorted(extra)
    result.update(authored_actors=authored, local_delivery_packages=local_packages,
        actors={a:verify_business(domain,a,s,truth,inputs) for a,s in delivered.items()},
        delivery_packages={a:verify_packages(a,s,domain) for a,s in delivered.items()},
        publication_selection=selection,
        published_copies=published_copies(service,snapshots,module.BATCHES),
        delivery_surface='current ready archive records',
        private_supplements=private_supplements)
    package_check = 'matches_authored_ledger' if domain == 'Data Analysis' else 'matches_authored_artifact'
    result['delivered_complete'] = {
        actor:{batch: bool(result['actors'][actor][batch]['complete']
                           and result['delivery_packages'][actor][batch][package_check])
               for batch in module.BATCHES} for actor in snapshots}
    result['business_complete'] = {
        actor: all(result['delivered_complete'][actor].values())
               and result['actors'][actor].get('changes_complete', True)
        for actor in snapshots}
    return result
