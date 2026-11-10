"""Select the registered workstation topology without changing agent instructions."""

from swarmform.file_deployment import FileDeployment


def make_deployment(startup, registration, **observations):
    if registration.get('study_mode') == 'swarmform-structure':
        observations['population'] = registration['population']
    settings = registration['deployment']
    if not isinstance(settings.get('shared'), bool):
        raise ValueError('A deployment must declare its shared scope')
    kind = settings.get('kind', 'shared_files')
    if kind == 'shared_files':
        if registration.get('study_mode') == 'swarmform-structure':
            observations['observation_settle_seconds']=registration.get('observation_settle_seconds',2)
        if registration.get('workstation_permissions', {}).get('networkAccess') is not False:
            raise ValueError('The shared-file deployment has no business network')
        return FileDeployment(startup, shared=settings['shared'], profile=settings.get('access_profile','content'), **observations)
    if kind == 'artifact_namespace':
        from swarmform.archive_deployment import ArtifactDeployment
        profile = settings.get('catalog_profile')
        if profile not in ('content', 'metadata', 'state', 'events', 'timing'):
            raise ValueError('The archive catalog profile must be registered')
        if registration.get('workstation_permissions', {}).get('networkAccess') is not True:
            raise ValueError('The archive deployment needs registered business network access')
        return ArtifactDeployment(startup, shared=settings['shared'], profile=profile,
            ready_publication_read=settings.get('ready_publication_read',False), **observations)
    if kind in ('shared_ipc', 'worker_endpoint'):
        network = kind == 'worker_endpoint'
        if registration.get('workstation_permissions', {}).get('networkAccess') is not network:
            raise ValueError('Processor network access differs from the registered deployment')
        if kind == 'shared_ipc':
            from swarmform.ipc_deployment import IPCDeployment as ProcessorDeployment
            return ProcessorDeployment(startup,shared=settings['shared'],profile=settings.get('processor_identity_profile','content'),
                request_group_write=settings.get('request_group_write',False),**observations)
        else:
            from swarmform.endpoint_deployment import EndpointDeployment as ProcessorDeployment
        return ProcessorDeployment(startup, shared=settings['shared'],profile=settings.get('delivery_profile','content'),
            transport=settings.get('endpoint_transport','tcp'), **observations)
    if kind == 'job_namespace':
        if registration.get('workstation_permissions', {}).get('networkAccess') is not True:
            raise ValueError('Processing deployment needs registered business network access')
        from swarmform.job_deployment import JobDeployment
        return JobDeployment(startup, shared=settings['shared'], profile=settings.get('processing_profile','content'),
            completed_result_read=settings.get('completed_result_read',False), **observations)
    raise ValueError('Unknown registered deployment: ' + str(kind))
