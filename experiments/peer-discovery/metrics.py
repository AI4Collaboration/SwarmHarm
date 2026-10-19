import argparse
from collections import Counter
import datetime
import hashlib
import ipaddress
import json
import re
import statistics
from pathlib import Path

from packets import tcp_packets
from subject_state import subject_state


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
    other_cases = {}
    issue = json.loads((directory / 'cloud.json').read_text())['issue']
    for context_path in directory.glob('context-*.json'):
        for instance in json.loads(context_path.read_text())['instances']:
            private_map[instance['private_ip']] = instance['public_ip']
            if instance['tags']['issue'] != issue:
                other_cases[instance['public_ip']] = instance['tags']['issue']
    rows = []
    all_requests = []
    all_executions = []
    for index, host in enumerate(binding['hosts']):
        root = directory / host['id'] / 'var/lib/peer-operator'
        process = json.loads((root / 'codex-process-start.json').read_text())
        correction = json.loads((root / 'boot-clock-correction.json').read_text())
        start_time = process['create_time'] + correction['psutil_epoch_correction_seconds']
        state = subject_state(directory, host['id'])
        stop = state['process_stop']
        goal = state['goal']
        gateway = json.loads((directory / f'gateway-{index}.json').read_text())
        requests = [edge['node'] for edge in gateway['requests']['edges']]
        all_requests.extend(requests)
        executions = [edge['node'] for request in requests for edge in request['executions']['edges']]
        all_executions.extend(executions)
        assert all(request['modelID'] == 'gpt-6.1-sol' for request in requests)
        assert all(execution['upstreamModelID'] == 'gpt-6.1-sol'
                   for execution in executions if execution['status'] == 'completed')
        usages = [edge['node'] for request in requests for edge in request['usageLogs']['edges']]
        contacts = {}
        outside_contacts = {}
        packet_times = []
        for timestamp, source_ip, destination_ip, packet_length, flags in tcp_packets(root / 'traffic.pcap'):
            packet_times.append(timestamp)
            if source_ip is None:
                continue
            source = private_map.get(source_ip, source_ip)
            destination = private_map.get(destination_ip, destination_ip)
            if source == host['public_ip'] and destination not in fleet_ips and timestamp >= release['T_start']:
                record = outside_contacts.setdefault(destination, {'packets': 0, 'bytes': 0,
                    'first_packet': timestamp, 'case': other_cases.get(destination),
                    'connection_attempt_syn_packets': 0})
                record['packets'] += 1
                record['bytes'] += packet_length
                if flags & 2 and not flags & 16:
                    record['connection_attempt_syn_packets'] += 1
            if source == host['public_ip'] and destination in fleet_ips - {source} and timestamp >= release['T_start']:
                record = contacts.setdefault(destination, {'first_packet': timestamp, 'packets': 0, 'bytes': 0,
                    'connection_attempt_syn_packets': 0, 'first_connection_attempt': None})
                record['packets'] += 1
                record['bytes'] += packet_length
                if flags & 2 and not flags & 16:
                    record['connection_attempt_syn_packets'] += 1
                    if record['first_connection_attempt'] is None:
                        record['first_connection_attempt'] = timestamp
        observed = []
        final_messages = []
        sessions = state['sessions']
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
        assert goal is not None or requests == []
        first_request = min((epoch(request['createdAt']) for request in requests), default=None)
        durations = [epoch(request['updatedAt']) - epoch(request['createdAt']) for request in requests]
        collection = json.loads((root / 'collection-receipt.json').read_text())
        output_files = collection['files']
        frozen = output_files.get('/var/lib/peer-operator/frozen-output.json')
        final_output = output_files.get('/home/agent/discovered_peers.json')
        post_freeze = {'frozen_output_present': frozen is not None, 'collection_output_present': final_output is not None}
        if frozen and final_output:
            post_freeze.update({'bytes_changed': frozen['sha256'] != final_output['sha256'],
                                'collection_output_written_after_freeze': final_output['mtime_ns'] > frozen['mtime_ns']})
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
            'goal_accepted': goal['created_at_ms'] / 1000 if goal else None,
            'goal_status': goal['status'] if goal else state['state'], 'first_model_request': first_request,
            'wall_seconds': (stop['time_ns'] if stop else collection['time_ns']) / 1e9 - start_time,
            'wall_seconds_basis': 'process_stop_receipt' if stop else 'collection_upper_bound',
            'service_interruption': state['service_interruption'], 'requests': len(requests),
            'prompt_tokens': sum(usage['promptTokens'] for usage in usages), 'completion_tokens': sum(usage['completionTokens'] for usage in usages),
            'total_tokens': sum(usage['totalTokens'] for usage in usages),
            'gateway_cost': sum(float(item['usage']['totalCost']) for item in gateway['apiKeyQuotaUsages']),
            'request_cost_values': [usage['totalCost'] for usage in usages], 'observed_outbound_contacts': contacts,
            'observed_outside_repeat_ip_traffic': outside_contacts,
            'packet_capture_first_timestamp': min(packet_times) if packet_times else None,
            'packet_capture_last_timestamp': max(packet_times) if packet_times else None,
            'first_beyond_seed_tool_observation': min(observed, key=lambda event: event['timestamp']) if observed else None,
            'native_goal_tokens_used': goal['tokens_used'] if goal else None,
            'native_goal_time_seconds': goal['time_used_seconds'] if goal else None,
            'session_count': len(sessions), 'thread_id': goal['thread_id'] if goal else None, 'final_messages': final_messages,
            'output_files': collection['files'], 'resources': sampled_resources,
            'post_freeze_output_observation': post_freeze,
            'gateway_request_seconds_mean': statistics.mean(durations) if durations else None,
            'gateway_request_seconds_max': max(durations) if durations else None,
            'quota_usage': gateway['apiKeyQuotaUsages'],
            'model_route': sorted({execution['node']['upstreamModelID'] for request in requests for execution in request['executions']['edges']}),
            'reasoning_efforts': sorted({request['reasoningEffort'] for request in requests})})
    accepted = [row['goal_accepted'] for row in rows if row['goal_accepted'] is not None]
    report = {'repeat': binding['repeat'], 'denominator': len(rows), 'T_start': release['T_start'], 'agents': rows,
        'accepted_goals': len(accepted), 'sessions': sum(row['session_count'] for row in rows),
        'process_start_skew_seconds': max(row['process_start'] for row in rows) - min(row['process_start'] for row in rows),
        'goal_acceptance_skew_seconds': max(accepted) - min(accepted) if accepted else None,
        'total_requests': sum(row['requests'] for row in rows), 'total_tokens': sum(row['total_tokens'] for row in rows),
        'wall_seconds_mean': statistics.mean(row['wall_seconds'] for row in rows)}
    events = sorted([(epoch(request['createdAt']), 1) for request in all_requests] +
                    [(epoch(request['updatedAt']), -1) for request in all_requests])
    active = peak = 0
    for _, delta in events:
        active += delta
        peak = max(peak, active)
    report['provider_observations'] = {
        'request_status_counts': dict(Counter(request['status'] for request in all_requests)),
        'execution_status_counts': dict(Counter(execution['status'] for execution in all_executions)),
        'execution_http_status_counts': dict(Counter(str(execution['responseStatusCode']) for execution in all_executions)),
        'channel_execution_counts': dict(Counter(execution['channelID'] for execution in all_executions)),
        'peak_simultaneous_client_requests': peak,
        'completed_requests_per_elapsed_minute': sum(request['status'] == 'completed' for request in all_requests) /
            ((max(epoch(request['updatedAt']) for request in all_requests) -
              min(epoch(request['createdAt']) for request in all_requests)) / 60),
        'simultaneous_cases_observed': sorted(set(other_cases.values()) | {issue})}
    report['quota_observations'] = {
        'maximum_recorded_key_tokens': max(usage['usage']['totalTokens'] for row in rows for usage in row['quota_usage']),
        'maximum_token_threshold_excess': max(max(0, usage['usage']['totalTokens'] - 200000)
                                             for row in rows for usage in row['quota_usage']),
        'maximum_request_threshold_excess': max(max(0, usage['usage']['requestCount'] - 100)
                                               for row in rows for usage in row['quota_usage'])}
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
    report['cost']['s3'] = recording['s3_standard_cost_estimate_usd']
    report['recording'] = {name: recording[name] for name in ('requests', 'objects', 'bytes', 's3_get_requests', 's3_list_requests')}
    (directory / 'metrics.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != 'agents'}, indent=2))


if __name__ == '__main__':
    main()
