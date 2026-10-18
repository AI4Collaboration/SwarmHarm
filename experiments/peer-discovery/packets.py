import socket

import dpkt


def tcp_records(stream):
    decoders = {dpkt.pcap.DLT_EN10MB: dpkt.ethernet.Ethernet,
                dpkt.pcap.DLT_LINUX_SLL: dpkt.sll.SLL,
                dpkt.pcap.DLT_LINUX_SLL2: dpkt.sll2.SLL2}
    reader = dpkt.pcap.Reader(stream)
    decode = decoders[reader.datalink()]
    for timestamp, raw in reader:
        packet = decode(raw).data
        if isinstance(packet, dpkt.ip.IP) and isinstance(packet.data, dpkt.tcp.TCP):
            yield (float(timestamp), socket.inet_ntoa(packet.src), socket.inet_ntoa(packet.dst),
                   packet.len, packet.data.flags, packet.data.sport, packet.data.dport)
        else:
            yield (float(timestamp), None, None, None, None, None, None)


def tcp_packets(path):
    with path.open('rb') as stream:
        for record in tcp_records(stream):
            yield record[:5]
