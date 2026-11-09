"""Select the registered workstation topology without changing agent instructions."""

from swarmform.file_deployment import FileDeployment


def make_deployment(startup, registration, **observations):
    settings = registration['deployment']
    if not isinstance(settings.get('shared'), bool):
        raise ValueError('A deployment must declare its shared scope')
    kind = settings.get('kind', 'shared_files')
    if kind == 'shared_files':
        if registration.get('workstation_permissions', {}).get('networkAccess') is not False:
            raise ValueError('The shared-file deployment has no business network')
        return FileDeployment(startup, shared=settings['shared'], **observations)
    if kind == 'artifact_namespace':
        from swarmform.archive_deployment import ArtifactDeployment
        profile = settings.get('catalog_profile')
        if profile not in ('content', 'metadata', 'state'):
            raise ValueError('The archive catalog profile must be registered')
        if registration.get('workstation_permissions', {}).get('networkAccess') is not True:
            raise ValueError('The archive deployment needs registered business network access')
        return ArtifactDeployment(startup, shared=settings['shared'], profile=profile, **observations)
    raise ValueError('Unknown registered deployment: ' + str(kind))
