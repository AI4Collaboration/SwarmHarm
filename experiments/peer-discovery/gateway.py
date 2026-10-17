import argparse
import json
import subprocess
import time
from pathlib import Path

import requests


BASE = 'http://127.0.0.1:8090'
FIELDS = '''id name type status scopes profiles { activeProfile profiles {
name modelIDs modelMappings { from to } quota { requests totalTokens period { type } }
} }'''


class Gateway:
    def __init__(self):
        credentials = json.loads(Path('/opt/swarmharm/admin-credentials.json').read_text())['axonhub']
        self.session = requests.Session()
        response = self.session.post(BASE + '/admin/auth/signin', json=credentials, timeout=30)
        response.raise_for_status()
        self.session.headers['Authorization'] = 'Bearer ' + response.json()['token']

    def gql(self, query, variables=None):
        response = self.session.post(BASE + '/admin/graphql', json={'query': query, 'variables': variables or {}}, timeout=120)
        response.raise_for_status()
        body = response.json()
        assert not body.get('errors'), body
        return body['data']

    def create(self, name):
        projects = self.gql('query { projects(first:100) { edges { node { id name } } } }')
        matches = [e['node'] for e in projects['projects']['edges'] if e['node']['name'] == 'SWH-77-peer-discovery']
        if matches:
            project = matches[0]
        else:
            project = self.gql('mutation($i:CreateProjectInput!){ createProject(input:$i){id name}}', {'i': {'name': 'SWH-77-peer-discovery'}})['createProject']
        key = self.gql('mutation($i:CreateAPIKeyInput!){createAPIKey(input:$i){id key name}}', {'i': {
            'name': name, 'type': 'user', 'scopes': ['read_channels', 'write_requests'], 'projectID': project['id']}})['createAPIKey']
        profile = {'activeProfile': 'experiment', 'profiles': [{'name': 'experiment', 'modelIDs': ['gpt-6-luna'],
            'modelMappings': [], 'quota': {'requests': 100, 'totalTokens': 200000, 'period': {'type': 'all_time'}}}]}
        key['configuration'] = self.gql('mutation($id:ID!,$i:UpdateAPIKeyProfilesInput!){updateAPIKeyProfiles(id:$id,input:$i){' + FIELDS + '}}', {'id': key['id'], 'i': profile})
        return key

    def export(self, key_id):
        edges = []
        cursor = None
        pages = 0
        while True:
            data = self.gql('''query($id:ID!,$after:Cursor){requests(first:100,after:$after,where:{apiKeyID:$id}){
              pageInfo{hasNextPage endCursor} edges{node{
              id createdAt updatedAt projectID dataStorageID channelID modelID reasoningEffort status stream
              requestBody responseBody responseChunks
              executions(first:100){pageInfo{hasNextPage} edges{node{
              id upstreamModelID reasoningEffort status responseStatusCode requestBody responseBody responseChunks
              errorMessage passThroughApplied }}}
              usageLogs(first:100){pageInfo{hasNextPage} edges{node{
              id promptTokens completionTokens totalTokens promptCachedTokens totalCost }}}
            }}} apiKeyQuotaUsages(apiKeyId:$id){profileName usage{requestCount totalTokens totalCost}}}''',
                {'id': key_id, 'after': cursor})
            page = data['requests']
            pages += 1
            for edge in page['edges']:
                assert not edge['node']['executions']['pageInfo']['hasNextPage']
                assert not edge['node']['usageLogs']['pageInfo']['hasNextPage']
            edges.extend(page['edges'])
            if not page['pageInfo']['hasNextPage']:
                return {'requests': {'edges': edges}, 'apiKeyQuotaUsages': data['apiKeyQuotaUsages'], 'pages': pages}
            assert page['pageInfo']['endCursor'] != cursor
            cursor = page['pageInfo']['endCursor']

    def recording(self):
        data = self.gql('''query {storagePolicy{storeChunks storeRequestBody storeResponseBody}
          defaultDataStorageID dataStorages(first:100){edges{node{id name type status settings{
          s3{bucketName endpoint region pathStyle}}}}}
          channels(first:100){edges{node{id status supportedModels liveLimiterStats{inFlight waiting capacity queueSize}}}}
        }''')
        assert all(data['storagePolicy'].values())
        data['observed_at'] = time.time()
        data['host_resources'] = {
            name: subprocess.run(command, check=True, capture_output=True, text=True).stdout
            for name, command in {'memory': ['free', '-b'], 'disk': ['df', '-B1', '/'], 'load': ['uptime'],
                                  'cpu': ['vmstat', '1', '2']}.items()}
        return data

    def progress(self, ids):
        declarations = ','.join(f'$id{index}:ID!' for index in range(len(ids)))
        fields = ' '.join(
            f'r{index}:requests(first:1,where:{{apiKeyID:$id{index}}}){{totalCount edges{{node{{id createdAt status modelID}}}}}} '
            f'q{index}:apiKeyQuotaUsages(apiKeyId:$id{index}){{usage{{requestCount totalTokens}}}}'
            for index in range(len(ids)))
        data = self.gql(f'query({declarations}){{{fields}}}', {f'id{index}': value for index, value in enumerate(ids)})
        return [{'api_key_id': value, 'requests': data[f'r{index}'], 'quota': data[f'q{index}']}
                for index, value in enumerate(ids)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['inventory', 'create', 'disable', 'export', 'recording', 'progress', 'prices', 'quota', 'token-quota'])
    parser.add_argument('value', nargs='?')
    args = parser.parse_args()
    gateway = Gateway()
    if args.mode == 'create':
        print(json.dumps(gateway.create(args.value)))
    elif args.mode == 'disable':
        print(json.dumps(gateway.gql('mutation($id:ID!){updateAPIKeyStatus(id:$id,status:disabled){' + FIELDS + '}}', {'id': args.value})))
    elif args.mode in ('quota', 'token-quota'):
        quota = {'requests': 5, 'totalTokens': 200000, 'period': {'type': 'all_time'}}
        if args.mode == 'token-quota':
            usage = gateway.gql('query($id:ID!){apiKeyQuotaUsages(apiKeyId:$id){usage{totalTokens}}}', {'id': args.value})
            quota = {'requests': 100, 'totalTokens': usage['apiKeyQuotaUsages'][0]['usage']['totalTokens'] + 1, 'period': {'type': 'all_time'}}
        profile = {'activeProfile': 'experiment', 'profiles': [{'name': 'experiment', 'modelIDs': ['gpt-6-luna'],
            'modelMappings': [], 'quota': quota}]}
        print(json.dumps(gateway.gql('mutation($id:ID!,$i:UpdateAPIKeyProfilesInput!){updateAPIKeyProfiles(id:$id,input:$i){' + FIELDS + '}}', {'id': args.value, 'i': profile})))
    elif args.mode == 'inventory':
        print(json.dumps(gateway.gql('''query { channels(first:100) { edges { node {
            id name type status supportedModels settings { modelMappings { from to } }
        } } } }''')))
    elif args.mode == 'prices':
        print(json.dumps(gateway.gql('''query {
          models(first:100,where:{modelID:"gpt-6-luna"}) {edges{node{modelID modelCard{cost{input output cacheRead cacheWrite}}}}}
          channels(first:100){edges{node{id name status supportedModels liveLimiterStats{inFlight waiting capacity queueSize}
          channelModelPrices{modelID referenceID price{items{itemCode pricing{mode flatFee usagePerUnit}}}}}}}
        }''')))
    elif args.mode == 'export':
        print(json.dumps(gateway.export(args.value)))
    elif args.mode == 'recording':
        print(json.dumps(gateway.recording()))
    elif args.mode == 'progress':
        print(json.dumps(gateway.progress(json.loads(args.value))))


if __name__ == '__main__':
    main()
