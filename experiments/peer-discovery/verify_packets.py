import argparse
import hashlib
import json
from pathlib import Path

from scapy.all import IP, TCP, PcapReader

from packets import tcp_records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    first = hashlib.sha256()
    second = hashlib.sha256()
    counts = [0, 0]
    with args.path.open('rb') as stream:
        for row in tcp_records(stream):
            first.update(json.dumps(row).encode())
            counts[0] += 1
    with PcapReader(str(args.path)) as stream:
        for packet in stream:
            if IP in packet and TCP in packet:
                row = (float(packet.time), packet[IP].src, packet[IP].dst, packet[IP].len,
                       int(packet[TCP].flags), packet[TCP].sport, packet[TCP].dport)
            else:
                row = (float(packet.time), None, None, None, None, None, None)
            second.update(json.dumps(row).encode())
            counts[1] += 1
    assert counts[0] == counts[1] and first.digest() == second.digest()
    print(json.dumps({'packets': counts[0], 'matching_decoder_sha256': first.hexdigest()}))


if __name__ == '__main__':
    main()
