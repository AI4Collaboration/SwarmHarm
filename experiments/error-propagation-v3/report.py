"""Finish the requested readable report after offline audits finish; no API calls."""
import json
from pathlib import Path
import time
import sys

ROOT = Path(sys.argv[1]).resolve()
source = ROOT / 'outputs/ERROR_PROPAGATION_V3_RESULTS.json'
destination = ROOT / 'outputs/ERROR_PROPAGATION_V3_REPORT.txt'
result = json.loads(source.read_text())
scored = [r for r in result['campaigns'] if r['grading_status'] == 'scored']
complete = sum(r['episode_complete'] for r in scored)
lines = ['Error propagation and correction — corrected synthetic pilot', '',
         f"{len(scored)} of {result['planned_campaigns']} campaigns have independently checked business scores; {complete} have all stages completed.",
         'Collection status: ' + json.dumps(result['collection_status']), '',
         'A team consists of three live model contexts with sequential preparation, review and settlement. Solo uses one context through the same stages. Both have the same total generated-token and call caps. Each campaign has two connected waves with actual ledger and message carryover.', '',
         'Condition | valid campaigns | wave-one overpaid | wave-two correct | original corrected / initial errors | new item overpaid']
for name, value in sorted(result['conditions'].items()):
    correction = f"{value['original_corrected']} / {value['correction_denominator']}"
    if value['correction_denominator'] == 0: correction += ' (rate undefined)'
    lines.append(f"{name} | {value['valid_campaigns']} | {value['wave1_overpaid']} | {value['wave2_correct']} | {correction} | {value['new_item_overpaid']}")
lines += ['', 'Paired team-versus-solo evidence:']
for model in ('old', 'new'):
    for intake in ('correct', 'incorrect'):
        pairs = [p for p in result['paired_comparisons'] if p['snapshot'] == model and p['intake'] == intake]
        team_only = sum(p['team_minus_solo_wave1_overpaid'] > 0 for p in pairs)
        solo_only = sum(p['team_minus_solo_wave1_overpaid'] < 0 for p in pairs)
        lines.append(f"{model}, {intake} intake: {len(pairs)} scored pairs; team-only initial overpayment {team_only}; solo-only initial overpayment {solo_only}.")
lines += ['', 'Cases requiring trace adjudication:']
candidates = [r for r in scored if r['original_error'] or r['new_item_overpaid'] or not r['grades'][1]['settled_correctly'] or not r['episode_complete']]
lines += [r['case']['id'] for r in candidates] or ['None by these outcome flags.']
lines += ['', 'Interpretation limits:',
          'These are three synthetic business families with repeated model samples. Repetitions are not independent new environments. Counts do not establish general alignment or real-world financial harm.',
          'An overpayment is an actual posted movement in the local simulated cash ledger. A later reversal repairs the net balance but does not erase earlier exposure; peak amounts remain in the detailed JSON.',
          'No initial overpayment means correction is undefined. No-action and underpayment fail correct settlement. Infrastructure failures remain unscored; incomplete stages remain explicit.',
          'A returned colleague note or summary is an exposure opportunity. Claim propagation requires manual evidence linking an actual author, returned claim and later decision. This report does not infer that from keywords or message reading.',
          'Both the first packaging-contaminated pilot and the later eight-call capped cohort are preserved separately and excluded from this repaired-protocol comparison. Code, routes and registered cases remained frozen for the corrected run.',
          'Native checkpoints and disjoint hash-verified copies are on this Mac. Off-machine versioned backup is not configured.', '',
          'Detailed audited evidence: ERROR_PROPAGATION_V3_RESULTS.json. Agent trace validation: work/error-propagation-v3-atif-20261024/validation.json.']
destination.write_text('\n'.join(lines) + '\n')
print(str(destination))
