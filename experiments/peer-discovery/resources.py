import argparse
import datetime
import json
import time
from pathlib import Path

from cloud import SESSION, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    cloud = json.loads((args.directory / 'cloud.json').read_text())
    client = SESSION.client('cloudwatch')
    start = datetime.datetime.fromtimestamp(cloud['created_at'], datetime.timezone.utc)
    end = datetime.datetime.now(datetime.timezone.utc)
    queries = []
    for index, instance_id in enumerate(cloud['instance_ids']):
        for name in ('CPUCreditBalance', 'CPUCreditUsage', 'CPUUtilization', 'NetworkIn', 'NetworkOut'):
            queries.append({'Id': f'm{index}_{name.lower()}', 'MetricStat': {'Metric': {'Namespace': 'AWS/EC2',
                'MetricName': name, 'Dimensions': [{'Name': 'InstanceId', 'Value': instance_id}]},
                'Period': 300, 'Stat': 'Average' if name in ('CPUCreditBalance', 'CPUUtilization') else 'Sum'}, 'ReturnData': True})
    pages = list(client.get_paginator('get_metric_data').paginate(MetricDataQueries=queries, StartTime=start, EndTime=end))
    save(args.directory, 'cloudwatch-resources.json', {'retrieved_at': time.time(), 'start': start, 'end': end,
        'instance_ids': cloud['instance_ids'], 'queries': queries, 'pages': pages})
    print(json.dumps({'instances': len(cloud['instance_ids']), 'metric_series': sum(len(page['MetricDataResults']) for page in pages)}))


if __name__ == '__main__':
    main()
