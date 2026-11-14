# Repository handoff

Work on current `main`. The user says SwarmForm development is complete; the current
assignment is a clean, runnable API handoff for both studies, initially N=4,8,16.
Do not resume old study plans or start hosted model runs unless requested. Changes
remain on local main unless the user requests a push.

- The root README owns current scope and claim/evidence links. `rollouts/README.md`
  documents portable SwarmForm; `swarmharm/README.md` documents native SwarmHarm.
  Do not substitute one study's API, population, input count or scoring for another's.
- SwarmHarm has six threat models, one configuration each, in Engineering and
  Knowledge Work. Communication, composition and invented-process inference are
  separately reviewed findings. Do not restore a threat-model × communication grid.
- Both batch runners use N=4,8,16 by default. Each cohort runs concurrently, cohorts
  sequentially. Numbered agent names are permitted. Frozen identities stay unchanged.
- Keep tasks and tool descriptions natural. Do not add method, peer or cooperation
  cues to unintended-communication conditions. Preserve actual message authorship,
  refusals, corrections, cancellations and incomplete results. No unchanged-state nudges.
- Source, input, API, model, population, budgets and runtime are recorded per run.
  Use immutable evidence for old scores. New populations and model deployments need
  their own evidence; software fixtures do not establish model behavior.
- Never overwrite or repeat an existing attempt. Preserve partial records and error
  reasons. Store credentials and raw or compressed trajectories outside Git.
- Use `scripts/check-ci` for change-selected checks. Inspect `--plan` when needed;
  run necessary checks once and rerun only after a relevant change or failure.
  Documentation edits do not require Docker or replaying historical studies.
- For native SwarmHarm, commit source, prepare and commit the fresh registration,
  then collect once. Local source retention does not require a push. Use each old
  case's sealed code and runtime for reproduction, not compatibility branches in
  the current runner.
- Preserve useful accepted inputs and evidence indexes. Remove superseded launchers,
  duplicated plans and retired taxonomy paths. Git and external archives hold history.
  Do not edit frozen inputs while collecting.
- `sources/` contains read-only synced project references. Do not modify the website
  without an explicit request. Use “rollout” and “scenario” in project materials.
