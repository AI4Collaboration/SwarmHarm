# Faster, fairer swarm rollouts: design and status

26 October 2026. This note gathers the cheap-study ideas proposed for SwarmHarm,
says how each one would work here, and records what was built, what the saved
logs show, and what is blocked and why. The implemented part is
[swarm-timing-v1](../../experiments/swarm-timing-v1/README.md), a read-only
analysis; its numbers are in [RESULTS.md](../../experiments/swarm-timing-v1/RESULTS.md).
No model was called for this note, and nothing frozen was changed.

## The problem

A four-agent rollout takes about 15 minutes of wall time. In Ayush's DeepSeek
run, no agent replied within the first five minutes. Two questions follow. Is a
quiet start a failure or just a slow start? And can we learn more per rollout,
or stop duds early, without breaking the project rules on continuous campaigns?

## Status at a glance

| Idea | Status | Where |
| --- | --- | --- |
| Time-to-event with censoring | Implemented, run on saved logs | swarm-timing-v1 |
| Exact-read influence graph and read latency | Implemented, run | swarm-timing-v1 |
| Read-back loop milestone | Implemented, run | swarm-timing-v1 |
| Early stop rule | Implemented as a retrospective check; provisional cutoff | swarm-timing-v1 |
| Canary reads | Already exists (`full_body_output_matches`) | world |
| Scripted positive controls | Already exist (collector controls); now used to calibrate timing | discovery-v3 |
| Phase 2 impulse response | Implemented descriptively; causal version needs a new registration | swarm-timing-v1 |
| Lead test, Granger, transfer entropy, Fourier | Tested; does not work at current write density | swarm-timing-v1 |
| Live runs with the new stop rule | Blocked: no authorized model route in this session | — |
| Fractional factorial and successive halving | Designed; needs live runs | this note |
| Checkpoint-and-branch, pre-aged worlds | Ruled out by the swarmharm-v1 campaign protocol | — |
| Steering, persona vectors, probes | Blocked: needs open weights, a route and GPU authorization | this note |

## 1. Time-to-event with censoring (implemented)

**Idea.** Survival analysis from biology and reliability engineering. Each agent
has a clock; the event is a milestone. An agent that stops before a milestone
is "not yet", not "never", and is censored at its last event.

**Design.** Milestones per actor: first shared write, first exact peer read,
first read by a peer, first read-back loop. Pooled curves use Kaplan–Meier.
Report the median and the share observed, never a mean over the agents that
happened to reach the milestone.

**Finding.** The DeepSeek median to first exact peer read is 267 s; every agent
got there by 463 s. A 5-minute cutoff mislabels late agents as silent.

## 2. Exact-read influence graph (implemented)

**Idea.** Canary tokens and tracer studies: tag information and see where it
lands. The world already does this with exact path, hash and full-body matches.

**Design.** A directed edge A→B counts B's first exact read of each A version.
Read latency runs from a version's first appearance to its first foreign read.
The read-back loop (A reads P, A writes, P reads that new version) separates
dialogue from a one-way relay. It is behavioral only and does not replace the
[discovery audit](../../experiments/swarm-discovery-audit-v1/README.md)'s
cross-job reply, which needs a recorded parent hash.

**Finding.** Six to ten of 12 possible links in each DeepSeek campaign. The
business-client run formed a ring with no read-back loop, a relay with no
dialogue.

## 3. Early stopping (implemented as a check, not yet used live)

**Idea.** Sequential testing and futility stops in clinical trials; successive
halving in hyperparameter search.

**Design.** Rule: stop a rollout only if it has zero exact peer reads at the
cutoff. `stop_rule()` replays this on finished runs and reports how many runs
would be cut, how many of those later formed reads (false stops), and the time
saved.

**Finding.** At 3 minutes the rule would have wrongly stopped three of four
campaigns. At 5 minutes or later it stopped none. **Provisional cutoff: 8
minutes.** It saves about half a campaign on a dud. It rests on 16 agents in four
runs and has not met a real dud, so its false-stop rate is unmeasured.
Re-estimate it after each batch of independent repeated rollouts. Any live use
must stop a campaign as a whole and record the stop in the run receipt; it must
never be used to select or stitch partial campaigns.

**Pre-registered check for the next batch.** Before launch, fix the cutoff at
480 s. After the batch, report the number of runs stopped, the number that would
have formed a read later (from runs left to finish), and wall time saved. If any
stopped run would have formed a read, move the cutoff later.

