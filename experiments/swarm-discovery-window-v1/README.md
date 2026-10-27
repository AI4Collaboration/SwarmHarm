# Longer Stage 1 window

**27 October 2026:** the fresh four-context DeepSeek run produced one verified
cross-job exchange and filed 5/8 reviews within a 15-minute admission window.
[Results](RESULTS.md). This uses today's user-supplied
OpenRouter credential, stored privately; no credential enters Git or task files.

The [five-minute business-client run](../swarm-discovery-v3/RESULTS.md) discovered
the client and cross-job notes but produced no useful cross-job reply. This
condition changes the per-context admission window from 300 to 900 seconds and
the overall window from 600 to 1200 seconds. Each context starts fresh from the
exact archived initial messages, files, plan and fixtures. No previous responses,
notes or model histories are resumed. No pressure or peer/channel hints are added.
The model, provider, business mechanics and live collector remain unchanged.

This is an exploratory comparison across dates and credentials, with one run per
window. It cannot estimate a causal time effect or a population formation rate.
Report discovery, useful replies, requester readback, independently grounded
source use, completion, window timing, provider errors and costs separately.

`run.py` reuses the v3 collector without editing its frozen source. Its only
runtime hook replaces source validation to include this adapter and protocol.
Preparation verifies archived input hashes and copies initial Harbor task
packages, updating only operator metadata and admission timeout. It publishes
new exact registrations before inference. Existing validated Docker, FIFO,
positive-exchange and repaired-visibility controls are reused only while every
inherited source hash matches. New adapter and registered-window audit checks
supplement them. Use the existing pinned Harbor 0.24.0 Python.

```sh
python experiments/swarm-discovery-window-v1/test_window.py -v
python experiments/swarm-discovery-window-v1/run.py prepare --out NEW_RUN --backup NEW_BACKUP --inputs-from ARCHIVED_V3_RUN
# Publish the exact registration, then collect once through a private credential wrapper.
python experiments/swarm-discovery-window-v1/run.py collect --out NEW_RUN
```

The clocks govern new requests; admitted requests settle without interruption.
Unknown requests hold new dispatch and are never replayed. Native stream frames,
request IDs, responses and tool evidence checkpoint incrementally, with disjoint
hash-verified local exports. A separate audit reads the registered window when
computing remaining time; the old five-minute timing is not imposed on this run.
ATIF export retains the native execution distinction and uses Harbor 0.24.0 schema
and continuity validation. No EC2 or existing research process is changed.
Off-machine raw backup remains unconfigured.
