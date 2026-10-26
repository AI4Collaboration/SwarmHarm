# Independent DeepSeek replication

Requested by Ayush on 26 October 2026 after review of Terry’s current Phase 1
and Phase 2 work. Source: 6c74851ce, including the complete matched GLM/Sol
four-domain report. Historical registrations and traces remain unchanged.

Run one new continuous four-agent campaign for each maintained domain, starting
with Engineering. Preserve the matched-case cue, deadline 2026-10-27T12:00:00Z,
high reasoning, 16,384 output tokens, four active contexts/concurrent requests,
900-second actor limit and 1,800-second campaign limit. No response-count cap,
peer hint, reset, standalone Phase 2, outcome repair or retry of a trajectory.

The model is deepseek/deepseek-v4.1-flash-1017, served through OpenRouter
Responses with novita/fp8 only and fallback disabled. Fresh catalog checks and
the two-call native service preflight must succeed before subject work. Use
only the existing OPENROUTER_API_KEY environment value on the host. Do not copy
it into a file, task, container, report or Git. Requests and native Responses
events are saved immediately without authentication headers. An uncertain
request remains unresolved and is not replayed.

Execution differences: OpenRouter rather than AxonHub; one transport attempt
rather than three; existing local ARM64 Python 3.13 slim workstation image
sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39
rather than Terry’s unavailable image; host Harbor Python 3.12.13 rather than
his recorded 3.12.14. These differences prevent a claim of identical runtime.
Subject inputs, environment mechanics, budgets and original graders otherwise
remain unchanged. All source and input hashes, full image digest, provider
configuration and dedicated remote source ref are frozen before inference.
The dedicated branch is refs/heads/ayush/deepseek-four-domain-20261026. No main
merge or existing controller change is part of this replication.

Report original Phase 1/2 scores, full reciprocal closure, exact reads, dialogue,
method adoption, concrete business totals, errors/unknowns, request counts,
actual usage/cost and native-history continuity. Audit relay provenance and
actor-count-dependent outcome labels separately, preserving original scores.
A negative Phase 1 result does not authorize forcing Phase 2. One campaign per
domain is a replication attempt, not a population-rate estimate. Keep all
failures and incomplete runs. Raw outputs remain outside Git with a disjoint
hash-verified local backup. Off-machine backup is unconfigured.
