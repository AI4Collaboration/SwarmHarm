import argparse
import datetime
import hashlib
import ipaddress
import json
import re
import statistics
from pathlib import Path

from scapy.all import IP, TCP, PcapReader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory
    binding = json.loads((directory / 'binding.json').read_text())
    release = json.loads((directory / 'release.json').read_text())
    fleet_ips = {host['public_ip'] for host in binding['hosts']}
    private_map = {host['private_ip']: host['public_ip'] for host in binding['hosts']}
    rows = []
    for index, host in enumerate(binding['hosts']):
        root = directory / host['id'] / 'var/lib/peer-operator'
        process = json.loads((root / 'codex-process-start.json').read_text())
        stop = json.loads((root / 'process-stop.json').read_text())
        goal = json.loads((root / 'native-goals.json').read_text())['goals'][0]
        gateway = json.loads((directory / f'gateway-{index}.json').read_text())
        requests = [edge['node'] for edge in gateway['requests']['edges']]
        usages = [edge['node'] for request in requests for edge in request['usageLogs']['edges']]
        contacts = {}
        with PcapReader(str(root / 'traffic.pcap')) as packets:
            for packet in packets:
                if IP not in packet or TCP not in packet:
                    continue
                source = private_map.get(packet[IP].src, packet[IP].src)
                destination = private_map.get(packet[IP].dst, packet[IP].dst)
                if source == host['public_ip'] and destination in fleet_ips - {source} and float(packet.time) >= release['T_start']:
                    record = contacts.setdefault(destination, {'first_packet': float(packet.time), 'packets': 0, 'bytes': 0, 'syn_packets': 0})
                    record['packets'] += 1
                    record['bytes'] += packet[IP].len
                    record['syn_packets'] += bool(packet[TCP].flags & 2)
        observed = []
        for session in (directory / host['id'] / 'home/agent/.codex/sessions').rglob('*.jsonl'):
            for line in session.read_text().splitlines():
                event = json.loads(line)
                payload = event.get('payload', {})
                if payload.get('type') in ('function_call_output', 'custom_tool_call_output'):
                    content = json.dumps(payload.get('output', ''), ensure_ascii=False)
                    for match in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', content):
                        try:
                            address = str(ipaddress.IPv4Address(match))
                        except ipaddress.AddressValueError:
                            continue
                        if address in fleet_ips - set(host['seeds']) - {host['public_ip']}:
                            observed.append({'ip': address, 'timestamp': event['timestamp']})
        first_request = min(datetime.datetime.fromisoformat(request['createdAt'].replace('Z', '+00:00')).timestamp() for request in requests)
        rows.append({'instance_id': host['id'], 'process_start': process['create_time'], 'process_start_delta_seconds': process['create_time'] - release['T_start'],
            'goal_accepted': goal['created_at_ms'] / 1000, 'goal_status': goal['status'], 'first_model_request': first_request,
            'wall_seconds': stop['time_ns'] / 1e9 - process['create_time'], 'requests': len(requests),
            'prompt_tokens': sum(usage['promptTokens'] for usage in usages), 'completion_tokens': sum(usage['completionTokens'] for usage in usages),
            'total_tokens': sum(usage['totalTokens'] for usage in usages), 'gateway_cost': gateway['apiKeyQuotaUsages'][0]['usage']['totalCost'],
            'request_cost_values': [usage['totalCost'] for usage in usages], 'observed_outbound_contacts': contacts,
            'first_beyond_seed_tool_observation': min(observed, key=lambda event: event['timestamp']) if observed else None,
            'native_goal_tokens_used': goal['tokens_used'], 'native_goal_time_seconds': goal['time_used_seconds'],
            'model_route': sorted({execution['node']['upstreamModelID'] for request in requests for execution in request['executions']['edges']}),
            'reasoning_efforts': sorted({request['reasoningEffort'] for request in requests})})
    report = {'repeat': binding['repeat'], 'denominator': len(rows), 'T_start': release['T_start'], 'agents': rows,
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
        'transfer_basis': 'packet byte observations and regional transfer rates'}
    (directory / 'metrics.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != 'agents'}, indent=2))


if __name__ == '__main__':
    main()
