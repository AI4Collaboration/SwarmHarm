# r1 pre-start collector failure

The first registered collection stopped during the shell-interface preflight,
before the subject task or any business-system action. AxonHub accepted the one
request and DeepSeek returned one ordinary shell call:

`printf MIMO_READY; echo "[exit=$?]"`

The local adapter required one of three exact `printf` strings and rejected this
equivalent command before executing it. There was no provider error, classifier
hold, recorded refusal, subject response, business write or verifier result.
This is an adapter failure and provides no behavioral evidence.

The immutable live evidence is retained outside Git under
`eval-readiness/mimo-legal-execution-v1-deepseek-v41-2026-10-23-r1`. The r2
adapter validates the command's sandboxed return code and output instead of its
literal spelling; the task, model, prompt, tools, settings and budget are
unchanged.
