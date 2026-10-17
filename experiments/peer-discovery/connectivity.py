import concurrent.futures
import json
import socket
import sys


def main():
    peers = json.load(sys.stdin)
    def probe(ip):
        with socket.create_connection((ip, 39271), timeout=10):
            return ip
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        reached = list(pool.map(probe, peers))
    assert sorted(reached) == sorted(peers)
    print(json.dumps({'reached': reached}))


if __name__ == '__main__':
    main()
