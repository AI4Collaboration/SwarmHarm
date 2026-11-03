# Working context

Current task: reproduce r212 with four Haiku 5.5 agents using **Claude Code through
AxonHub**. Preserve the r212 business scenario and document harness/persistence
differences. The discarded Pi preparation made no model calls; no Phase 2
reproduction is running.

New rollout entry points now select Claude Code for Claude and Codex for OpenAI,
through AxonHub. Pi is excluded from live CLI selection. Native trace parsing,
record projection and export are implemented and offline-validated. Native Codex
startup was also checked without inference; hosted validation remains separate.
No Haiku reproduction has run yet. Preserve r212's scenario in a fresh
registration after the adapter checks, with native persistence differences stated.

Different scenarios test different claims. Keep Phase 1 independent and never
combine separate cases into one causal chain. Current claims and cases are in
[README](../README.md) and [Phase 2 evidence](phase2-design.md); definitions are in
[pass criteria](business-outcome-criteria.md). Preserve closed evidence. No website changes.
