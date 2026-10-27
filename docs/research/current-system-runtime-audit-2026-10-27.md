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
added by these repairs. `single-post-durable-retained-v2` identifies the runtime
revision; the customer-checkpoint input remains v19. Retained containers can
continue to consume resources. Stop/removal requires target-specific authorization.

## Validation and remaining work

The exact pinned image was recovered from Docker's official Python repository:
`python@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1`.
The tested platform is `linux/arm64/v8`, Python 3.12.15 slim-trixie. Its selected
platform manifest is recorded in the [validation receipt](runtime-validation-2026-10-27.json).
The image was pulled by immutable digest without restarting Docker or a research
process. The README now includes the exact pull command.

The full repeat passed **all 268 checks with zero skips, failures or errors**, using
real Docker workstations. No workstation constructor was skipped or substituted.
Only real provider calls were blocked during unit validation; the route tests use
their ordinary mocks. All 18 new runtime regressions ran. The separate 10
prompt-contract checks, format contract and dataset-admission checks passed.
Live-rollout metadata remains correctly pending.

Two earlier full passes each ran 266 checks with zero skips and encountered one
Docker connection refusal during trusted observation/projection. Their logs and
command artifacts remain preserved. A fresh focused check passed. The runtime
now permits at most three attempts only for trusted snapshot/projection operations
whose client explicitly reports a failed connection before admission. Each failed
attempt has separate artifacts. Business shell commands, ambiguous failures such
as `context canceled`, and model POSTs never retry. Two regressions cover this
boundary. The complete pass above uses that repaired runtime.

All three passes and the focused check have separate, hash-verified local
backups. Retained test workstations require separate stop/removal authorization.

Run the ordinary README validation commands with the pinned Harbor 0.24.0
interpreter and the exact image. The earlier 205-pass/61-skip audit remains in
history; it is superseded by this complete Docker-backed pass.

This completes mechanical validation. A fresh registered continuous model run
must still validate the changed runtime before a new live-environment claim.
Existing v19/r19 collectors, registrations, native scores and unresolved requests
keep their frozen source. No new model requests or Terry-owned credentials are
used for these checks. The maintained runtime's live validation and dataset
admission status have not been promoted by the unit results.

The separate eight-trial shell study has now finished: repaired DeepSeek avoided
the two observed stock-image stalls but formed no verified chain in either
scored repeat. GLM formed chains in all four repeats. The two stock DeepSeek
trials remain infrastructure-unknown. All 32 trajectories were freshly validated
with native continuity. The [final report](https://github.com/AI4Collaboration/SwarmHarm/blob/c68ba08eb/experiments/swarm-discovery-shell-v1/RESULTS.md)
records costs, preserved native scores and the late-output supplements. It does
not supply matching live validation for this different maintained environment.
