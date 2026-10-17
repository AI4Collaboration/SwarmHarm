# SwarmHarm project rules

- Put the newest update, setup change and experiment/result entry first in maintained README files, reports and indexes, including updates on the same date. Follow `.cursor/rules/latest-first.mdc`; never reorder or rewrite frozen protocols, source snapshots or archived results.
- Read `README.md` → **Current setup** before setup, model-routing or evaluation work.
- Every setup change must update that README section in the same change: affected versions, endpoints, permissions, credential availability (never values), commands, verification date/evidence, and remaining limits. Do not leave superseded settings presented as current.
- Keep the hosted coordinator/runtime on the existing Multica 0.4.44 setup. Preserve the maintainer's public-server file-access security patch. Do not treat an upstream upgrade or daemon restart as routine eval preparation.
- Before any explicitly requested future upgrade, identify the exact patch and deployed build, plan patch migration and rollback, and verify protection and compatibility. Do not infer that the SWH-13 wakeup patch is the public-server security patch.
- Follow SWH-30/59/60's separation of coordinator and independent experiment labs. Test model tools, network restrictions and experimental permission rules in the environment to which the claim applies.
- Treat model names, installed clients and historical successful runs as insufficient proof of current model access. Verify the active route and exact model/harness pairing before a new experiment.
- Keep agent tasks free of evaluator instructions, hidden tests, gold patches and operator credentials. Record the intended pressure manipulation separately from operator infrastructure instructions.
- Export and independently grade experiment artifacts, then stop owned wakeups/runs, tear down owned lab resources and revoke scoped experiment keys. Record cleanup evidence.
- Preserve historical experiment settings and results. Distinguish configuration, live verification and historical evidence; never commit credentials or raw credential-bearing traces.
