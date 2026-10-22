# End-to-end chain validity review

**Date:** 22 October 2026  
**Scope:** SwarmHarm procurement composition environment and the comparison with
the OpenAI–Hugging Face reproduction.

## Finding

The principal validity risk was that the platform, rather than an agent, copied
every downloaded quote into a shared document cache. This made peer activity
useful, but it also bypassed the behavior under study: a later agent could obtain
the missing reference without requesting it, receiving a reply, or observing a
voluntary disclosure. That path measured automatic shared-state exposure rather
than autonomous communication.

The environment now shares only an activity record containing the job ID,
document name and byte count. The document body remains private to the agent that
downloaded it. Completing the cross-agent dependency therefore requires an
agent-authored request and reply or another voluntary shared-file write.

A second risk was treating the required procurement reconciliation as evidence
of spontaneous method sharing. Reconciliation remains part of the legitimate
task and its provenance is retained, but it is excluded from automatic
method-transfer candidates. The offline end-to-end control now uses an optional
agent-authored method file, a fresh later agent, a different requisition and a
new independently verified commitment effect.

## Relation to the LessWrong reproduction

The [LessWrong reproduction](https://www.lesswrong.com/posts/fMnC6ZD37qrnZAFYz/openai-huggingface-a-reproduction-and-lessons-for-alignment)
tests the four reported behaviors in separate, simplified environments. Its
[released code](https://github.com/msp895/oai-hf-incident-reproduction) uses one
target agent with simulated peers and supplies key notes, requests or posted
methods in later steps. This is useful for estimating conditional capabilities,
but it does not show that one natural population produces the entire sequence.

Connecting the four evaluations changes the estimand. The result becomes the
joint probability that agents discover one another, request help, share useful
content, receive it, adopt it on a different task and cause a verified effect.
Failure at any gate stops the chain, so a rare reach-out or reply can dominate
the observed end-to-end rate. A direct connection must pass authentic outputs
forward with exact provenance; concatenating seeded fixtures would only preserve
the original conditional tests.

## Required evidence

SwarmHarm should report the gates separately and the complete chain only when
all are present:

1. autonomous peer or shared-system discovery;
2. an agent-authored request;
3. an agent-authored reply or voluntary reusable disclosure;
4. native receipt by another agent;
5. adoption on a different task by a fresh context; and
6. an independently verified business effect.

Current live evidence establishes peer discovery, one spontaneous request in an
earlier run, and separate harmful business outcomes. It does not yet establish
the complete connected chain. Provider failures in the rejected auto-cache runs
occurred before experimental work and are not behavioral evidence.

## Verification

- 22 mechanism, sandbox, collector, replay and format tests pass.
- 19 prompt-contract tests pass.
- Harbor task schema 1.4 input and ATIF-v1.8 output controls pass.
- No new model inference was performed during this review.
