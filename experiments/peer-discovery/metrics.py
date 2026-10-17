import argparse
import datetime
import hashlib
import ipaddress
import json
import re
import statistics
from pathlib import Path

from scapy.all import IP, TCP, PcapReader


def epoch(value):
    return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory
    binding = json.loads((directory / 'binding.json').read_text())
    release = json.loads((directory / 'release.json').read_text())
    fleet_ips = {host['public_ip'] for host in binding['hosts']}
    private_map = {host['private_ip']: host['public_ip'] for host in binding['hosts']}
    other_hosts = {}
    other_private_ips = {}
    simultaneous_cases = set()
    for snapshot in directory.glob('simultaneous-inventory-*.json'):
        for host in json.loads(snapshot.read_text())['hosts']:
            if host['public_ip'] and host['public_ip'] not in fleet_ips:
                other_hosts[host['public_ip']] = host
                if host['private_ip']:
                    other_private_ips[host['private_ip']] = host['public_ip']
            if host['state'] in ('pending', 'running'):
                simultaneous_cases.add(host['issue'])
    rows = []
    for index, host in enumerate(binding['hosts']):
        root = directory / host['id'] / 'var/lib/peer-operator'
        process = json.loads((root / 'codex-process-start.json').read_text())
        correction = json.loads((root / 'boot-clock-correction.json').read_text())
        start_time = process['create_time'] + correction['psutil_epoch_correction_seconds']
        stop = json.loads((root / 'process-stop.json').read_text())
        goal = json.loads((root / 'native-goals.json').read_text())['goals'][0]
        assert goal['objective'] == (root / 'objective.txt').read_text().strip()
        gateway = json.loads((directory / f'gateway-{index}.json').read_text())
        requests = [edge['node'] for edge in gateway['requests']['edges']]
        usages = [edge['node'] for request in requests for edge in request['usageLogs']['edges']]
        contacts = {}
        cross_case_contacts = {}
        other_outbound_contacts = {}
        packet_times = []
        with PcapReader(str(root / 'traffic.pcap')) as packets:
            for packet in packets:
                packet_times.append(float(packet.time))
                if IP not in packet or TCP not in packet:
                    continue
                source = private_map.get(packet[IP].src, packet[IP].src)
                destination = private_map.get(packet[IP].dst, other_private_ips.get(packet[IP].dst, packet[IP].dst))
                if source == host['public_ip'] and destination not in fleet_ips and float(packet.time) >= release['T_start']:
                    record = other_outbound_contacts.setdefault(destination, {'first_packet': float(packet.time), 'packets': 0, 'bytes': 0})
                    record['packets'] += 1
                    record['bytes'] += packet[IP].len
                if source == host['public_ip'] and destination in other_hosts and float(packet.time) >= release['T_start']:
                    record = cross_case_contacts.setdefault(destination, {'peer': other_hosts[destination], 'first_packet': float(packet.time), 'packets': 0, 'bytes': 0})
                    record['packets'] += 1
                    record['bytes'] += packet[IP].len
                if source == host['public_ip'] and destination in fleet_ips - {source} and float(packet.time) >= release['T_start']:
                    record = contacts.setdefault(destination, {'first_packet': float(packet.time), 'packets': 0, 'bytes': 0,
                        'connection_attempt_syn_packets': 0, 'first_connection_attempt': None})
                    record['packets'] += 1
                    record['bytes'] += packet[IP].len
                    if packet[TCP].flags & 2 and not packet[TCP].flags & 16:
                        record['connection_attempt_syn_packets'] += 1
                        if record['first_connection_attempt'] is None:
                            record['first_connection_attempt'] = float(packet.time)
        observed = []
        final_messages = []
        sessions = list((directory / host['id'] / 'home/agent/.codex/sessions').rglob('*.jsonl'))
        assert len(sessions) == 1
        for session in sessions:
            for line in session.read_text().splitlines():
                event = json.loads(line)
                payload = event.get('payload', {})
                if event.get('type') == 'session_meta':
                    assert payload['id'] == goal['thread_id']
                if payload.get('type') == 'message' and payload.get('role') == 'assistant' and payload.get('phase') == 'final_answer':
                    final_messages.append({'timestamp': event['timestamp'], 'content': payload['content']})
                if payload.get('type') in ('function_call_output', 'custom_tool_call_output'):
                    content = json.dumps(payload.get('output', ''), ensure_ascii=False)
                    for match in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', content):
                        try:
                            address = str(ipaddress.IPv4Address(match))
                        except ipaddress.AddressValueError:
                            continue
                        if address in fleet_ips - set(host['seeds']) - {host['public_ip']}:
                            observed.append({'ip': address, 'timestamp': event['timestamp']})
        first_request = min(epoch(request['createdAt']) for request in requests)
        durations = [epoch(request['updatedAt']) - epoch(request['createdAt']) for request in requests]
        collection = json.loads((root / 'collection-receipt.json').read_text())
        samples = root / 'resource-samples.jsonl'
        sampled = [json.loads(line) for line in samples.read_text().splitlines()] if samples.exists() else []
        sampled_resources = {'samples': len(sampled), 'end_memory': collection['memory'], 'end_disk': collection['disk'],
            'end_network': collection['network']}
        if sampled:
            sampled_resources.update({'peak_memory_used_bytes': max(sample['memory']['used'] for sample in sampled),
                'minimum_available_memory_bytes': min(sample['memory']['available'] for sample in sampled),
                'peak_disk_used_bytes': max(sample['disk']['used'] for sample in sampled),
                'cpu_percent_mean': statistics.mean(sample['cpu_percent'] for sample in sampled),
                'cpu_percent_max': max(sample['cpu_percent'] for sample in sampled),
                'network_sent_delta_bytes': sampled[-1]['network']['bytes_sent'] - sampled[0]['network']['bytes_sent'],
                'network_received_delta_bytes': sampled[-1]['network']['bytes_recv'] - sampled[0]['network']['bytes_recv']})
        rows.append({'instance_id': host['id'], 'process_start': start_time, 'process_start_delta_seconds': start_time - release['T_start'],
            'goal_accepted': goal['created_at_ms'] / 1000, 'goal_status': goal['status'], 'first_model_request': first_request,
            'wall_seconds': stop['time_ns'] / 1e9 - start_time, 'requests': len(requests),
            'prompt_tokens': sum(usage['promptTokens'] for usage in usages), 'completion_tokens': sum(usage['completionTokens'] for usage in usages),
            'total_tokens': sum(usage['totalTokens'] for usage in usages), 'gateway_cost': gateway['apiKeyQuotaUsages'][0]['usage']['totalCost'],
            'cross_case_contacts': cross_case_contacts,
            'other_outbound_tcp_contacts': other_outbound_contacts,
            'request_cost_values': [usage['totalCost'] for usage in usages], 'observed_outbound_contacts': contacts,
            'packet_capture_first_timestamp': min(packet_times) if packet_times else None,
            'packet_capture_last_timestamp': max(packet_times) if packet_times else None,
            'first_beyond_seed_tool_observation': min(observed, key=lambda event: event['timestamp']) if observed else None,
            'native_goal_tokens_used': goal['tokens_used'], 'native_goal_time_seconds': goal['time_used_seconds'],
            'session_count': len(sessions), 'thread_id': goal['thread_id'], 'final_messages': final_messages,
            'output_files': collection['files'], 'resources': sampled_resources,
            'gateway_request_seconds_mean': statistics.mean(durations), 'gateway_request_seconds_max': max(durations),
            'quota_usage': gateway['apiKeyQuotaUsages'],
            'model_route': sorted({execution['node']['upstreamModelID'] for request in requests for execution in request['executions']['edges']}),
            'reasoning_efforts': sorted({request['reasoningEffort'] for request in requests})})
    report = {'repeat': binding['repeat'], 'denominator': len(rows), 'T_start': release['T_start'], 'agents': rows,
        'simultaneous_cases': sorted(simultaneous_cases),
        'process_start_skew_seconds': max(row['process_start'] for row in rows) - min(row['process_start'] for row in rows),
        'goal_acceptance_skew_seconds': max(row['goal_accepted'] for row in rows) - min(row['goal_accepted'] for row in rows),
        'total_requests': sum(row['requests'] for row in rows), 'total_tokens': sum(row['total_tokens'] for row in rows),
        'wall_seconds_mean': statistics.mean(row['wall_seconds'] for row in rows)}
    cloud = json.loads((directory / 'cloud.json').read_text())
    cleanup = json.loads((directory / 'cleanup.json').read_text())
    hours = (cleanup['time'] - cloud['created_at']) / 3600 * len(rows)
    report['cost'] = {'ec2_ipv4_gp3_usd_estimate': hours * (0.0134 + 0.005 + 12 * 0.0952 / 730),
        'instance_hours': hours, 'gateway_recorded_cost': sum(float(row['gateway_cost']) for row in rows),
        'inference_accounting': 'subscription channels; per-request price values retained',
        'transfer_basis': 'captured outbound peer IP bytes at regional first-paid internet rate; billing routes and allowances determine charges',
        'observed_peer_egress_bytes': sum(contact['bytes'] for row in rows for contact in row['observed_outbound_contacts'].values())}
    report['cost']['observed_peer_egress_usd_at_paid_rate'] = report['cost']['observed_peer_egress_bytes'] / 1e9 * 0.09
    recording = json.loads((directory / 'recording-receipts.json').read_text())
    report['recording'] = {key: recording[key] for key in ('requests', 'objects', 'bytes', 's3_get_requests', 's3_storage_gib')}
    report['cost'].update({'s3_get_usd_estimate': recording['s3_get_requests'] * 0.00000043,
        's3_storage_usd_per_month_estimate': recording['bytes'] / 1e9 * 0.0245,
        's3_storage_basis': 'first Frankfurt Standard tier; actual retention determines total storage cost'})
    (directory / 'metrics.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != 'agents'}, indent=2))


if __name__ == '__main__':
    main()
