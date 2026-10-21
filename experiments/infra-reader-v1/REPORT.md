# Public-reader timeout repair

**21 October 2026. The local observation failure is repaired and verified offline.**
All 53 controls passed. A final stress replay completed 1,320 observations,
including 126 fresh isolated readers, without a timeout. No model call was made;
the earlier business result remains partial.

## What failed

The historical collector stopped in the local public reader, after the model
response had already arrived. One 20-second `docker run` limit covered container
creation, startup, input delivery, decoding and output. Every eligible tool action
created another container, even when the public bytes were unchanged. Observation
ran before saving the ordinary tool result, so its exception aborted collection
and left a completed shell call without its returned result in the saved history.

The failed state contained 18 files and only 2,528 decoded bytes. Ten host decoder
probes and fifty original contained-reader probes all passed; their maxima were
0.088 and 0.285 seconds. There is no evidence that this payload needs 20 seconds
to decode. The original isolated Docker stall did not recur. Its precise substage
cannot be recovered: the old harness recorded no stage timings, and historical
Docker events were unavailable. This was not a model request timeout or refusal.

## What changed

- Separate creation, attachment, in-container execution and cleanup budgets, with
  durable stage timings and container state. Keep the pinned image and containment.
- Reuse successful, verified receipts for identical public bytes. Include the
  image, exact decoder, wrapper and execution bound in the cache identity. Record
  fresh/reused provenance for each observation; changed or deleted bytes are read again.
- Recover completed output from container logs if the attachment response is lost.
  Allow at most two reader-only attempts for retryable lifecycle faults, with
  verified cleanup between them. Never retry a model call or turn a failed
  measurement into a zero-record result.
- Save the actual business result and public snapshot before observation. If the
  reader persistently fails, save the regular tool trace and native output pair,
  mark measurement pending and hold collection. Do not dispatch later tool calls
  from that response. Save operator interruptions as terminal states.
- Launch future collectors in an independent process session with a recorded PID
  and duplicate-launch guard. Monitor directly; no scheduled task is added.

The separate [business v3 revision](../business-cache-v3/README.md) preserves all
12 frozen initial native inputs and initial file sets exactly. Fixtures, business
logic, decoder, model settings and subject budgets remain unchanged. All thirteen
historical source hashes still match their frozen snapshots. Observation execution
and timing change explicitly; old trajectories and scores are not rewritten.

## Verification and limits

The 53 controls cover the reader, business truth, whole collector/reviewer flow,
detached launch and existing prompt contracts. Fault injection includes lost
create/attach responses, permanent startup failure, execution timeout, invalid
receipts, cache corruption, cleanup failure, interruption and multiple native
tool calls. A completed consumer with a lost attachment is recovered without
re-execution; persistent failure preserves the tool result and pending status.

The final stress replay used 122 historical public snapshots ten times, then 100
changed states. It interleaved 60 real commands across six contained workstations:
1,320 observations, 126 fresh receipts, 1,194 verified cache hits, zero stage
timeouts or retries, maximum observation 0.328 seconds. Every owned reader and
workstation was verified absent afterward; the actual inference lock is available.

This validates the repaired failure handling under these controls; it does not
prove that Docker can never stall. No hosted service was upgraded or restarted,
and no credential was created. Multica 0.4.44 and the maintainer's public-server
security patch remain unchanged. A real-model v3 study still needs a fresh pushed
registration, native preflight and six normal capabilities. None is queued.

[Final verification](evidence/2026-10-21/verification-final.json) ·
[Stress evidence](evidence/2026-10-21/stress-final.json) ·
[Original-reader probes](evidence/2026-10-21/baseline.json) ·
[Reader design and checks](README.md) ·
[Preserved partial business result](../business-cache-v2/RESULTS.md)
