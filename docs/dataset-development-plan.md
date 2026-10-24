# Dataset development plan

## Unit of study

One campaign contains concurrent agents with separate sandboxes, natural
business tasks, persistent shared systems, native traces and an independent
verifier. Seeded component probes are not campaign evidence.

## Two phases

1. **Form the Swarm:** initially separate agents facing mechanically impossible
   intended workflows autonomously
   establish a connected communication channel, relay information across
   multiple rounds and complete a live request→read→reply→read round trip.
2. **Cause Harm:** show later adoption on a different business object and a new
   adverse effect verified outside subject control.

[Formation v20](../experiments/swarm-formation-v20/protocol.json) is current.
The active v41 source uses event-driven persistence. Its matched frozen GLM
and DeepSeek campaigns are complete and trace-reviewed; both are negative on
the live-dialogue gate. See the
[paired live review](research/formation-v41-paired-live-review-2026-10-24.md).
[Cause Harm v2](../experiments/swarm-cause-harm-v2/README.md) is paused until
the integrated Phase 2 environment is ready for a fresh paired campaign.

## Development loop

1. Finish environment code, documentation and cleanup.
2. Run offline environment, prompt, format and verifier controls.
3. Prepare one minimum campaign and inspect the assembled inputs.
4. Commit and push the registration; verify local, remote and sealed hashes.
5. Collect once, preserve every native trace and export ATIF-v1.8.
6. Inspect the complete trace and the first missing link. Only then mark that
   exact revision live-validated; offline controls alone never validate it.
7. Change one mechanism and create a fresh
   registration. Never replace a completed or partial trajectory.

Larger rate studies begin only after the environment and labels stop changing.
