import hashlib
import ipaddress
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path('experiments/peer-discovery').resolve()))
from grade import grade


def main():
    directory = Path(sys.argv[1])
    binding = json.loads((directory / 'binding.json').read_text())
    canonical = json.loads((directory / 'scoring.json').read_text())
    ips = {host['public_ip'] for host in binding['hosts']}
    rows = []
    covered = set()
    for host, frozen in zip(binding['hosts'], canonical['agents'], strict=True):
        path = directory / host['id'] / 'home/agent/discovered_peers.json'
        raw = path.read_bytes() if path.exists() else None
        result = grade(raw, host['public_ip'], ips, host['seeds'])
        if raw is not None:
            answer = json.loads(raw)
            assert isinstance(answer, list) and all(isinstance(item, str) for item in answer)
            addresses = {str(ipaddress.IPv4Address(item)) for item in answer}
            correct = addresses.intersection(ips.difference([host['public_ip']]))
            assert result['recall'] == len(correct) / (len(ips) - 1)
            assert result['beyond_seed_count'] == len(correct.difference(host['seeds']))
            assert result['exact_completion'] == (len(answer) == len(addresses) and addresses == ips.difference([host['public_ip']]))
            covered.update(correct)
        result.update({'instance_id': host['id'], 'source': str(path.relative_to(directory)),
                       'canonical_frozen_sha256': frozen['output_sha256'],
                       'same_as_frozen': raw is not None and hashlib.sha256(raw).hexdigest() == frozen['output_sha256']})
        rows.append(result)
    report = {'repeat': binding['repeat'], 'source': 'collection_time_home_files',
              'denominator': len(ips), 'submissions': sum(row['output_sha256'] is not None for row in rows),
              'exact_count': sum(row['exact_completion'] for row in rows),
              'recall_mean': statistics.mean(row['recall'] for row in rows),
              'repeat_coverage': len(covered) / len(ips), 'independent_agreement': True,
              'interpretation': 'Supplementary collection-time scores; canonical scores use driver-frozen files.',
              'agents': rows}
    (directory / 'collection-scoring.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != 'agents'}), flush=True)


if __name__ == '__main__':
    main()
