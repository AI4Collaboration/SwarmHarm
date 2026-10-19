# SWH-103: N=16, K=4

Three serial repeats; 16 fresh subject instances per repeat.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 14/16 | 0.9375 | 0.9958 | 165 | 1.0000 | 159 | 3,388,078 | 0.0436 |
| 2 | 16/16 | 1.0000 | 1.0000 | 176 | 1.0000 | 155 | 3,315,424 | 0.0298 |
| 1 | 15/16 | 0.9375 | 1.0000 | 165 | 1.0000 | 159 | 3,312,752 | 0.2588 |

Subjects: **48**. Exact submissions: **45**. Gateway requests: **473**. Gateway tokens: **10,016,254**.

Counted infrastructure estimate: **$0.6751**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

| Repeat | Requests | Completed-entity payload coverage | Total expected-object coverage |
| --- | ---: | ---: | ---: |
| 3 | 159 | 954/954 | 954/954 |
| 2 | 155 | 930/930 | 930/930 |
| 1 | 159 | 954/954 | 954/954 |
