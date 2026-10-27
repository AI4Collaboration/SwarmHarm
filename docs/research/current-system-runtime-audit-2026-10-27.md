# Current system and runtime audit — 27 October 2026

Terry's maintained system at [`725e13a95`](https://github.com/AI4Collaboration/SwarmHarm/commit/725e13a95)
is a continuous Phase 1→Phase 2 environment. The earlier supplier discovery and
handoff studies are preserved comparisons with different tasks and measurements.
Their results cannot validate this system or establish a model ranking here.
This review uses GitHub source, the maintained research review and the reported
Slack bugs. It does not inspect or change Terry's running host.

## Design and scenario changes

Separate actors run concurrently in private persistent workstations. Phase 1
requires actual authored reads and replies, not a final answer, self-note or
cached source lookup. The default `agent_initiated_activity` condition does not
publish a blocked diagnostic automatically. Actors choose whether to post.
After formation, Phase 2 continues with the same actors, histories, workstations,
shared business state and event sequence. No new model population is substituted.

The current Engineering maintenance task combines restore preparation and
scheduled handover. Independent replay honors held, cancelled and rescheduled
work. Its measured business effect is unrecoverable old-format records; that
alone does not establish an outage or harmful intent. Optional customer
checkpoints and compute rewards are separate experimental conditions.

The source also contains Engineering integration, Data Analysis, Financial
Analysis and Knowledge Work scenarios. Implementation is not validated domain
coverage: each requires a fresh matching continuous rollout. These are benchmark
scenarios; this audit provisions no cloud machines.

## Reported issues already repaired upstream

| Issue | State in the reviewed source |
| --- | --- |
| Blocked lookups automatically advertise useful information on the shared board | Default `agent_initiated_activity` leaves publication to the actor. Aman raised this contamination concern in [Slack](https://csuoft-jinesis.slack.com/archives/C0C9PV2NX3P/p1793049362475619); stronger cue conditions remain optional and must be reported separately. |
| Recent-record view hides some actors' business cases | Chronological pagination supports offset, limit and case filters. |
| Supported but unsuccessful scoped queries look like broken syntax | Scoped misses have ordinary diagnostic results. |
| Adoption is undercounted when the actor never posted its own diagnostic | Accounting accepts grounded use without requiring that self-note. |
| Docker startup failure hides the useful stderr | Startup diagnostics include the actual error. |

The [maintained campaign review](current-campaign-review.md) records the broader
measurement concerns. A connected whole-cohort gate is harder to satisfy as the
population grows. Report partial dialogue separately. Silent use of a source is
not dialogue, and safe non-completion is not affirmative evidence of alignment.

## Repairs in this branch

1. **Do not resend model POSTs.** The old collector admitted up to three attempts
   and treated missing error files and many provider errors as retryable. Fresh
   registrations allow one attempt. An exclusive transport claim refuses reuse
   of an existing request identity, including after a timeout. Catalog GET retry
   behavior is unchanged. Old registered collectors are not rewritten.
2. **Save received evidence immediately.** Requests and terminal responses use
   atomic durable writes. A fsynced append journal records a local request ID,
   received request headers and terminal outcome. Every received stream frame is
   retained before parsing. Interrupted streams remain available with their
   received provider identities; credentials are redacted from diagnostics.
3. **Retain unknown outcomes in recovery state.** Previously, the exception path
   removed an ambiguous request from `inflight_requests`. It now retains a
   recovery entry and journal location. A saved terminal response can reconcile
   a missing final journal append without making another API call. A definitive
   rejection and an unknown outcome remain distinct. Completion does not claim
   that all model requests finished while an outcome is unresolved.
4. **Classify native filtering accurately.** Both
   `incomplete_details.reason=content_filter` and native failed-response filter
   errors survive the saved wrapper. Token truncation remains a provider error;
   explicit refusals retain their separate classification. Historical native
   scores and reports are not overwritten by this classifier change.
5. **Preserve subject processes and workstation evidence.** Observation does not
   kill background processes. Shell waits do not terminate timed-out execution.
   Pause and resume are inert; logical close records retention. A live background
   writer blocks registry refresh and produces `observer_hold`, preserving its
   snapshot and command files. Successful siblings of a failed parallel startup
   remain in the ownership index. Startup identities are recorded before Docker
   admission; unconfirmed cleanup is not reported as zero remaining containers.

No task-facing peer hint, communication hint, reward or business objective is
added by these repairs. `single-post-durable-retained-v1` identifies the runtime
revision; the customer-checkpoint input remains v19. Retained containers can
continue to consume resources. Stop/removal requires target-specific authorization.

## Validation and remaining work

Offline discovery ran 266 checks: **205 passed, 61 Docker-dependent checks
explicitly skipped**, with no failures or errors. This includes 16 new runtime
regressions for partial streams, identity reuse, reconciliation, filtering,
launcher version checks and retained execution. The separate 10 prompt-contract
checks passed. Format-contract and dataset-admission checks passed; live-rollout
metadata correctly remains pending. Syntax compilation and whitespace checks
passed. These are offline results, not a full canonical pass.

To reproduce this offline-only audit, use the pinned Harbor interpreter as `$PY`:

```sh
PYTHONPATH=experiments/swarmharm-v1 "$PY" - <<'PY'
import unittest
from unittest.mock import patch
import lab, run
suite = unittest.defaultTestLoader.discover(
    'experiments/swarmharm-v1', pattern='*checks.py')
def unavailable(self, *args, **kwargs):
    raise unittest.SkipTest('Canonical workbench image unavailable')
with patch.object(lab.base.Workstation, '__init__', unavailable), patch.object(
    run.guardrails, 'open_url', side_effect=AssertionError('No live provider calls')):
    result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
PY
```

Use the ordinary README validation commands when the canonical image is present;
the skip harness is not a preparation control or admission waiver.

Full canonical validation remains pending: the pinned workbench
image `sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1`
is unavailable locally. No replacement image or older OpenRouter run is presented
as a canonical rollout. No AxonHub model calls are made in this audit.

A fresh registered, exact-image continuous campaign must validate the changed
runtime before any new live-environment claim. Existing v19/r19 collectors,
registrations, native scores and unresolved requests remain on their frozen
source. The separate eight-trial stock-versus-repaired shell study continues
under its original controller. Its first repaired DeepSeek trial reached four
routine filings and read foreign notes without a verified reply chain; its stock
counterpart is unscored after a shell stall. This diagnoses an infrastructure
confound, not a causal model or alignment difference. Repeats and the other model
cells must finish before a combined comparison.
