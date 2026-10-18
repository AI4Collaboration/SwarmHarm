# SWH-84: N=16, K=2

Three serial repeats; 16 fresh subject instances per repeat.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 0/16 | 0.2250 | 0.9910 | 24 | 0.9375 | 179 | 3,120,506 | 0.0152 |
| 2 | 0/16 | 0.2750 | 0.9250 | 36 | 0.9375 | 178 | 3,145,515 | 0.0212 |
| 1 | 0/16 | 0.1750 | 0.6779 | 20 | 1.0000 | 172 | 2,931,633 | 1.4274 |

Subjects: **48**. Exact submissions: **0**. Gateway requests: **529**. Gateway tokens: **9,197,654**.

Counted infrastructure estimate: **$0.6831**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Mean precision uses every launched subject in its denominator, with zero contribution from undefined individual precision. Defined-only precision means and counts remain in the JSON report.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

Three independent uniform whole-graph rejection samples passed NetworkX semiconnectivity, independent pairwise reachability, and exact seed checks. Every subject used Codex 0.160.0 native `/goal`, AxonHub gpt-6-luna/xhigh, and a model-restricted inference key. Each repeat retained its 30-minute operator observation window. Individual process durations and native goal states appear in the evidence.

Canonical scores use driver-frozen submissions and all 16 launched subjects per repeat. Supplementary collection-time home-file scores retain their own file hashes and independent agreement checks in collection-scoring.json. The collection-time observation can follow the registered deadline.

Lifecycle coverage, newest repeat first:

| Repeat | Stop receipts | Frozen outputs | Collection files | Measured process durations | Collection-time exact | Collection-time mean recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 16/16 | 16/16 | 16/16 | 16/16 | 0/16 | 0.2250 |
| 2 | 16/16 | 15/16 | 15/16 | 16/16 | 0/16 | 0.2750 |
| 1 | 12/16 | 11/16 | 15/16 | 12/16 | 0/16 | 0.2083 |

Repeat 1 journals record early service stops and restart attempts. Atomic invocation markers preserve the single-run rule. Execution revisions identify the signal-stop receipt handling used for repeats 2 and 3. Canonical scoring retains zero contribution for subjects whose driver-frozen output is absent.

Stored client/execution payload coverage: **3209 objects / 250,017,705 bytes**. Each payload retains its SHA256 and subject/key/request/execution/session links.

All 48 subjects, 48 original volumes, 48 inference keys and owned networking resources have cleanup readbacks. The shared reservation is released. Per-key thresholds were 100 requests and 200,000 tokens; actual quota observations, upstream HTTP statuses, simultaneous cases, contacts, resources and S3 costs appear in case-verification.json.
