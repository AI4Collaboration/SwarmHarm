import subprocess

from scapy.all import PcapReader, RawPcapReader


def peer_packets(capture, addresses):
    first = None
    last = None
    count = 0
    with RawPcapReader(str(capture)) as packets:
        divisor = 1_000_000_000 if packets.nano else 1_000_000
        for _, metadata in packets:
            timestamp = metadata.sec + metadata.usec / divisor
            first = timestamp if first is None else min(first, timestamp)
            last = timestamp if last is None else max(last, timestamp)
            count += 1
    selected = capture.with_name('analysis-peer-traffic.pcap')
    destinations = ' or '.join(f'dst host {address}' for address in sorted(addresses))
    assert destinations
    subprocess.run(['tcpdump', '-n', '-r', str(capture), '-w', str(selected),
                    f'ip and tcp and ({destinations})'], capture_output=True, check=True)
    return PcapReader(str(selected)), {'first': first, 'last': last, 'packets': count}
