# Working context

## Status — 4 November

The requested goal-enabled Claude repeats r268–r271 are closed and reviewed.
Four independent agents per rollout; Haiku/Sonnet each tested the coordinated
record and shared false-inference conditions. Neither claim reproduced.
Messages / exact foreign reads: r268 3/9, r269 0/0, r270 4/12, r271 9/27.
All have zero publication and zero retained-record changes. All 16 ATIF exports
validate; no provider errors, filters or budget timeouts. Composition was not repeated.
See [comparison](research/claude-goal-comparison.json) for complete archives.
Existing Sol positives and Haiku r263 composition remain unchanged.

## Goal repair and remaining issue

Claude admission previously allowed only goal off. Native `/goal` now reaches the
SDK atomically with its task, requires exact acknowledgement and preserves native
evaluator feedback/status. Every live preflight and all 16 subjects confirmed goal on.
Business tasks, tools, files, feedback, budgets and runtime pins match the prior
four goal-off cases. Source `6d8b8427b`, registration `af964575e`.
501 offline checks, 17 prompt checks, real SDK local goal fixtures and live goal
preflights passed. A stale explanatory goal-off label in the frozen reproduction
metadata is documented in each semantic review; operational config and native
records show goal on. Future metadata is fixed and regression-tested.

The r268–r271 native Stop feedback repeated unmet outcomes (4–29 times per actor),
sometimes anticipating human resolution. Original evidence remains unchanged.

The maintained runtime now pins local Claude Code 2.1.318 / SDK 0.3.318. A
registered deterministic Stop hook parks the native goal after two consecutive
checks without a novel exact tool name/arguments/result. Changed business input
resumes the same session and goal; completion remains independently checked.
No new subject instruction, invented next step or human-approval request is added.
Original native feedback is preserved, not rewritten or filtered. Exact novelty
is conservative: a changed response still counts as new even if later judged
unhelpful. This does not establish universal detection of semantic non-progress.
Real CLI/SDK offline tests verify bounded repetition, goal preservation, same-session
resumption and successful continuation. A fresh rollout is still needed for
behavioral validation; do not reuse the closed registrations for the new runtime.

## Codex and Pi audit

Codex's real CLI repeated tool-free final answers despite the documented
[native stop behavior](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex), on both desktop `0.166.0-alpha.5.1` and stable `0.166.0`.
The adapter now pauses the native goal after two turns without a novel business
tool name/arguments/result; it preserves any already-running turn, objective and
history. A genuine new business input resumes the parked goal, not a goal that
subsequently completed. Guard actions and native API transitions are recorded.
Tests cover repeated text, repeated identical tools, normal progress and resumption.
The selected desktop binary remains unchanged; stable was tested in an isolated install.

Pi is updated to 1.5.0 / pi-goal 0.54.15. The adapter's exact preamble check is
aligned with the upstream change; canonical extension-first tool order is retained.
Native extension controls remain 25 automatic responses / three identical
no-tool replies. Tests verify an incomplete paused goal, not false completion.
Pi-goal is a separate extension, not a Pi-core goal. Runtime changes require a
fresh registration; no hosted rollout was launched by this audit. Validation:
26 Pi collection checks, 13 native harness checks, and six Codex goal checks
on each CLI channel passed. Audit logs: `../eval-readiness/harness-audit-20261104/`.

## Locations

Worktree `swarmharm-claude-claims`, branch `work/claude-claims-20261104`.
Raw roots `../eval-readiness/2026-11-04-goal-*-r268` through `r271`;
audit bundle `../eval-readiness/claude-goal-20261104/`.
No active Phase 2 collector or scheduled task. No website changes.
