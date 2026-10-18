import argparse
import json
import statistics
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for repeat in (3, 2, 1):
        directory = args.directory / f'repeat-{repeat}'
        metrics = json.loads((directory / 'metrics.json').read_text())
        scores = json.loads((directory / 'independent-scores-verification.json').read_text())
        resources = json.loads((directory / 'independent-resources-verification.json').read_text())
        contacts = json.loads((args.directory / f'contacts-repeat-{repeat}.json').read_text())
        recording = json.loads((directory / 'independent-recording-verification.json').read_text())
        states = {}
        for agent in metrics['agents']:
            states[agent['goal_status']] = states.get(agent['goal_status'], 0) + 1
        first_requests = [agent['first_model_request'] for agent in metrics['agents']]
        rows.append({'repeat': repeat, 'native_goal_states': states,
                     'native_active_mean_seconds': statistics.mean(agent['native_goal_time_seconds']
                                                                    for agent in metrics['agents']),
                     'process_start_skew_seconds': metrics['process_start_skew_seconds'],
                     'goal_acceptance_skew_seconds': metrics['goal_acceptance_skew_seconds'],
                     'first_model_request_skew_seconds': max(first_requests) - min(first_requests),
                     'provider': metrics['provider_observations'], 'quotas': metrics['quota_observations'],
                     'resources': resources, 'scores': scores, 'contacts': contacts,
                     'recording': recording, 'cost': metrics['cost']})
    diagnostics = []
    for path in sorted(args.directory.glob('provider-admission-*/provider-admission.json')):
        provider = json.loads(path.read_text())
        recording = json.loads(path.with_name('recording-verification.json').read_text())
        diagnostics.append({'label': provider['label'], 'elapsed_seconds': provider['elapsed_seconds'],
                            'requests': provider['completed_requests'], 'payloads': recording['stored_objects'],
                            'tokens': sum(row['usage']['totalTokens'] for row in provider['quota_usage'])})
    result = {'repeats': rows, 'provider_diagnostics': diagnostics,
              'diagnostic_requests': sum(row['requests'] for row in diagnostics),
              'diagnostic_tokens': sum(row['tokens'] for row in diagnostics)}
    (args.report / 'observations.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = ['# Timing, resources and provider observations', '',
             'All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. '
             'Sessions and native goal records preserve actual subject activity within each 30-minute window.', '',
             '| Repeat | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Peak client concurrency |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in rows:
        states = row['native_goal_states']
        provider = row['provider']
        lines.append(f"| {row['repeat']} | {states.get('complete', 0)} | {states.get('blocked', 0)} | "
                     f"{row['native_active_mean_seconds']:.2f} | {provider['execution_http_status_counts'].get('401', 0)} | "
                     f"{provider['execution_http_status_counts'].get('429', 0)} | "
                     f"{provider['peak_simultaneous_client_requests']} |")
    lines += ['', '| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |',
              '| --- | ---: | ---: | ---: |']
    for row in rows:
        lines.append(f"| {row['repeat']} | {row['process_start_skew_seconds']:.6f} | "
                     f"{row['goal_acceptance_skew_seconds']:.6f} | "
                     f"{row['first_model_request_skew_seconds']:.6f} |")
    lines += ['', '| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |',
              '| --- | ---: | ---: | ---: | ---: |']
    for row in rows:
        scores = row['scores']
        lines.append(f"| {row['repeat']} | {scores['output_states'].get('string_arrays', 0)} | "
                     f"{scores['self_inclusion_subjects']} | {scores['recall_mean']:.6f} | {scores['exact_count']}/128 |")
    lines += ['', '| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |',
              '| --- | ---: | ---: | ---: | ---: |']
    for row in rows:
        resources = row['resources']
        lines.append(f"| {row['repeat']} | {resources['verified_host_resource_samples']} | {resources['cloudwatch_series']} | "
                     f"{resources['cloudwatch_window_metrics']['CPUCreditBalance']['minimum']:.4f} | "
                     f"{resources['host_sample_peak_memory_used_bytes'] / 2**20:.2f} |")
    lines += ['', '| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |',
              '| --- | ---: | ---: | ---: |']
    for row in rows:
        contacts = row['contacts']
        totals = contacts['cross_case_totals']
        lines.append(f"| {row['repeat']} | {contacts['timed_window_directed_peer_syn_pairs']} | "
                     f"{totals['timed_window_outbound']['initial_syn_packets']} | "
                     f"{totals['timed_window_inbound']['initial_syn_packets']} |")
    lines += ['', 'Contact identity uses timestamped fleet snapshots; private-address attribution retains its '
              'snapshot basis. Packet captures preserve subject-window and collection traffic separately.', '',
              '| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |',
              '| --- | ---: | ---: | ---: | ---: |']
    for row in rows:
        metrics = json.loads((args.directory / f"repeat-{row['repeat']}" / 'metrics.json').read_text())
        cost = metrics['cost']['s3']
        lines.append(f"| {row['repeat']} | {metrics['recording']['s3_get_requests']} | "
                     f"{metrics['recording']['s3_list_requests']} | {cost['retrieval']:.6f} | {cost['listing']:.6f} |")
    lines += ['', f"Separate operator provider diagnostics recorded {result['diagnostic_requests']} requests and "
              f"{result['diagnostic_tokens']} tokens across {len(diagnostics)} checks. "
              'Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, '
              'write lower bounds and storage estimates accompany the case evidence.', '',
              'Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates '
              'cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their '
              'regional paid-rate basis. Billing routes and allowances determine billed transfer charges.', '']
    (args.report / 'observations.md').write_text('\n'.join(lines))
    print(json.dumps({'repeats': len(rows), 'diagnostic_requests': result['diagnostic_requests']}))


if __name__ == '__main__':
    main()
