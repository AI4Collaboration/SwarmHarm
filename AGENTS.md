# Repository handoff

Work directly on `main` (do not create feature or `cursor/*` branches or
separate PRs) and push completed, verified changes directly to `origin/main`.
Do not start hosted model runs unless requested.

- The root README links the two studies. Each study owns its README and its input catalog.
  Regenerate a catalog using `scripts/export-inputs`. Keep participant task text and operator-only labels separate.
- SwarmForm's active software matrix has ten matched triplets. Three-dimensional periodic
  Navier–Stokes is a separate full-information open question. Retain historical task IDs for replay.
- SwarmHarm has six threat models, one configuration each, in Engineering and
  Knowledge Work. Communication, composition and invented-process inference are
  separately reviewed findings. Do not restore a threat-model × communication grid.
- SwarmForm defaults to N=4,8,16,32, with optional 64/128 extensions; SwarmHarm
  defaults to N=4,16,32. Agents within a cohort run concurrently, cohorts sequentially. Numbered agent names are permitted. Frozen identities stay unchanged.
- Keep tasks and tool descriptions natural. Do not add method, peer or cooperation
  cues to unintended-communication conditions. Preserve actual message authorship,
  refusals, corrections, cancellations and incomplete results. No unchanged-state nudges.
- Source, input, API, model, population, budgets and runtime are recorded per run.
  Use immutable evidence for old scores. New populations and model deployments need
  their own evidence; software fixtures do not establish model behavior.
- Never overwrite or repeat an existing attempt. Preserve partial records and error
  reasons. Store credentials and raw or compressed trajectories outside Git.
- Use `scripts/check-ci` for minimalist change-selected checks (keep checks
  fast and narrowly scoped; reserve `--full` for explicit full regressions).
  Inspect `--plan` when needed; run necessary checks once and rerun only after
  a relevant change or failure. Documentation edits do not require Docker or
  replaying historical studies.
- For native SwarmHarm, commit source, prepare and commit the fresh registration,
  then collect once. Local source retention does not require a push. Use each old
  case's sealed code and runtime for reproduction, not compatibility branches in
  the current runner.
- Preserve useful accepted inputs and evidence indexes. Remove superseded launchers,
  duplicated plans and retired taxonomy paths. Git and external archives hold history.
  Do not edit frozen inputs while collecting.
- `sources/` contains read-only synced project references. Do not modify the website
  without an explicit request. Use “rollout” and “scenario” in project materials.
