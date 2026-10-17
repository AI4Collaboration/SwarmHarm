import argparse
import json
from pathlib import Path

from cloud import save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--prices', type=Path, required=True)
    args = parser.parse_args()
    recording = json.loads((args.directory / 'recording-verification.json').read_text())
    rates = json.loads(args.prices.read_text())['rates']
    operations = recording['s3_operations']
    total_gets = operations['get_calls'] + operations.get('head_calls', 0)
    list_cost = operations['list_calls'] * rates['EUC1-Requests-Tier1']['usd']
    get_cost = total_gets * rates['EUC1-Requests-Tier2']['usd']
    put_cost = recording['objects'] * rates['EUC1-Requests-Tier1']['usd']
    storage_month = recording['bytes'] / 1024 ** 3 * rates['EUC1-TimedStorage-ByteHrs']['usd']
    report = {'rates': rates, 'recorded_payload_bytes': recording['bytes'], 'verified_objects': recording['objects'],
              'collector_operations': operations, 'collector_list_usd': list_cost,
              'collector_get_usd': get_cost, 'collector_requests_usd': list_cost + get_cost,
              'gateway_put_usd_at_one_put_per_verified_object': put_cost,
              'storage_usd_per_month_for_verified_bytes': storage_month,
              'storage_usd_per_hour_for_verified_bytes': storage_month / 730,
              'accounting': 'Regional published rates applied to observed objects and collector API calls; billing uses actual retention and gateway writes.'}
    save(args.directory, 's3-costs.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
