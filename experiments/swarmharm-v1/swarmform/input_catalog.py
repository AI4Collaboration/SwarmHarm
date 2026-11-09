"""Business inputs selected by registered deployment and observable fields."""
from swarmform.domain_inputs import build as build_files

ARCHIVE_PROFILES = {'payload_content':'content', 'identifiers_metadata':'metadata',
                    'operational_state':'state', 'event_pattern':'events', 'timing':'timing'}


IMPLEMENTED_ENCODINGS = {
    'shared_files': ('payload_content', 'identifiers_metadata'),
    'shared_ipc': ('payload_content', 'identifiers_metadata', 'operational_state', 'event_pattern'),
    'worker_endpoint': ('payload_content', 'identifiers_metadata', 'operational_state'),
    'artifact_namespace': tuple(ARCHIVE_PROFILES),
    'job_namespace': tuple(ARCHIVE_PROFILES),
}


def business_users(manifest, actors):
    settings=manifest['effective_settings']
    identities=settings.get('business_account_ids',settings.get('account_ids',[65534]*len(actors)))
    if len(identities)!=len(actors):raise ValueError('Business accounts differ from the population')
    return {actor:f'{uid}:{uid}' for actor,uid in zip(actors,identities)}


def observation_registration(manifest, actors):
    from swarmform.read_observer import MAX_TRACE_BYTES,MAX_ACTIVE_BYTES
    result={'scalar_read_maximum_bytes':262144,'trace_storage':'private_disk_volume',
        'trace_bytes_per_log':MAX_TRACE_BYTES,'active_trace_bytes_per_station':MAX_ACTIVE_BYTES,
        'native_instruction_source':'unchanged Codex model catalog','native_provider_http_payloads_captured':False,
        'business_users':business_users(manifest,actors),'business_effective_capabilities':0,
        'observer_container_capabilities':['SYS_PTRACE','SETUID','SETGID','DAC_READ_SEARCH'],
        'closed_trace_policy':'archive_verified_bytes_before_pruning'}
    if manifest['effective_settings']['deployment'] in ('artifact_namespace','job_namespace'):
        from swarmform.service_capture import MAX_FILE,MAX_TOTAL
        result['service_capture']={'max_file_bytes':MAX_FILE,'max_total_bytes':MAX_TOTAL}
    return result


def build(dataset_key, domain='Data Analysis', *, deployment='shared_files',
          encoding='payload_content', shared=True):
    if type(shared) is not bool:
        raise ValueError('Declare shared or private resource scope')
    if deployment == 'shared_files':
        if encoding not in ('payload_content','identifiers_metadata'):
            raise ValueError('File encoding has no implemented access profile')
        visible, truth, manifest = build_files(dataset_key, domain)
        manifest['effective_settings']['shared'] = shared
        if encoding=='identifiers_metadata':
            settings=manifest['effective_settings'];settings.update(file_access_profile='metadata',encoding_opportunity=encoding,
                account_ids=[62000,62001,62002],creation_mask='0077', owner_can_publish_read_permissions=True)
            from hashlib import sha256
            from pathlib import Path
            settings['identity_runtime_sha256']={name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('file_deployment.py','read_observer.py')}
            settings['incidental_paths']=['owner changes file permissions','file size and modes','creation order and timestamps','same-host timing']
        return visible, truth, manifest
    if deployment == 'artifact_namespace':
        from swarmform.artifact_inputs import build as build_archive
        if encoding not in ARCHIVE_PROFILES:
            raise ValueError('Archive encoding has no implemented profile')
        return build_archive(domain, dataset_key, profile=ARCHIVE_PROFILES[encoding], shared=shared)
    if deployment in ('shared_ipc', 'worker_endpoint'):
        supported = IMPLEMENTED_ENCODINGS[deployment]
        if encoding not in supported:
            raise ValueError('This processor encoding is not implemented')
        if deployment == 'shared_ipc':
            from swarmform.ipc_inputs import build as build_processor
            return build_processor(dataset_key,domain,shared=shared,profile=ARCHIVE_PROFILES[encoding])
        else:
            from swarmform.endpoint_inputs import build as build_processor
        return build_processor(dataset_key, domain, shared=shared,profile=ARCHIVE_PROFILES[encoding])
    if deployment == 'job_namespace':
        if encoding not in ARCHIVE_PROFILES:
            raise ValueError('This processing encoding has no implemented profile')
        from swarmform.job_inputs import build as build_jobs
        return build_jobs(dataset_key, domain, shared=shared, profile=ARCHIVE_PROFILES[encoding])
    raise ValueError('Unimplemented workstation deployment: '+str(deployment))


def deployment_registration(manifest):
    settings = manifest['effective_settings']
    if settings['deployment'] == 'shared_files':
        return {'shared':settings['shared'], 'kind':'shared_files', 'network':'none', **({'access_profile':settings['file_access_profile']} if 'file_access_profile' in settings else {})}
    if settings['deployment'] == 'artifact_namespace':
        return {'shared':settings['shared_archive_scope'], 'kind':'artifact_namespace',
                'catalog_profile':settings['catalog_profile'], 'network':settings['network']}
    if settings['deployment'] in ('shared_ipc', 'worker_endpoint'):
        return {'shared': settings['shared'], 'kind': settings['deployment'],
                'network': settings['network'], **({'processor_identity_profile':settings['processor_identity_profile']} if settings['deployment']=='shared_ipc' else {'delivery_profile':settings['delivery_profile']})}
    if settings['deployment'] == 'job_namespace':
        return {'shared': settings['shared_job_scope'], 'kind': 'job_namespace',
                'network': settings['network'], 'processing_profile':settings['processing_profile']}
    raise ValueError('Unknown deployment')


def task_network(deployment):
    """Harbor input description matching the actual business topology."""
    hosts = {'shared_files': [], 'shared_ipc': [],
             'artifact_namespace': ['records'], 'worker_endpoint': ['127.0.0.1', 'localhost', '::1'],
             'job_namespace': ['processor']}
    if deployment not in hosts:
        raise ValueError('Unknown workstation deployment')
    return {'network_mode': 'allowlist' if hosts[deployment] else 'no-network',
            'allowed_hosts': hosts[deployment]}
