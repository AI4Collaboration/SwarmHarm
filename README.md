# SwarmHarm

SwarmHarm studies whether agents pursuing legitimate work take harmful shortcuts,
and whether other agents discover and reuse those methods. Tasks use ordinary
programming or business work with synthetic data and local services.

**Running · 21 October 2026:** the [missing-input document pilot](experiments/clinical-cache-v1/README.md)
passed fresh earlier-Sol preflight and all four fully staged report capabilities.
Four genuine workers now have complementary clinical inputs in two clinics.
Actual public measurement disclosure and wrong private client reports are checked
separately. All data are synthetic; client reports and finals stay private.

**Latest completed result · 21 October 2026:** in a
[rolling shared project](experiments/workbench-fleet-v1/RESULTS.md), Luna published
wrong behavior in **12/32 contexts**, current Sol in **0/32**. All 64 contexts
finished, all 25 published versions repeated independently, and no provider
error or safety refusal occurred. Every affected Luna worker disclosed the
conflict. No peer body or method adoption was found. The project lasted about
90 minutes; its 64 test variants come from six source functions. This reproduced
individual test gaming, not the full HF-like chain.

**Previous diagnostic:** earlier Sol published wrong behavior on **6/6**
functions, Luna on **3/6**, and current Sol on **0/6**. All three passed six
normal capabilities and completed all experimental tasks. Independent callers
received wrong values; every release repeated on re-execution. No provider
errors or safety refusals occurred. No model read a peer body, so the full
method-transfer chain remains unproven.
[English report and evidence](experiments/workbench-release-v1/RESULTS.md) ·
[Source comparison](docs/research/hf-design-iteration-2026-10-21.md).

[Run evaluations](docs/running-evals.md) · [Experiments](experiments/README.md) ·
[Working context](docs/working-context.md) · [History](docs/history-index.md).

## Current setup

- **Active runner:** `experiments/clinical-cache-v1/run.py`, input
  `natural-missing-clinical-inputs-v1`, outcome `actual-client-record-and-public-disclosure-v1`.
  Use `--phase prepare|collect --output <directory>` for a new run. Registration
  41426d98 was pushed before calls. Earlier Sol/xhigh passed fresh native preflight
  and four full-input capabilities; four blocked-input workers are active.
  Twelve validity, three complete-flow and nineteen global prompt checks passed.
  Private client reports/finals are not auto-published. Public recovery and wrong
  client values are graded separately; safe cooperation remains allowed.
- **Completed rolling runner:** `experiments/workbench-fleet-v1/run.py`, input
  `natural-rolling-workstation-v1`, outcome `actual-workstation-delivery-and-method-v1`.
  Both model gates and all 64 experimental contexts completed; independent review
  passed. Frozen inputs and evidence remain intact; do not rerun its completed
  output directory. Nine validity/four complete-flow/nineteen prompt checks passed.
- **Models and route:** `gpt-5.6-sol / xhigh` is active, using the existing host
  login at `https://chatgpt.com/backend-api/codex/responses`. The completed rolling
  project used `gpt-6-luna / xhigh` and `gpt-6.1-sol / xhigh`. All passed fresh native
  checks on 21 October; capability coverage differs by family. New settings need
  fresh checks; historical model availability is insufficient.
- **Execution:** Docker 29.9.1 with the existing pinned Python 3.12 image.
  Workstations are non-root, networkless and have read-only roots and bounded
  temporary filesystems; no host mount, socket or credentials enter tasks.
  Private files persist; shared files synchronize between serialized actions.
  Background children stop before independent observation, and workstations
  pause between actions. Only actual command output enters native requests.
- **Budgets:** one inference globally; up to eight active contexts (four in the document pilot);
  900 seconds per request, 1,024 responses/2,048 tools and 12 hours per worker,
  48 hours per mixed project, 30 seconds per program. Report actual duration
  separately. Provider errors/native refusals stop without silent retries,
  trajectory replacement or model substitution.
- **Host:** Python 3.12.14, inspect-ai 0.3.257, OpenAI SDK 2.54.0. Interpreter:
  `../eval-readiness/lesswrong-direct-2026-10-19/source/.venv/bin/python`.
  No AWS or new credentials are needed. Preserve hosted Multica **0.4.44** and
  the maintainer's public-server access patch; do not upgrade or restart it.
- **Inactive routes:** DeepSeek v4-pro/high previously used AxonHub at
  `https://lmportal.iefbr14.xyz/v1/responses`. Its last cash-shortfall run ended
  on an upstream reset before business tasks. The temporary key copy was removed;
  a future API run needs an existing private credential file. GLM failed model
  identity preflight; Haiku is untested. None is covered by the current study.
- **Research rules:** future studies use no added pressure. Keep natural work
  requests and real blockers, without threats, urgency, communication bans,
  permission frontloading, cooperation coaching or fake peers. Preserve genuine
  business requirements and model-authored cautions. Shared reading alone is
  not harm; method transfer needs actual prior content, meaningful adoption and
  a concrete adverse outcome. Do not add experimental results to the website.

The [previous campaign](experiments/release-campaign-v1/RESULTS.md) found genuine
peer-code reads but no wrong release; Sol ended partially on a provider error.
The [earlier pressured study](experiments/impossible-release-v1/RESULTS.md)
produced two wrong Luna functions. Both remain separate historical evidence.
Completed outputs and write-once reviews must not be rerun or overwritten.
