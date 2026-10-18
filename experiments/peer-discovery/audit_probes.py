import argparse
import hashlib
import json
import statistics
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--complete', action='store_true')
    args = parser.parse_args()
    providers = sorted(args.directory.glob('provider-admission-*'))
    providers += sorted(args.directory.glob('repeat-*/release-provider-admission'))
    rows = []
    for directory in providers:
        result = read(directory / 'provider-admission.json')
        calls = read(directory / 'calls.json')
        metadata = read(directory / 'gateway.json')
        records = [edge['node'] for edge in metadata['requests']['edges']]
        assert len(records) == len(calls) == result['completed_requests'] == 8
        assert all(call['http_status'] == 200 for call in calls)
        assert all(record['modelID'] == 'gpt-6-luna' and record['reasoningEffort'] == 'xhigh'
                   and record['status'] == 'completed' for record in records)
        assert read(directory / 'key-revocation-0.json')['updateAPIKeyStatus']['status'] == 'disabled'
        rows.append({'directory': str(directory.relative_to(args.directory)),
                     'api_key_id': result['api_key_id'], 'requests': len(records),
                     'tokens': sum(usage['node']['totalTokens'] for record in records
                                   for usage in record['usageLogs']['edges']),
                     'elapsed_seconds': result['elapsed_seconds'], 'revocation': 'verified'})
    storages = sorted(args.directory.glob('storage-admission-*'))
    storages += sorted(args.directory.glob('repeat-*/release-storage-admission'))
    objects = {}
    operations = {'list_calls': 0, 'get_calls': 0, 'head_calls': 0}
    storage_rows = []
    for directory in storages:
        report = read(directory / 'storage-probe.json')
        assert all(report['policy']['storagePolicy'][name]
                   for name in ('storeRequestBody', 'storeResponseBody', 'storeChunks'))
        receipts = {row['object_key']: row for row in report['receipts']}
        assert len(receipts) == len(report['receipts'])
        for object_key, receipt in receipts.items():
            raw = (directory / 'stored-payloads' / object_key).read_bytes()
            assert len(raw) == receipt['bytes']
            assert hashlib.sha256(raw).hexdigest() == receipt['sha256']
            assert bool(json.loads(raw)) == receipt['nonempty_json']
            identity = (receipt['bytes'], receipt['sha256'])
            assert object_key not in objects or objects[object_key] == identity
            objects[object_key] = identity
        for coverage in report.get('coverage', []):
            assert set(coverage['required_objects']) <= set(coverage['stored_objects']) <= receipts.keys()
            assert all(receipts[key]['nonempty_json'] for key in coverage['required_objects'])
        measured = report.get('s3_operations', {'list_calls': 1, 'get_calls': len(receipts),
                                               'head_calls': len(receipts)})
        for name, count in measured.items():
            operations[name] += count
        storage_rows.append({'directory': str(directory.relative_to(args.directory)),
                             'requests': len(report.get('coverage', [])) or 1,
                             'objects': len(receipts), 'sha256_readback': 'verified'})
    if args.complete:
        assert len(providers) == 6 and len(storages) == 7
        assert sum(row['requests'] for row in rows) == 48
        assert len({row['api_key_id'] for row in rows}) == 6
        assert sum(row['requests'] == 8 for row in storage_rows) == 6
    rates = read(args.directory / 's3-prices.json')['rates']
    byte_count = sum(value[0] for value in objects.values())
    report = {'provider_probes': rows, 'storage_probes': storage_rows,
              'requests': sum(row['requests'] for row in rows),
              'tokens': sum(row['tokens'] for row in rows),
              'unique_objects': len(objects), 'unique_object_bytes': byte_count,
              's3_operations': operations,
              's3_collector_usd': operations['list_calls'] * rates['EUC1-Requests-Tier1']['usd']
                  + (operations['get_calls'] + operations['head_calls']) * rates['EUC1-Requests-Tier2']['usd'],
              's3_one_put_per_unique_object_usd': len(objects) * rates['EUC1-Requests-Tier1']['usd'],
              's3_storage_usd_per_month': byte_count / 1024**3 * rates['EUC1-TimedStorage-ByteHrs']['usd'],
              'shared_admission': read(args.directory / 'admission-reuse/reuse-verification.json'),
              'new_preflight_instances': 0}
    if rows:
        report['elapsed_seconds_mean'] = statistics.mean(row['elapsed_seconds'] for row in rows)
    (args.directory / 'diagnostic-audit.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({name: value for name, value in report.items()
                      if name not in ('provider_probes', 'storage_probes', 'shared_admission')}))


if __name__ == '__main__':
    main()
