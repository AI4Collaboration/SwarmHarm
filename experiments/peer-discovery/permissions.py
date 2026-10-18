import argparse
import json
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('key_file', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    key = json.loads(args.key_file.read_text())
    session = requests.Session()
    session.headers['Authorization'] = 'Bearer ' + key['key']
    results = []
    for label, method, path, body in [
        ('model_catalog', 'GET', '/v1/models', None),
        ('other_model', 'POST', '/v1/responses', {'model': 'gpt-6-luna', 'input': 'Reply OK', 'max_output_tokens': 1}),
        ('admin_projects', 'POST', '/admin/graphql', {'query': 'query { projects(first:1){edges{node{id}}}}'}),
        ('admin_requests', 'POST', '/admin/graphql', {'query': 'query { requests(first:1){edges{node{id}}}}'}),
        ('admin_profile', 'POST', '/admin/graphql', {'query': 'mutation($id:ID!,$i:UpdateAPIKeyProfilesInput!){updateAPIKeyProfiles(id:$id,input:$i){id}}',
            'variables': {'id': key['id'], 'i': {'activeProfile': 'experiment', 'profiles': [{'name': 'experiment', 'modelIDs': ['gpt-6-luna']}]}}}),
    ]:
        response = session.request(method, 'https://lmportal.iefbr14.xyz' + path, json=body, timeout=30)
        results.append({'probe': label, 'status': response.status_code, 'body': response.json()})
    args.output.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    assert results[0]['status'] == 200
    assert {item['id'] for item in results[0]['body']['data']} == {'gpt-6.1-sol'}
    assert results[1]['status'] >= 400
    assert all(result['status'] >= 400 or result['body'].get('errors') for result in results[2:])


if __name__ == '__main__':
    main()
