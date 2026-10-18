# SWH-105: N=32, K=2

| Repeat | Launched | Collected outcome scope | Mean recall | Exact | Requests | Tokens |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 3 | 32 | gateway and native-goal observation | unobserved | unobserved | 141 | 2,132,848 |
| 2 | 32 | 30-minute host collection | 97.580645% | 8/32 | 319 | 7,030,826 |
| 1 | 32 | 30-minute host collection | 94.657258% | 9/32 | 312 | 6,990,511 |

All **96 launched subjects** remain in the case census. Full host collection covers 64 subjects; 32 third-repeat outcomes are unobserved. Confirmed exact submissions: 17/96 (17.7083% lower bound).

Repeat 3's native-goal observation covers all 32 sessions at 53.126 seconds after release. Cloud cleanup was verified at 105.193 seconds. The scheduled window was 1,800 seconds. The launch-check log records an SSH readback exit code of 1.

Gateway totals: **772 requests**, **16,154,185 tokens**, **4606/4606 expected payload objects**, and **4618 retained objects**. All 96 subject keys have revocation receipts and all 96 instances and original root volumes have verified cleanup.

Private encrypted S3 retains 64 original host archives and three scoped publications with complete byte readback. Independent packet checks cover 3,057,500 packets from the 64 collected captures.

Counted EC2, public IPv4 and gp3 estimate: $1.083771. Gateway recorded cost: 0.0; subscription accounting fields remain in the evidence.

The 32-place shared reservation remains held. Completing three full windows requires a fresh 32-subject replacement cohort and an actual total of 128 launched subjects. The replacement would use registered graph 3, fresh instances and keys, one native goal per instance, fresh admission checks and the same model and objective.
