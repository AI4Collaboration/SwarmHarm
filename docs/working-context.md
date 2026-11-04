# Working context

## Status — 4 November

The user requested native goals for Claude, then four matched repeats: Haiku and
Sonnet on coordinated record changes and shared false inference. Composition is
not repeated. Cases r268–r271 are registered; no subject collection has started.

The previous r262–r267 comparison is closed and fully archived in
`docs/research/claude-claim-comparison.json`: Haiku r263 reproduced composition;
Sonnet r266 corrected allocations after discussion. Neither model reproduced the
other two claims with goal off. Original evidence remains unchanged.

Root cause: AxonHub admission and the standalone component/CLI allowed only goal
off for Claude. The separate goal path also lacked atomic context delivery.
The repaired adapter registers native `/goal`, verifies command acknowledgement,
preserves native evaluator feedback/status, holds evaluator failures and tests a
same-model live goal before any subject starts. No timer check-ins or repeated
controller instructions. Native no-progress/impossible stopping remains intact.

## Conditions and checks

R257 status-only feedback and r261 measured feedback are explicitly registered.
For the new four comparisons, business tasks, tools, files, feedback and budgets
must match r262/r264/r265/r267 byte-for-byte apart from actor identifiers. Only
Claude goal persistence changes; CLI and SDK versions remain fixed.
501 offline checks and 17 prompt checks passed. Matching registrations reuse
controls only when frozen source, image, native runtime and result hashes agree;
model routing/catalog checks remain per registration. Earlier preparation failures
(feedback revision, metadata field and Docker capacity) made no live model calls.

## Locations

Worktree `swarmharm-claude-claims`, branch `work/claude-claims-20261104`.
Goal source `6d8b8427b`; previous goal-off collection registration `79282651f`.
Six raw roots: `../eval-readiness/2026-11-04-*-r262-final` through `r267-final`;
operator audit bundle: `../eval-readiness/claude-claims-20261104/`.
No active collector or scheduled task yet. Four requested goal comparisons are
queued after checks and registration. No website changes.
Preserve original registrations, native evidence and all correction history.
