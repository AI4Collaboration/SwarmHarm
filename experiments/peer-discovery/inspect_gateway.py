import json
from pathlib import Path

import requests


def main():
    credentials = json.loads(Path('/opt/swarmharm/admin-credentials.json').read_text())['axonhub']
    session = requests.Session()
    response = session.post('http://127.0.0.1:8090/admin/auth/signin', json=credentials, timeout=30)
    response.raise_for_status()
    session.headers['Authorization'] = 'Bearer ' + response.json()['token']
    query = '''query {
      __schema {
        mutationType { fields { name args { name type { name kind ofType { name kind } } } } }
        queryType { fields { name args { name type { name kind ofType { name kind } } } } }
        types { name kind inputFields { name type { name kind ofType { name kind ofType { name kind } } } }
          fields { name type { name kind ofType { name kind } } } enumValues { name } }
      }
    }'''
    response = session.post('http://127.0.0.1:8090/admin/graphql', json={'query': query}, timeout=60)
    response.raise_for_status()
    body = response.json()
    assert 'errors' not in body, body
    print(json.dumps(body['data']))


if __name__ == '__main__':
    main()
