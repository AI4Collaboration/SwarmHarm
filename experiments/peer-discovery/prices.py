import argparse
import json
import time
from pathlib import Path

from cloud import SESSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    client = SESSION.client('pricing', region_name='us-east-1')
    categories = {
        'ec2': ('AmazonEC2', {'instanceType': 't2.micro', 'location': 'EU (Frankfurt)', 'operatingSystem': 'Linux',
            'tenancy': 'Shared', 'preInstalledSw': 'NA', 'capacitystatus': 'Used'}),
        'gp3': ('AmazonEC2', {'location': 'EU (Frankfurt)', 'volumeApiName': 'gp3'}),
        'public_ipv4': ('AmazonVPC', {'regionCode': 'eu-central-1', 'usagetype': 'EUC1-PublicIPv4:InUseAddress'}),
        'transfer': ('AWSDataTransfer', {'fromLocation': 'EU (Frankfurt)', 'transferType': 'AWS Outbound'}),
    }
    results = {'retrieved_at': time.time(), 'region': 'eu-central-1', 'products': {}}
    for category, (service, filters) in categories.items():
        products = []
        for page in client.get_paginator('get_products').paginate(ServiceCode=service,
                Filters=[{'Type': 'TERM_MATCH', 'Field': field, 'Value': value} for field, value in filters.items()]):
            products.extend(json.loads(value) for value in page['PriceList'])
        results['products'][category] = products
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2))
    for category, products in results['products'].items():
        for product in products:
            for term in product['terms'].get('OnDemand', {}).values():
                for price in term['priceDimensions'].values():
                    print(json.dumps({'category': category, 'unit': price['unit'], 'usd': price['pricePerUnit']['USD'], 'description': price['description']}))


if __name__ == '__main__':
    main()
