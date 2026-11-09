"""Business inputs selected by registered deployment and observable fields."""
from swarmform.domain_inputs import build as build_files

ARCHIVE_PROFILES = {'payload_content':'content', 'identifiers_metadata':'metadata',
                    'operational_state':'state'}


def build(dataset_key, domain='Data Analysis', *, deployment='shared_files',
          encoding='payload_content', shared=True):
    if type(shared) is not bool:
        raise ValueError('Declare shared or private resource scope')
    if deployment == 'shared_files':
        if encoding != 'payload_content':
            raise ValueError('This file deployment exposes payload content')
        visible, truth, manifest = build_files(dataset_key, domain)
        manifest['effective_settings']['shared'] = shared
        return visible, truth, manifest
    if deployment == 'artifact_namespace':
        from swarmform.artifact_inputs import build as build_archive
        if encoding not in ARCHIVE_PROFILES:
            raise ValueError('Archive encoding has no implemented profile')
        return build_archive(domain, dataset_key, profile=ARCHIVE_PROFILES[encoding], shared=shared)
    raise ValueError('Unimplemented workstation deployment: '+str(deployment))


def deployment_registration(manifest):
    settings = manifest['effective_settings']
    if settings['deployment'] == 'shared_files':
        return {'shared':settings['shared'], 'kind':'shared_files', 'network':'none'}
    if settings['deployment'] == 'artifact_namespace':
        return {'shared':settings['shared_archive_scope'], 'kind':'artifact_namespace',
                'catalog_profile':settings['catalog_profile'], 'network':settings['network']}
    raise ValueError('Unknown deployment')
