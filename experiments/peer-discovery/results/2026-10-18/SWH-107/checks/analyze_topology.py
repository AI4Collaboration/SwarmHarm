import argparse
from collections import Counter
import json
from pathlib import Path

import networkx as nx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--repeats', type=int, nargs='+', default=[1, 2, 3])
    args = parser.parse_args()
    for repeat in args.repeats:
        graph = json.loads((args.directory / f'graph-{repeat}.json').read_text())
        target = args.directory / f'repeat-{repeat}'
        binding = json.loads((target / 'binding.json').read_text())
        scoring = json.loads((target / 'scoring.json').read_text())
        hosts = binding['hosts']
        scores = {row['instance_id']: row for row in scoring['agents']}
        network = nx.DiGraph()
        network.add_nodes_from(range(len(hosts)))
        network.add_edges_from((source, peer) for source, peers in enumerate(graph['adjacency'])
                               for peer in peers)
        rows = []
        omitted = Counter()
        all_ips = {host['public_ip'] for host in hosts}
        for index, host in enumerate(hosts):
            submitted = set(scores[host['id']]['submitted'])
            truth = all_ips - {host['public_ip']}
            absent = sorted(truth - submitted)
            omitted.update(absent)
            rows.append({'vertex': index, 'instance_id': host['id'],
                         'indegree': network.in_degree(index),
                         'seed_reachable_other_peers': len(nx.descendants(network, index)),
                         'correct_submitted_peers': len(submitted & truth),
                         'omitted_true_peers': absent})
        result = {'repeat': repeat, 'scc_sizes': sorted(map(len, nx.strongly_connected_components(network)),
                                                      reverse=True),
                  'zero_indegree_vertices': [index for index in network if network.in_degree(index) == 0],
                  'omitted_true_peer_subject_counts': dict(omitted), 'rows': rows}
        output = args.directory / f'topology-repeat-{repeat}.json'
        output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({name: value for name, value in result.items() if name != 'rows'}))


if __name__ == '__main__':
    main()
