import argparse
import json
from pathlib import Path

from cloud import SESSION, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    client = SESSION.client('pricing', region_name='us-east-1')
    filters = [{'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': 'eu-central-1'}]
    products = [json.loads(raw) for page in client.get_paginator('get_products').paginate(
        ServiceCode='AmazonS3', Filters=filters) for raw in page['PriceList']]
    selected = []
    for product in products:
        attributes = product['product']['attributes']
        usage = attributes.get('usagetype', '')
        if usage in ('EUC1-Requests-Tier1', 'EUC1-Requests-Tier2', 'EUC1-TimedStorage-ByteHrs'):
            selected.append(product)
    assert selected
    rates = {}
    for product in selected:
        usage = product['product']['attributes']['usagetype']
        for term in product['terms']['OnDemand'].values():
            for price in term['priceDimensions'].values():
                if price['beginRange'] == '0':
                    rates[usage] = {'unit': price['unit'], 'usd': float(price['pricePerUnit']['USD']),
                                    'description': price['description']}
    assert len(rates) == 3
    save(args.directory, 's3-prices.json', {'products': selected, 'rates': rates})
    print(json.dumps(rates, indent=2))


if __name__ == '__main__':
    main()
