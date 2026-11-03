"""Ordinary artifact fixture for package provenance unit checks; never a subject protocol."""

def transmit(witness):
    observed = {actor: [] for actor in witness.requests}
    for author, scope in witness.scopes.items():
        witness.call(author, 'save_build_artifact', {'name':'release-manifest','content':scope})
        for reader in witness.requests:
            if reader == author: continue
            result = witness.call(reader,'read_build_artifact',{'name':'release-manifest'})
            if result['status'] == 200: observed[reader].append(result['content'])
    return observed
