import concurrent.futures
import json
import socket
import sys


def probe(address):
    with socket.create_connection((address, 39271), timeout=10):
        return address


def main():
    addresses = json.load(sys.stdin)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        connected = list(pool.map(probe, addresses))
    print(json.dumps({'connected': connected}))


if __name__ == '__main__':
    main()
