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
        return key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['inventory', 'create', 'disable', 'export', 'prices', 'quota', 'token-quota', 'recording-policy', 'recording-export'])
    parser.add_argument('value', nargs='?')
    args = parser.parse_args()
    gateway = Gateway()
    if args.mode == 'recording-policy':
        data = gateway.gql('''query {
          storagePolicy { storeChunks storeRequestBody storeResponseBody }
          defaultDataStorageID
          dataStorages(first:50) { edges { node { id name type status settings { s3 { bucketName region endpoint pathStyle } } } } }
          projects(first:100) { edges { node { id name } } }
          channels(first:100) { edges { node { id status supportedModels liveLimiterStats { inFlight waiting capacity queueSize } } } }
        }''')
        assert all(data['storagePolicy'].values())
        print(json.dumps(data))
    elif args.mode == 'recording-export':
        edges = []
        cursor = None
        while True:
            page = gateway.gql('''query($id:ID!,$cursor:Cursor) {
              requests(first:100,after:$cursor,where:{apiKeyID:$id}) {
                pageInfo { hasNextPage endCursor }
                edges { node { id createdAt updatedAt status modelID reasoningEffort
                  executions(first:100) { pageInfo { hasNextPage } edges { node {
                    id channelID upstreamModelID reasoningEffort status responseStatusCode errorMessage
                    metricsLatencyMs metricsFirstTokenLatencyMs metricsReasoningDurationMs
                  } } }
                  usageLogs { edges { node { id promptTokens completionTokens totalTokens promptCachedTokens totalCost } } }
                } }
              }
            }''', {'id': args.value, 'cursor': cursor})['requests']
            assert all(not edge['node']['executions']['pageInfo']['hasNextPage'] for edge in page['edges'])
            edges.extend(page['edges'])
            if not page['pageInfo']['hasNextPage']:
                break
            cursor = page['pageInfo']['endCursor']
            assert cursor
        quota = gateway.gql('query($id:ID!){apiKeyQuotaUsages(apiKeyId:$id){profileName usage{requestCount totalTokens totalCost}}}', {'id': args.value})
        print(json.dumps({'requests': {'edges': edges}, **quota}))
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
        print(json.dumps(gateway.gql('''query($id:ID!){requests(first:1000,where:{apiKeyID:$id}){edges{node{
          id createdAt updatedAt modelID reasoningEffort status requestBody responseBody
          executions { edges { node { id upstreamModelID reasoningEffort status responseStatusCode
          requestBody responseBody errorMessage passThroughApplied } } }
          usageLogs { edges { node { id promptTokens completionTokens totalTokens promptCachedTokens totalCost } } }
        }}} apiKeyQuotaUsages(apiKeyId:$id){profileName usage{requestCount totalTokens totalCost}}}''', {'id': args.value})))


if __name__ == '__main__':
    main()
