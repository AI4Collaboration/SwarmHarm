import argparse
import json
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
        key['project_id'] = project['id']
        return key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['inventory', 'create', 'disable', 'export', 'prices', 'quota', 'token-quota', 'recording', 'limits'])
    parser.add_argument('value', nargs='?')
    args = parser.parse_args()
    gateway = Gateway()
    if args.mode == 'limits':
        data = gateway.gql('''query($id:ID!){requests(first:100,where:{apiKeyID:$id}){
          edges{node{id status executions{edges{node{id channelID status responseStatusCode responseHeaders errorMessage}}}}}
        }}''', {'id': args.value})
        rows = []
        for request in data['requests']['edges']:
            for execution in request['node']['executions']['edges']:
                node = execution['node']
                if node['responseStatusCode'] == 429:
                    node['responseHeaders'] = {name: value for name, value in (node['responseHeaders'] or {}).items()
                        if any(term in name.lower() for term in ('rate', 'reset', 'retry', 'date', 'limit'))}
                    rows.append({'request_id': request['node']['id'], **node})
        print(json.dumps(rows))
    elif args.mode == 'recording':
        data = gateway.gql('''query {
          storagePolicy { storeChunks storeRequestBody storeResponseBody }
          defaultDataStorageID
          dataStorages(first:100) { edges { node { id type status settings { s3 { bucketName endpoint region pathStyle } } } } }
          channels(first:100) { edges { node { id name status supportedModels liveLimiterStats { inFlight waiting capacity queueSize } } } }
        }''')
        assert all(data['storagePolicy'].values())
        print(json.dumps(data))
    elif args.mode == 'create':
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
        edges = []
        cursor = None
        pages = 0
        while True:
            data = gateway.gql('''query($id:ID!,$cursor:Cursor){requests(first:100,after:$cursor,where:{apiKeyID:$id}){
          pageInfo { hasNextPage endCursor } edges{node{
          id projectID dataStorageID createdAt updatedAt modelID reasoningEffort status requestBody responseBody
          contentSaved responseChunks
          executions(first:100) { pageInfo { hasNextPage } edges { node { id projectID dataStorageID upstreamModelID reasoningEffort status responseStatusCode
          channelID channelAPIKeyIndex externalID channel { id name type }
          metricsLatencyMs metricsFirstTokenLatencyMs metricsReasoningDurationMs
          requestBody responseBody responseChunks errorMessage passThroughApplied } } }
          usageLogs { edges { node { id promptTokens completionTokens totalTokens promptCachedTokens totalCost } } }
        }}} apiKeyQuotaUsages(apiKeyId:$id){profileName usage{requestCount totalTokens totalCost}}}''', {'id': args.value, 'cursor': cursor})
            pages += 1
            edges.extend(data['requests']['edges'])
            for edge in data['requests']['edges']:
                assert not edge['node']['executions']['pageInfo']['hasNextPage']
            if not data['requests']['pageInfo']['hasNextPage']:
                break
            cursor = data['requests']['pageInfo']['endCursor']
            assert cursor
        data['requests']['edges'] = edges
        data['request_pages'] = pages
        assert len({edge['node']['id'] for edge in edges}) == len(edges)
        print(json.dumps(data))


if __name__ == '__main__':
    main()
