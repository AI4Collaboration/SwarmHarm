"""Saved artifact identities and independent resolution from preceding writes."""
from phase1 import release_workflow


def name(reference):
    return reference['name'] if isinstance(reference, dict) else reference


def metadata(name, record):
    return {'artifact': {'name': name, 'version': record['version']},
            'recorded_by': record['actor']}


def sources(plan, events):
    """Resolve build bytes from earlier successful saves, never terminal jobs."""
    versions, resolved = {}, {}
    for event in events:
        args, result = event['arguments'], event['result']
        if event['operation'] == 'save_build_artifact' and result.get('status') == 200:
            reference = result.get('artifact')
            if reference:
                key = reference['name'], reference['version']
                if key in versions and versions[key] != args['content']:
                    raise ValueError('Artifact revision bytes changed')
                versions[key] = args['content']
        if event['operation'] == 'submit_build' and result.get('status') == 202:
            source = args['source']
            if isinstance(source, dict):
                if not release_workflow.artifact_revisions(plan[event['actor']]):
                    raise ValueError('Saved-source reference absent from this revision')
                try:
                    source = versions[source['name'], source['version']]
                except KeyError as exc:
                    raise ValueError('Build references an unsaved artifact revision') from exc
            resolved[event['id']] = source
    return resolved