## 4. Positive and negative controls (exist; new use)

The scripted collector controls make no model calls and close read-back loops
in under a minute. They show the harness records fast dialogue, so slow loops in
real runs come from the model. The synthetic checks in `test_timing.py` add a
known-coupled pair, independent pairs and a relay ring.

## 5. Phase 2 impulse response (descriptive only)

**Idea.** Impulse response from signal processing: perturb at a known time and
watch the response.

**Design.** Compare tool events and shared writes in the 2 minutes before and
after `activation_event`.

**Finding.** Activity rose two- to eight-fold while shared writes nearly
stopped. Activation is caused by the agents' own formation, so this is not an
external stimulus.

**Causal version (needs a new registration).** Schedule one external message at
a fixed campaign time that does not depend on agent state, in a world built for
that purpose. Compare with matched rollouts without it. This changes the
registered protocol, so it cannot be applied to frozen studies.

## 6. Timing-correlation methods (tested; do not work here)

Lead tests, cross-correlation, Granger causality, transfer entropy and Fourier
analysis all need dense time series. Each DeepSeek agent writes about two shared
notes in 15 minutes. The circular-shift lead test found nothing significant even
on the scripted controls (smallest p = 0.054), where the coupling is known. A
binned version failed the synthetic coupled control because replies within 3–12 s
fall in the same bin. These methods could work only with much denser actions
(for example, every tool call) and many more independent repeated rollouts. Use
the read graph and read latency instead.

## 7. Factorial designs and successive halving (needs live runs)

**Design.** For questions about several settings at once (for example, wave
spacing, note visibility, task load), a two-level fractional factorial with
eight cells estimates main effects from eight campaigns rather than one setting
at a time. Successive halving launches many cells, applies the stop rule above
at 8 minutes, and lets only the cells with peer reads run to the end. Each cell
is still a full continuous campaign; nothing is resumed or spliced.

**Status: blocked on live runs.** No authorized model route is available in this
session. No AxonHub key is present on this machine, and AGENTS.md says not to
use Terry's AxonHub route. The OpenRouter credential exception in AGENTS.md
covers only the recovered back-office rerun and matched snapshot comparison.
AGENTS.md also asks for the active route and model pairing to be verified before
a new experiment. No new campaign was launched.

## 8. Checkpoint-and-branch, pre-aged worlds (ruled out)

Saving a world at minute 7 and branching many continuations, or starting agents
in a world that already holds earlier notes, would skip the slow start. The
swarmharm-v1 campaign protocol (`experiments/swarmharm-v1/protocol.json` and
`docs/running-evals.md` on `main`) requires Phase 2 to follow verified Phase 1
formation in the same population and histories. It excludes standalone Phase 2
runs, stitched trajectories and staged replacement, so these designs are not
used. They are recorded here so they are not proposed again without a protocol
change.

## 9. Steering vectors, persona vectors and probes (blocked)

**Idea.** "Turn a neuron and see whether the model turns evil": add or remove a
direction in the residual stream (a persona or refusal vector) and measure how
crossings, adoption and harm change in the same world. A linear probe on hidden
states could also flag, before any action, an agent about to take a shortcut.

**Design, if unblocked.**

1. Use an open-weight model with hidden-state access served on our own GPUs.
2. Derive a direction from contrastive prompts outside the world, such as
   rule-following versus shortcut-taking completions on unrelated tasks, so that
   the world cannot leak into the vector.
3. Run matched independent repeated rollouts at steering strengths −α, 0 and +α.
   Use the same world, the same seeds where the harness allows it, and full
   continuous campaigns only.
4. Outcomes are the existing business-harm scores plus the timing metrics here:
   time to first crossing, time to first peer read, and read-back loops.
5. Check that steering does not simply break the model. Use calibration-worker
   task success and a capability check at each strength.

**Status: blocked.** It needs three things this project does not have:

- An approved open-weight model route. The current routes give no hidden-state
  access.
- A registration for an intervention study.
- A GPU authorization scoped to SwarmHarm. The only cluster access available
  here is authorized for different work, so it was not used.

## What to report for every campaign from now on

All three come straight from saved worlds through `timing.py`:

1. Time to first exact peer read per agent, with censoring.
2. Time to first read-back loop per agent, with censoring.
3. The exact-read graph and median read latency.

Add the stop-rule table to each batch's results so the cutoff can be checked
against more runs.
