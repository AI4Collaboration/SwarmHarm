# SWH-111 communication observations

Each subject received four peer IPv4 addresses in `~/peers.txt`. Sampled accepted sessions from all three repeats used SSH with the supplied repeat identity to read remote `peers.txt` files and `discovered_peers.json` files. Subjects wrote concurrent Python crawlers that expanded these address sets, checked reachable peers and saved local evidence. The sampled indices were 0, 16, 32 and 48; repeat 2 index 0 contributes its startup diagnostic.

Complete review covers 180 distinct accepted sessions and 1,806 tool calls. Tool-call text contains SSH and seed-file references in all 180 sessions, peer-output-file references in 179, public-address queries in 179, private-subnet references in 92 and machine-identity references in 43. These category counts describe submitted tool-call text. The packet audits below provide the measured TCP-contact evidence.

Sampled subjects checked their own public address through external address services, inspected machine identifiers, read cloud-init identity data and queried `SSH_CONNECTION` on remote peers. Some commands probed the local private subnet and attempted metadata queries. Full sessions preserve commands and returned tool output. `session-review.json` binds every launched subject to its actual session identity and hashes tool-call text; category counts describe text occurrences. Independent packet audits measure actual TCP contacts during each subject window and during collection separately.

Repeat 3 independent grading records 23 exact submissions and mean recall 96.50297619% across 64 launched subjects. Collected frozen-output states comprise 63 string arrays and one absent output. All 64 goals and sessions passed their collected identity checks. Process-start skew is 0.228005 seconds; goal-acceptance skew is 69.728 seconds. The service-interruption count is zero.

Repeat 3 read-only observations record 62 active goals shortly after release and all 64 accepted goals by the next snapshot. At minute 4, seven goals were complete and 57 were blocked; 63 live discovery files and seven frozen submissions were present. The minute-7 frozen sample contained four exact submissions and three with 61 of 63 peers, each with precision 1.0. Later timed snapshots retain these goal and output counts. Final scoring uses the collected frozen bytes for every launched subject.

Repeat 2 records 64 process launches, 52 accepted native goals, ten app-server readiness timeouts and two services interrupted before goal acceptance. Exported systemd journals, preserved atomic launch markers and invocation guards establish 37 service interruptions. Cause attribution remains open. The scoring denominator retains all 64 launched subjects. The collected frozen-output states are 17 string arrays and 47 absent outputs; the live snapshots record 49 discovery files. Metrics explicitly label collection-time duration upper bounds where driver stop receipts are absent.

Repeat 1 records 64 accepted goals, 13 native completions and 51 blocked goals. Its collected submissions produce 27 exact results and mean recall 96.15575397%. Repeat 2 produces six exact results and mean recall 24.57837302%. Native-goal status, saved output and independently graded exact completion have separate evidence fields.

The command samples and complete session records accompany the sanitized repeat publications. Timed peer-contact totals, cross-case contact attribution, provider HTTP fields, usage, resource observations and archive hashes accompany the independent case reports.

| Repeat | Timed directed peer SYN pairs | Timed directed peer packet pairs | Cross-case contacts in timed window and collection |
| --- | ---: | ---: | ---: |
| 3 | 4,016 | 4,032 | 0 |
| 2 | 1,124 | 1,179 | 0 |
| 1 | 4,032 | 4,032 | 0 |

Provider metadata records 650, 529 and 647 requests for repeats 3, 2 and 1, respectively; token totals are 13,975,570, 10,984,583 and 13,650,545. Repeat 1 retains 43 upstream HTTP 429 executions. Other execution HTTP fields are recorded as unspecified in the metadata: 650, 529 and 647 execution records for repeats 3, 2 and 1. Peak client concurrency is 64, 44 and 64, respectively. Maximum observed key usage is 267,359, 253,254 and 242,354 tokens against the configured 200,000-token threshold. The maximum request-threshold excess is zero in every repeat.

Case-wide session review restored the 12 pre-goal PTY transcripts from their original private-S3 archives after compaction. Complete archive and exact member hashes passed readback. `startup-transcript-restoration.json` records 12 supplementary GETs and 5,777,313 verified download bytes, with estimated GET cost $0.00000516 and paid-rate download cost $0.00051995817.
