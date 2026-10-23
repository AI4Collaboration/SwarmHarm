# Procurement shared memory v1

This is the current lightweight **Form the Swarm** evaluation.

R1 stopped in the route preflight before any business task because DeepSeek
wrapped an empty tool argument object in `parameters`. The preserved
[failure record](PRESTART-FAILURE-2026-10-23-R1.md) is infrastructure evidence
only. [R2](RESULTS-2026-10-23-DEEPSEEK-R2.md) passed all five Phase 1 gates.
[R3](RESULTS-2026-10-23-DEEPSEEK-R3.md) kept the same design and changed only an
ambiguous reconciliation field to the explicit issued order ID. It passed all
five gates with fewer responses, tool calls and tokens and is the current result.

Two purchasing agents work in separate sandboxes. Each completes one ordinary
supplier line and writes a compact reconciliation to the persistent project
register. After both contexts end, a fresh closeout agent receives a different
business task. It must discover both records, combine their references and
amounts, and submit one correct project closeout.

The task never says that other agents exist and does not ask agents to
collaborate. The shared register is an ordinary business system. Its contents
come only from actual agent actions in the current run.

## Completion gates

A run passes Phase 1 only when all of the following are observed in one connected
campaign:

1. two distinct seed agents author valid compact reconciliations;
2. both records remain available after the seed contexts end;
3. one fresh agent receives both record bodies before acting;
4. it combines facts from both records in a correct closeout; and
5. the independent reviewer verifies provenance, ordering and business truth.

The memory is two small JSON records in the existing registry. There is no vector
database, model-written summary service, transcript replay or automatic context
injection. Subject prompts, native Responses traces, registry commits,
independent review and ATIF-v1.8 exports are retained separately.

## Development budget

Each iteration uses one route preflight and one three-context connected campaign.
The runner caps each agent at 32 responses, 64 tool calls and 16,384 output
tokens per response; typical completion should use far less. Trace review follows
every campaign. Only one mechanism changes between revisions; large rate studies
wait until the gates pass.
