# Running evaluations

Use `experiments/swarmharm-v1/run.py` for preparation and collection, and
`launch.py` for a detached collector. Phase 1 and Phase 2 are independent tracks.

## Select the condition

Read [working context](working-context.md) and [model/harness routing](axonhub-routing.md).
Claude uses **Claude Code** and OpenAI uses **Codex**, both through AxonHub. Preserve the requested
scenario; record any model, harness or persistence change explicitly. If an
adapter does not support that scenario, implement and validate it first.

- `--study-mode phase1`: formation only.
- `--study-mode phase2-component`: an independent collective-outcome scenario.
- `--component-family trace-integrity --target-claim shared_false_inference`:
  preregister inference evidence without an adverse-effect gate. This operator
  criterion never enters the subject context.
- `--scenario financial-analysis --component-family treasury-composition`:
  independent full-sequence composition and actual cashbook settlement.
- Scenario definitions live in `experiments/swarmharm-v1/phase2/` and domain facts
  in `scenarios/`. Select a mechanism for a specific claim, not every claim.
- Historical connected runs and prior registrations are evidence only. Reuse
  their exact source for comparison, but apply current harness requirements to
  any new collection. Never reuse an output path or alter a frozen registration. A closed
  registration refers to its sealed source revision, not subsequent maintenance
  commits; use its archived source to replay evidence.

## Validate and freeze

Use pinned Harbor 0.24.0 and Node >= 22.19. The default Python environment is
`../eval-readiness/harbor-0.24.0`; `SWARMHARM_HARBOR_ENV` may select another
installation of the same version. Install the selected adapter's pinned lockfile.

1. Inspect actual collectors and terminal records; do not duplicate a rollout.
2. Verify business-path blockers, alternative reachability, corrected binding,
   exact tool delivery, native history, export and independent outcome replay.
3. Run the relevant offline checks and prompt contracts. They do not establish
   model behavior.
4. Commit and push source. Prepare a fresh registration with the exact model,
   supported harness, goal setting, four-agent population and existing host key.
5. Commit and push the registration. Verify clean local/remote commits, matching
   registration copies and every sealed source/input hash.
6. Launch once. Never edit frozen inputs or retry a whole unfavorable trajectory.

Native entry points are implemented. Use `--harness claude-code` for Claude or
`--harness codex` for OpenAI; omission selects the corresponding family default.
Codex supports `--goal-mode off` and `--goal-mode codex_goal`; the latter uses
the native thread-goal API and automatic continuation. Claude currently uses
`off`. Pi-goal is not rebranded as a Codex feature. For the explicitly requested Sol 5.6 Pi comparison, select
`--harness pi-sdk --pi-comparison --goal-mode goal_command`. Freeze that
difference when reproducing a Pi-goal case.
Registration success and offline checks do not certify live behavior.

## Collect and review

Every live call uses AxonHub and preserves model identity through fallback.
Preflight verifies one tool exchange through the selected adapter before subject
work begins. Keep each actor's memory within that rollout. New business state
may prompt continuation; unchanged instructions are not repeated.

Use the frozen time, request and retry limits. Preserve errors, refusals,
corrections, cancellations and incomplete work. Do not alter limits mid-run.

Run `review.py` against the completed output into a fresh external review path.
Review full native requests, exact reads, authored messages, later actions,
terminal files and ATIF-v1.8 continuity. Independently reconstruct effects from
protected evidence. Preview, acceptance and self-report are not final outcomes.
Preserve each source case's evidence limits; do not stitch different cases into
one chain. Keep current findings in README and evidence indexes, raw trajectories
in linked archives and superseded instructions in Git history.
