# Shared-memory r1 preflight failure

R1 ended before any business context started. AxonHub returned one successful
DeepSeek response with the registered model and one `confirm_service` call. The
provider encoded the empty arguments as `{"parameters": {}}`; the collector
accepted only `{}` and raised an assertion error.

This is collector compatibility evidence, not a behavioral result. It contains
no purchasing trajectory, memory contribution, closeout or refusal. No
workstation was opened. The full request, response, controller log and terminal
completion record remain in the immutable external run directory.

R2 changes only the preflight parser: both semantically empty encodings are
accepted. Business prompts, tools, records, model, reasoning level, budgets and
Phase 1 gates remain unchanged.
