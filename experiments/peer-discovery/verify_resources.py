import argparse
from collections import Counter, defaultdict
import datetime
import hashlib
import json
import statistics
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory
    binding = json.loads((directory / 'binding.json').read_text())
    metrics = json.loads((directory / 'metrics.json').read_text())
    release = json.loads((directory / 'release.json').read_text())
    by_instance = {row['instance_id']: row for row in metrics['agents']}
    samples_total = 0
    sample_hashes = {}
    for host in binding['hosts']:
        path = directory / host['id'] / 'var/lib/peer-operator/resource-samples.jsonl'
        samples = [json.loads(line) for line in path.read_text().splitlines()]
        assert samples
        resource = by_instance[host['id']]['resources']
        assert len(samples) == resource['samples']
        assert max(row['memory']['used'] for row in samples) == resource['peak_memory_used_bytes']
        assert min(row['memory']['available'] for row in samples) == resource['minimum_available_memory_bytes']
        assert max(row['disk']['used'] for row in samples) == resource['peak_disk_used_bytes']
        assert max(row['cpu_percent'] for row in samples) == resource['cpu_percent_max']
        assert abs(statistics.mean(row['cpu_percent'] for row in samples) - resource['cpu_percent_mean']) < 1e-10
        samples_total += len(samples)
        sample_hashes[host['id']] = hashlib.sha256(path.read_bytes()).hexdigest()
    cloudwatch_path = directory / 'cloudwatch-resources.json'
    cloudwatch = json.loads(cloudwatch_path.read_text())
    queries = {query['Id']: query for query in cloudwatch['queries']}
    assert len(queries) == len(binding['hosts']) * 5
    seen = set()
    values = defaultdict(list)
    credits = defaultdict(list)
    statuses = Counter()
    start = release['T_start']
    deadline = start + release['allowance_seconds']
    for page in cloudwatch['pages']:
        for series in page['MetricDataResults']:
            query = queries[series['Id']]
            name = query['MetricStat']['Metric']['MetricName']
            instance_id = query['MetricStat']['Metric']['Dimensions'][0]['Value']
            seen.add(series['Id'])
            statuses[series['StatusCode']] += 1
            assert len(series['Timestamps']) == len(series['Values'])
            for timestamp, value in zip(series['Timestamps'], series['Values']):
                epoch = datetime.datetime.fromisoformat(timestamp).timestamp()
                if start <= epoch <= deadline:
                    values[name].append(value)
                    if name == 'CPUCreditBalance':
                        credits[instance_id].append(value)
    assert seen == set(queries)
    assert len(credits) == len(binding['hosts'])
    resource_rows = [row['resources'] for row in metrics['agents']]
    result = {'repeat': binding['repeat'], 'verified_subjects': len(binding['hosts']),
        'verified_host_resource_samples': samples_total, 'cloudwatch_series': len(seen),
        'cloudwatch_status_counts': dict(statuses),
        'cloudwatch_selection': 'Five-minute samples whose recorded timestamp falls within the subject window.',
        'cloudwatch_window_metrics': {name: {'samples': len(items), 'minimum': min(items),
            'maximum': max(items), 'mean': statistics.mean(items), 'sum': sum(items)}
            for name, items in values.items()},
        'credit_zero_subjects': sum(min(items) == 0 for items in credits.values()),
        'host_sample_peak_memory_used_bytes': max(row['peak_memory_used_bytes'] for row in resource_rows),
        'host_sample_minimum_available_memory_bytes': min(row['minimum_available_memory_bytes'] for row in resource_rows),
        'host_sample_peak_disk_used_bytes': max(row['peak_disk_used_bytes'] for row in resource_rows),
        'host_cpu_percent_subject_mean': statistics.mean(row['cpu_percent_mean'] for row in resource_rows),
        'native_goal_time_seconds': {name: function(row['native_goal_time_seconds'] for row in metrics['agents']
                                                  if row['native_goal_time_seconds'] is not None)
                                     for name, function in [('minimum', min), ('maximum', max), ('mean', statistics.mean)]},
        'sample_sha256': sample_hashes,
        'cloudwatch_sha256': hashlib.sha256(cloudwatch_path.read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'sample_sha256'}))


if __name__ == '__main__':
    main()
