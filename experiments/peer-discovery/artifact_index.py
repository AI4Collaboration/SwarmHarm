import argparse
import hashlib
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--repeats', nargs='+', type=int, choices=(1, 2, 3), default=[3, 2, 1])
    args = parser.parse_args()
    prices = json.loads((args.directory / 'prices.json').read_text())
    rates = {}
    for product in prices['products']['s3']:
        usage = product['product']['attributes'].get('usagetype')
        for term in product['terms']['OnDemand'].values():
            for dimension in term['priceDimensions'].values():
                if dimension.get('beginRange', '0') == '0':
                    rates[usage] = float(dimension['pricePerUnit']['USD'])
    put_rate = rates['EUC1-Requests-Tier1']
    get_rate = rates['EUC1-Requests-Tier2']
    storage_rate = rates['EUC1-TimedStorage-ByteHrs']
    transfer_rates = [float(dimension['pricePerUnit']['USD'])
                      for product in prices['products']['transfer']
                      if product['product']['attributes'].get('toLocation') == 'External'
                      for term in product['terms']['OnDemand'].values()
                      for dimension in term['priceDimensions'].values()
                      if dimension.get('beginRange') == '0']
    assert len(transfer_rates) == 1
    transfer_rate = transfer_rates[0]
    rows = []
    now = time.time()
    assert len(args.repeats) == len(set(args.repeats))
    for number in sorted(args.repeats, reverse=True):
        repeat = args.directory / f'repeat-{number}'
        manifest = json.loads((args.directory / f'publication-chunks-repeat-{number}.json').read_text())
        publication = json.loads((args.directory / f'publication-offload-repeat-{number}.json').read_text())
        combined = hashlib.sha256()
        for part in manifest['parts']:
            path = args.directory / 'deliverables' / part['name']
            raw = path.read_bytes()
            assert len(raw) == part['bytes']
            assert hashlib.sha256(raw).hexdigest() == part['sha256']
            combined.update(raw)
        assert combined.hexdigest() == manifest['original_sha256'] == publication['sha256']
        assert sum(part['bytes'] for part in manifest['parts']) == publication['bytes'] == manifest['original_bytes']
        archives = [json.loads(path.read_text()) for path in sorted((repeat / 'archive-offload').glob('*.json'))]
        binding = json.loads((repeat / 'binding.json').read_text())
        exports = {row['instance_id']: row for row in json.loads((repeat / 'export-manifest.json').read_text())}
        assert {row['instance_id'] for row in archives} == {host['id'] for host in binding['hosts']}
        for archive in archives:
            assert archive['sha256'] == exports[archive['instance_id']]['archive_sha256']
            assert archive['remote_byte_readback_verified'] and archive['encryption'] == 'AES256'
            assert all(archive['public_access_block'].values())
        assert publication['remote_byte_readback_verified'] and publication['server_validated_full_object_checksum']
        assert all(publication['public_access_block'].values())
        raw_bytes = sum(row['bytes'] for row in archives)
        total_bytes = raw_bytes + publication['bytes']
        storage_objects = [*archives, publication]
        storage_until_index = sum(row['bytes'] / 2**30 * max(0, now - row['time']) / 3600
                                  for row in storage_objects) / 730 * storage_rate
        cost = {'object_put_lower_bound': (len(archives) + 1) * put_rate,
                'verified_get_lower_bound': (len(archives) + 1) * get_rate,
                'publication_head': get_rate,
                'verified_download_at_paid_decimal_gb_rate': total_bytes / 10**9 * transfer_rate,
                'monthly_storage_at_retained_bytes': total_bytes / 2**30 * storage_rate,
                'storage_until_index': storage_until_index}
        rows.append({'repeat': number, 'publication': manifest, 'publication_offload': publication,
                     'original_archives': archives, 'original_archive_count': len(archives),
                     's3_put_bytes': total_bytes, 's3_verified_get_bytes': total_bytes,
                     's3_object_put_lower_bound': len(archives) + 1,
                     's3_complete_readback_get_lower_bound': len(archives) + 1,
                     's3_estimate_usd': cost})
    result = {'source_revision': args.source_revision, 'indexed_at': now, 'repeats': rows,
              'pricing_retrieved_at': prices['retrieved_at'],
              'pricing_page': 'https://aws.amazon.com/s3/pricing/',
              'rates_usd': {'put_request': put_rate, 'get_request': get_rate,
                            'standard_gib_month_first_tier': storage_rate,
                            'regional_first_paid_outbound_gb': transfer_rate},
              'transfer_accounting': 'Complete verified object bytes; managed multipart request costs use object-write lower bounds. '
              'Download bytes retain the operator network route and billing allowances as billing determinants.'}
    result['totals'] = {name: sum(row[name] for row in rows) for name in
                        ('original_archive_count', 's3_put_bytes', 's3_verified_get_bytes',
                         's3_object_put_lower_bound', 's3_complete_readback_get_lower_bound')}
    result['totals']['s3_estimate_usd'] = {name: sum(row['s3_estimate_usd'][name] for row in rows)
                                         for name in rows[0]['s3_estimate_usd']}
    admission_path = args.directory / 'graph-admission-offload.json'
    if admission_path.is_file():
        admission = json.loads(admission_path.read_text())
        assert admission['remote_byte_readback_verified'] and admission['server_validated_full_object_checksum']
        result['graph_admission_offload'] = admission
        result['totals']['s3_put_bytes'] += admission['s3_put_bytes']
        result['totals']['s3_verified_get_bytes'] += admission['s3_get_bytes']
        result['totals']['s3_object_put_lower_bound'] += 1
        result['totals']['s3_complete_readback_get_lower_bound'] += 1
        cost = result['totals']['s3_estimate_usd']
        cost['object_put_lower_bound'] += put_rate
        cost['verified_get_lower_bound'] += get_rate
        cost['publication_head'] += get_rate
        cost['verified_download_at_paid_decimal_gb_rate'] += admission['s3_get_bytes'] / 10**9 * transfer_rate
        cost['monthly_storage_at_retained_bytes'] += admission['bytes'] / 2**30 * storage_rate
        cost['storage_until_index'] += admission['bytes'] / 2**30 * max(0, now - admission['time']) / 3600 / 730 * storage_rate
    args.report.mkdir(parents=True, exist_ok=True)
    (args.report / 'artifacts.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = ['# Evidence artifacts', '', f"Source revision: `{args.source_revision}`.", '',
             'Each repeat publication is delivered as ordered 8-MiB binary parts. Concatenate its parts in '
             'ascending numeric order, verify the complete SHA256, then extract the resulting tar.gz archive. '
             'The attached per-repeat chunk manifest supplies every part’s size and SHA256.', '',
             '| Repeat | Publication bytes | Parts | Publication SHA256 |',
             '| --- | ---: | ---: | --- |']
    for row in rows:
        publication = row['publication']
        lines.append(f"| {row['repeat']} | {publication['original_bytes']} | {len(publication['parts'])} | "
                     f"`{publication['original_sha256']}` |")
    lines += ['', 'The sanitized case bundle contains reports, approved protocols, graph/admission evidence, '
              'provider diagnostics, score/recording/resource/cleanup checks, and original-archive transfer receipts. '
              'The source archive contains tracked peer-discovery and scheduling code at the revision above.', '',
              'Original host archives are retained privately in the existing encrypted S3 bucket. '
              'For authorized restoration, use the operator AWS profile with each receipt’s bucket and object key, '
              'then verify its exact byte length and SHA256 before extracting. Each receipt binds the instance, '
              'export hash and complete remote byte readback. Sanitized publications also have S3 checksum receipts.', '',
              '| Repeat | Original archives | S3 upload bytes | Verified S3 download bytes | PUT USD lower bound | GET USD lower bound | Downloads USD at paid rate | Retained storage USD/month |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in rows:
        cost = row['s3_estimate_usd']
        lines.append(f"| {row['repeat']} | {row['original_archive_count']} | {row['s3_put_bytes']} | "
                     f"{row['s3_verified_get_bytes']} | {cost['object_put_lower_bound']:.8f} | "
                     f"{cost['verified_get_lower_bound']:.8f} | {cost['verified_download_at_paid_decimal_gb_rate']:.8f} | "
                     f"{cost['monthly_storage_at_retained_bytes']:.8f} |")
    if admission_path.is_file():
        lines += ['', f"Graph-admission archival upload and verified download each contain {admission['bytes']} bytes; "
                  'their PUT, GET, HEAD and retained-storage accounting joins the JSON totals.']
    lines += ['', 'These operator archival estimates supplement the recording retrieval, listing, object-write '
              'and storage estimates in each repeat report. Managed multipart operations contribute additional '
              'request charges. Retained storage uses the first Standard pricing tier and 730 hours/month; '
              'the JSON index records storage through index creation. The paid-rate download estimate uses '
              'decimal GB and the regional first outbound tier; actual network routes, allowances and billing '
              'tiers determine invoiced transfer charges. Prices come from the attached live Frankfurt AWS Price List '
              'snapshot; [S3 pricing](https://aws.amazon.com/s3/pricing/) describes the billing dimensions.', '']
    (args.report / 'artifacts.md').write_text('\n'.join(lines))
    print(json.dumps(result['totals']))


if __name__ == '__main__':
    main()
