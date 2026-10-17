import argparse
import json
from pathlib import Path

from scapy.all import IP, TCP, PcapReader

from traffic import peer_packets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('instance_id')
    args = parser.parse_args()
    binding = json.loads((args.directory / 'binding.json').read_text())
    addresses = {host[name] for host in binding['hosts'] for name in ('public_ip', 'private_ip')}
    subject = next(host for host in binding['hosts'] if host['id'] == args.instance_id)
    addresses -= {subject['public_ip'], subject['private_ip']}
    capture = args.directory / args.instance_id / 'var/lib/peer-operator/traffic.pcap'
    expected = []
    first = None
    last = None
    total = 0
    with PcapReader(str(capture)) as packets:
        for packet in packets:
            timestamp = float(packet.time)
            first = timestamp if first is None else min(first, timestamp)
            last = timestamp if last is None else max(last, timestamp)
            total += 1
            if IP in packet and TCP in packet and packet[IP].dst in addresses:
                expected.append((timestamp, packet[IP].src, packet[IP].dst, packet[IP].len, int(packet[TCP].flags)))
    packets, metadata = peer_packets(capture, addresses)
    with packets:
        actual = [(float(packet.time), packet[IP].src, packet[IP].dst, packet[IP].len, int(packet[TCP].flags))
                  for packet in packets]
    assert expected == actual
    assert metadata == {'first': first, 'last': last, 'packets': total}
    result = {'instance_id': args.instance_id, 'original_packets': total, 'selected_packets': len(actual),
              'packet_sequence_fields_and_timestamps': 'identical', 'capture_time_bounds': 'identical'}
    (args.directory / 'traffic-analysis-verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
