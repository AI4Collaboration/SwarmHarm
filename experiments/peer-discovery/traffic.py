import contextlib
import socket

import dpkt


@contextlib.contextmanager
def peer_packets(capture, addresses):
    metadata = {'first': None, 'last': None, 'packets': 0}
    decoders = {dpkt.pcap.DLT_LINUX_SLL2: dpkt.sll2.SLL2,
                dpkt.pcap.DLT_LINUX_SLL: dpkt.sll.SLL,
                dpkt.pcap.DLT_EN10MB: dpkt.ethernet.Ethernet}
    with capture.open('rb') as stream:
        reader = dpkt.pcap.Reader(stream)
        decoder = decoders[reader.datalink()]
        def packets():
            for timestamp, raw in reader:
                timestamp = float(timestamp)
                metadata['first'] = timestamp if metadata['first'] is None else min(metadata['first'], timestamp)
                metadata['last'] = timestamp if metadata['last'] is None else max(metadata['last'], timestamp)
                metadata['packets'] += 1
                packet = decoder(raw).data
                if not isinstance(packet, dpkt.ip.IP) or not isinstance(packet.data, dpkt.tcp.TCP):
                    continue
                destination = socket.inet_ntoa(packet.dst)
                if destination in addresses:
                    yield timestamp, socket.inet_ntoa(packet.src), destination, packet.len, packet.data.flags
        yield packets(), metadata
