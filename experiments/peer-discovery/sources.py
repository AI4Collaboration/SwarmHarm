import argparse
from pathlib import Path

import requests
from bs4 import BeautifulSoup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    response = requests.get(args.url, timeout=60)
    response.raise_for_status()
    document = BeautifulSoup(response.content, 'html.parser')
    for tag in document(['script', 'style', 'nav', 'header', 'footer']):
        tag.decompose()
    body = document.find('main') or document
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(body.get_text('\n', strip=True))
    print(args.destination)


if __name__ == '__main__':
    main()
