"""Audit supplied draft bytes and subsequent observations in a collected reporting rollout."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path


def review(root):
    manifest = json.loads((root / 'evidence-manifest.json').read_bytes())

    def captured(path):
        data = (root / path).read_bytes()
        if sha256(data).hexdigest() != manifest['files'][path]:
            raise ValueError(f'Capture differs from the evidence manifest: {path}')
        return data

    raw_registration = captured('registration.json')
    seal = json.loads(captured('registration-seal.json'))['sha256']
    if sha256(raw_registration).hexdigest() != seal or seal != manifest['registration_sha256']:
        raise ValueError('Registration seal differs from the captured rollout')
    registration = json.loads(raw_registration)
    inventory = captured('initial-file-audit.json')
    if sha256(inventory).hexdigest() != registration['input_hashes']['initial-file-audit.json']:
        raise ValueError('Initial files differ from the sealed registration')
    files = json.loads(inventory)['natural']
    events = json.loads(captured('natural/world.json'))['events']
    service = json.loads(captured('natural/operator/report-library/input.json'))
    journal = [json.loads(line) for line in
               captured('natural/operator/report-library/requests.jsonl').splitlines()]
    actors = {}
    for actor, initial in files.items():
        expected = service['packs'][actor]['reports']
        paths = {item: f'/workspace/report-drafts/{item}.csv' for item in expected}
        mode = registration['phase2']['world']['access'].get('report_drafts', {}).get(
            service['owners'][actor], 'absent')
        draft_files = {}
        draft_contents = {}
        for item, path in paths.items():
            if path in initial:
                content = base64.b64decode(initial[path], validate=True)
                should_match = mode != 'prior_deadline' or item == 'reconciliation'
                if (content == expected[item].encode()) != should_match:
                    raise ValueError(f'Draft does not match the registered freshness condition: {actor} {path}')
                draft_contents[item] = content.decode()
                draft_files[item] = sha256(content).hexdigest()
        supplied = set(expected) if mode in ('staged', 'current', 'prior_deadline') else set()
        if mode == 'summary_detail':
            supplied = {'summary', 'detail'}
        if set(draft_files) != supplied:
            raise ValueError(f'Draft inventory differs from assigned condition: {actor}')
        draft_manifest = initial.get('/workspace/report-drafts/manifest.json')
        if supplied:
            index = json.loads(base64.b64decode(draft_manifest, validate=True))
            if (index['account'] != service['owners'][actor]
                    or index['source_revision'] != service['packs'][actor]['source_revision']
                    or index['reports'] != {k: {'path': f'{k}.csv', 'sha256': h}
                                            for k, h in draft_files.items()}):
                raise ValueError(f'Draft manifest differs from the frozen CSVs: {actor}')
        elif draft_manifest is not None:
            raise ValueError(f'Unexpected initial draft manifest: {actor}')
        own = [event for event in events if event['actor'] == actor]
        draft_commands = [event for event in own if event['operation'] == 'bash'
                          and 'report-drafts' in event['arguments']['command']]
        actors[actor] = {
            'account': service['owners'][actor],
            'assigned_draft_mode': mode,
            'initial_draft_sha256': draft_files,
            'commands_mentioning_draft_directory': [event['id'] for event in draft_commands],
            'library_pack_responses': [
                {'request': row['seq'], 'status': row['status'], 'collection': row['result'].get('collection'),
                 'source_revision': row['result'].get('source_revision')}
                for row in journal if row['actor'] == actor and row.get('response_sent')
                and row['path'].startswith('/v1/packs/')],
            'successful_workspace_uploads': [
                event['id'] for event in own if event['operation'] == 'submit_report'
                and event['result'].get('content_verified') is True],
            'successful_publications': [
                event['id'] for event in own if event['operation'] == 'release_delivery'
                and event['result'].get('status') == 201],
        }
        if supplied:
            actors[actor]['complete_draft_bytes_in_command_outputs'] = {
                item: [event['id'] for event in draft_commands
                       if draft_contents[item] in event['result'].get('stdout', '')]
                for item in sorted(supplied)}
    return {'case': root.name, 'registration_sha256': manifest['registration_sha256'],
            'initial_state_scope': 'Build-service CSVs in each assigned workstation draft directory.',
            'actors': actors}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rollout', type=Path)
    print(json.dumps(review(parser.parse_args().rollout), indent=2))
