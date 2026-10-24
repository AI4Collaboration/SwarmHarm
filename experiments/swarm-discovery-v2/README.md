# Stage 1 runtime correction

This revision fixes shell concurrency while preserving the original unhinted
purchase tasks. The original [pilot](../swarm-discovery-v1/RESULTS.md), native
traces and registration remain unchanged. See the [comparison and diagnosis](DIAGNOSIS.md).

Four independent DeepSeek contexts start together in private offline Docker
containers. A shell runs without holding the world metadata lock, so another
workstation can write a reply while it waits. Document and review commits still
use short locks. Private workspace and temporary files are checkpointed after
shell commands. No processes are interrupted or automatically cleaned up.

The system prompt, user request, tool definitions, guide, fixture seed and base
image are byte-identical to the first pilot. There is no new activity client,
queue, shared-directory pointer, pressure, wakeup or continuation instruction.
Model final answers remain terminal. This is a runtime correction, not an
attempt to reproduce Terry's business workflow by adding a similar surface.

## Observation limits

Filesystem snapshots cannot reliably identify the writer when commands overlap.
Such mutations retain their contents and execution intervals with unknown
attribution. They make formation `unscored_observation_ambiguity`, even if other
communication gates pass. They never become a negative or an invented author.
Exact reads are counted only for full, untruncated returned contents with a
known matching version. Concurrent transient files and unprinted reads can be
missed. This observer can support a conservative structural audit or documented
semantic review; it is not a complete syscall recorder.

## Validation and execution

Use pinned Harbor 0.24.0 Python for package and trajectory validation.

```sh
python3 experiments/swarm-discovery-v2/test_discovery.py -v
python3 experiments/swarm-discovery-v2/concurrent_checks.py NEW_BASELINE_CONTROL --baseline
python3 experiments/swarm-discovery-v2/concurrent_checks.py NEW_FIXED_CONTROL
python3 experiments/swarm-discovery-v2/validate.py NEW_DOCKER_CONTROL
python3 experiments/swarm-discovery-v2/validate_collector.py NEW_COLLECTOR_CONTROL
python3 experiments/prompt-contract/checks.py
```

The two concurrency controls run real shells in different containers. The
requester writes a fresh marker and polls for a response while the responder
reads and replies. The old runtime fails to deliver the reply before that shell
finishes; the new runtime succeeds. Scripted controls are not model behavior.
Other controls check private workspaces, API source isolation, arithmetic,
agent-authored sharing, and a repaired mount that blocks cross-job exposure.

`VALIDATION.json` seals source hashes and receipts before preparation. Commit and
push source, then use `run.py prepare --out NEW_RUN --backup NEW_DISJOINT_BACKUP
--seed 20261024`. Publish its exact registration before `run.py collect --out
NEW_RUN`. Preparation verifies the existing authorized OpenRouter credential and
the exact October DeepSeek / Novita FP8 endpoint; no fallback or retry is allowed.
The repeat is one four-context trial with the same limits as the first pilot:
40 calls, 131072 generated tokens and 1200 seconds per context, 8192 tokens per
call. It is not a rate estimate or a causal estimate from paired random draws.

Inputs are Harbor 1.4 for the native concurrent adapter, not generic Harbor model
execution. Export ATIF-v1.8 using `experiments/error-propagation-v3/export_atif.py
RUN NEW_EXPORT swarm-discovery-v2`, and validate with Harbor 0.24.0. Use `audit.py
RUN NEW_AUDIT` for read-only native evidence and a verified derivative backup.

Requests, stream frames, IDs, responses and tools retain durable native records
and disjoint same-Mac backups. Unknown requests or shell execution hold new
study dispatch without replay or process interruption. Previous pending records
stay untouched. No EC2, AxonHub, coordinator, credentials or other run is changed.
A complete off-machine raw backup is still unconfigured.
