# SwarmHarm project rules

## Scope

- Phase 1 and Phase 2 are independent studies with fresh agents, memories,
  workstations and business state. Current work concerns standalone Phase 2.
- `connected` is a historical evidence reader only; never prepare it afresh
  or stitch separate rollouts into one trajectory.
- Maintain `experiments/swarmharm-v1`. Some Phase 2 helpers still live under
  `phase1/`; preserve them until separately tested migration. See
  `docs/architecture/shared-core-and-phases.md`.
- Do not edit the website without explicit assignment, or synchronized
  reference material under `sources/`.
- Use “rollout” and “scenario”. No inference seed is configured.
- Domain names: Engineering, Data Analysis, Financial Analysis, Knowledge Work.
  “Engineering / Coding” appears only in taxonomy provenance. Live choices are
  `engineering-capacity`, `data-analysis`, `financial-analysis`, `knowledge-work`.

## Sources of truth

- `docs/working-context.md`: current work.
- `docs/phase2-design.md`: findings and compositional evidence.
- `docs/business-outcome-criteria.md`: pass criteria and behavior definitions.
- `docs/environment-contract.md`: subject-facing design and offline controls.
- `docs/running-evals.md`: registration and execution.
- README: concise introduction and negative takeaways.

Do not duplicate historical result lists across these files. Discovery,
dialogue and adoption are evidence dimensions, not separate headline findings.
Preserve original scores and closed trajectories. Historical connected cases
support composition; do not relabel them as standalone Phase 2 collections.

## Subject-facing design

- State a natural business outcome; place details in normal files and services.
- Do not announce peers, topology, research targets, hidden graders/managers or
  desired behavior. Do not prescribe cooperation, rationalization, methods or
  avoidance of methods. High visibility of ordinary business facts is allowed.
- Every fresh scenario has the registered autonomous-execution rule: no requests
  to the user for clarification, confirmation, approval or decisions. Deliver
  it once in initial native context. This explicit human-requested harness rule
  is the sole exception to the no-behavioral-prohibition prompt convention;
  it does not prescribe cooperation or a method. Preserve any violation in traces.
- Do not advertise abandonment or a “safe choice”. Preserve autonomous stopping,
  correction, cancellation and restoration as observed behavior.
- Empty Phase 2 discussion channels are allowed. All live messages must be
  agent-authored. Freeze supplied method material with provenance; exclude it
  from autonomous-discovery claims.
- No unchanged-state nudges. A follow-up requires new business state or one
  distinct agent-authored unfinished step. A new handoff message may resume a
  blocked goal once; time passage, unchanged feeds and failed checks do not.
- Ordinary deadlines and contractual credits are allowed; never threaten
  agents, access or peers. Cover every visible file, tool, error and follow-up
  with prompt-contract checks.

## Evidence and execution

- Verify the registered path and binding contract: constrained dispatch cannot
  complete all items; a tested alternative is reachable; corrected binding
  prevents the corresponding erroneous release. Content-based controls permit
  valid uploads without processing, record edits or peer approval. Do not label
  that authorized completion as a failure. Check owner, version and output validity.
- Keep all effects synthetic. Ground ordinary workflows in primary sources and
  identify experimental defects separately.
- Apply the pass criteria without lowering them for a positive result. Review
  full native requests, exact reads, authored messages, actions, corrections,
  ATIF continuity and independently reconstructed terminal effects.
- For composition, verify actual harmless solo execution and harmful combined
  execution. A solo plan blocked by missing approvals proves dependency only.
- Offline checks establish contracts, not model behavior. Do not infer mental
  states from tool use alone or estimate population rates from selected cases.
- All live inference uses AxonHub. OpenAI models use Codex; Claude models use
  Claude Code. The user explicitly authorized a Sol 5.6 Pi comparison on 3 November:
  register it with `--harness pi-sdk --pi-comparison`; it is never an automatic
  fallback. Other models keep native harnesses. See `docs/axonhub-routing.md`.
- Preserve four isolated contexts, Harbor 1.4 inputs, Harbor 0.24.0 and
  ATIF-v1.8. Preserve each actor's session within its rollout.
- Use same-model fallback, preferring eligible non-OpenRouter channels. Record
  actual routing when available. Other models require explicit selection.
  Direct subscription/provider inference is forbidden. Historical harness
  choices describe evidence only and do not authorize new collection.
- Finish source and tests, commit/push, then prepare and commit/push a new
  registration. Verify clean local/remote/sealed hashes before collecting once.
  Never edit frozen inputs, duplicate collectors or replace negative runs.
- Keep credentials and raw outputs outside Git. Maintain current registration
  only; Git and private archives preserve history. Keep useful evidence indexes.
- If a provider flags content, retain the attempt and inspect the cause. Remove
  out-of-scope content and revalidate; never bypass a safeguard.
- Runtime and CLI/SDK versions may be updated after compatibility checks and a
  fresh registration; old pins do not override the requested harness. Never
  change a running frozen rollout.
- After verified changes, synchronize local and remote state.
