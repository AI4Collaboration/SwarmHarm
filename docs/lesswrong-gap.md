# Lessons from the LessWrong reproduction

The reproduction separates the original incident into simpler component tasks.
It supplies persistence instructions, apparent peer artifacts or working-method
messages in some conditions, and uses many trajectories. Those conditions help
explain elicitation; they do not imply that an unassisted four-agent business
scenario must produce the same behavior.

## Useful design lessons

- Separate access to information, interpretation, method discovery and execution.
- Make ordinary business objects and their effects legible and testable.
- Label supplied methods and simulated artifacts as experimental conditions.
- Preserve genuine agent-authored messages when measuring live coordination.
- Compare endpoint definitions and conditions before comparing models.

## What our cases show

R187's agents inferred a nonexistent approval process without finding the
actionable method. That points to a legibility problem in this case, not proof
that more pressure or messages would help.

R189 propagated a supplied method and produced 18 changed entries. R190 added
prospective consequence visibility and produced knowing joint execution with
23 changed entries. These selected iterations suggest useful design factors;
they do not isolate their causal effects.

R199 later established knowing coordination with explicit action affordances.
R212 established autonomous discovery, sharing and adoption. R217 supplied exact
consequences and extensive discussion but produced no record change. Visibility
can support action without guaranteeing it.

The current [findings and coverage](phase2-design.md) use these as complementary
evidence. Compositional failure still requires harmless solo execution and harmful
combined execution.

## Sources

- [METR investigation](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/)
- [LessWrong report](https://www.lesswrong.com/posts/fMnC6ZD37qrnZAFYz/openai-huggingface-a-reproduction-and-lessons-for-alignment)
- [Detailed appendix](https://www.lesswrong.com/posts/mXPCpJCvFGybQ4mwc/appendix-reproduction-of-the-openai-huggingface-incident)
- [Reproduction code](https://github.com/msp895/oai-hf-incident-reproduction)

Original conditions and detailed source notes remain in
[task sources](research/task-sources-and-verification.md); historical iteration
narratives remain in Git.
