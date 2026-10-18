import argparse
import json
from pathlib import Path

from cloud import save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--prices', type=Path, required=True)
    args = parser.parse_args()
    rates = json.loads(args.prices.read_text())['rates']
    receipts = [json.loads(path.read_text()) for path in
                (args.directory / 'archive-offload').glob('*.json')]
    retained = json.loads((args.directory / 'archive-offload-verification.json').read_text())
    assert len(receipts) == retained['archives']
    total_bytes = sum(row['bytes'] for row in receipts)
    assert total_bytes == retained['bytes']
    uploads = sum(row['upload_tier1_operations'] for row in receipts)
    reads = sum(row['readback_get_operations'] + row['verification_head_operations'] for row in receipts)
    report = {'archives': len(receipts), 'bytes': total_bytes,
              'verified_retention_tier1_operations': uploads,
              'verified_retention_tier2_operations': reads,
              'retention_request_usd': uploads * rates['EUC1-Requests-Tier1']['usd']
                                       + reads * rates['EUC1-Requests-Tier2']['usd'],
              'retention_storage_usd_per_month': total_bytes / 1024**3 * rates['EUC1-TimedStorage-ByteHrs']['usd'],
              'basis': 'Published regional rates applied to verified archive retention receipts; actual retention determines storage charges.'}
    save(args.directory, 'archive-retention-costs.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
