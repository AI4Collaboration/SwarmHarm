# Provisioning and subject accounting

All provisioned instances: **512**. Scheduled subject sessions: **384**.

Three serial repeats each released 128 fresh subjects. A preceding repeat-2 preparation provisioned 128 instances, completed readiness and connectivity checks, and ended during connectivity-service shutdown with operator SSH return code 255. Its 128 inference keys have verified revocation receipts and zero request histories. Its release-timer and native-session counts are zero. Independent readback verifies cleanup of all preparation instances and original resources.

| Population | Instances | Native sessions | Exact submissions | Infrastructure USD estimate |
| --- | ---: | ---: | ---: | ---: |
| Scheduled repeats | 384 | 384 | 5/384 | 7.083942 |
| Pre-release preparation | 128 | 0 | 0/128 | 0.591643 |
| All provisioned | 512 | 384 | 5/512 | 7.675585 |

Mean recall across all 512 provisioned instances: **2.526759%**. Each pre-release preparation instance contributes zero discoveries. The scheduled-repeat scores, precision, recall and coverage retain their three 128-subject denominators. The preparation archive and audit retain instance/key identities and cleanup bindings.
