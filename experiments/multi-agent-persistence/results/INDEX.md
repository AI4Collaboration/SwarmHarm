# Results index

Each directory holds the compact export of one run: `FINAL-REPORT.md` (the sub-issue's final report), `README.txt`, `agents.json`, `wakeups.json`, `issue-body.md` (the exact task text the agents saw), `monitor.log`, `started-at.txt`, the Multica export in `multica/` (issue, comments, runs, every run's messages, wakeup rules and their runs, timeline, attachments), `grading/` (official-container results for `final.patch` and each working tree), `proxy/` (squid access log: every proxied request including denied hosts), `runtimes/rt-*/` (git state, diff against the base commit, firewall and sudo records, daemon journal) and `axonhub-requests-metadata.json` (request index with API key, model, status and timing).

The full trace packages additionally hold the AxonHub request and response bodies of every model call and the agents' local session state (Codex rollouts, Claude Code sessions); they are large and stay in S3 (bucket `swarmharm-swh13-artifacts-906513713427`, eu-central-1). `C01`–`C03` are the stage-1 configuration tests with a one-hour rehearsal each; `E01`–`E12` are the twelve experiments of the analysis.

| Experiment | Sub-issue | Model (harness) | Agents | Task | Trace package in S3 | Size | sha256 |
|---|---|---|---|---|---|---|---|
| C01 | SWH-14 | deepseek-flash (codex) | 2 | T1-ansible-combine-vars | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-C01-traces.tar.xz` | 11.3 MB | `7e7e6292997ba3ae…` |
| C02 | SWH-15 | glm-5.3-flash (codex) | 2 | T2-qutebrowser-search-url | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-C02-traces.tar.xz` | 1.2 MB | `0babecb92bd4a1cc…` |
| C03 | SWH-16 | claude-opus-5-5 (claude) | 2 | T1-ansible-combine-vars | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-C03-traces.tar.xz` | 10.4 MB | `01341b63fd32c10d…` |
| E01 | SWH-17 | deepseek-flash (codex) | 2 | T1-ansible-combine-vars | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E01-traces.tar.xz` | 7.2 MB | `57ed54dba7a827ac…` |
| E02 | SWH-18 | deepseek-flash (codex) | 3 | T1-ansible-combine-vars | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E02-traces.tar.xz` | 15.3 MB | `6448e4adb2d3a39f…` |
| E03 | SWH-19 | glm-5.3-flash (codex) | 3 | T1-ansible-combine-vars | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E03-traces.tar.xz` | 3.4 MB | `f233b7a9740df55a…` |
| E04 | SWH-20 | glm-5.3-flash (codex) | 4 | T1-ansible-combine-vars | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E04-traces.tar.xz` | 4.3 MB | `74b4c8b64f854d25…` |
| E05 | SWH-21 | claude-opus-5-5 (claude) | 2 | T1-ansible-combine-vars | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E05-traces.tar.xz` | 7.6 MB | `93d47ad106721130…` |
| E06 | SWH-22 | claude-opus-5-5 (claude) | 4 | T1-ansible-combine-vars | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E06-traces.tar.xz` | 465.7 MB | `dc6f04ef04c343d3…` |
| E07 | SWH-23 | deepseek-flash (codex) | 2 | T2-qutebrowser-search-url | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E07-traces.tar.xz` | 7.3 MB | `3049f0ff3dbce631…` |
| E08 | SWH-24 | deepseek-flash (codex) | 3 | T2-qutebrowser-search-url | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E08-traces.tar.xz` | 12.0 MB | `6c39803cf6efb777…` |
| E09 | SWH-25 | glm-5.3-flash (codex) | 3 | T2-qutebrowser-search-url | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E09-traces.tar.xz` | 3.6 MB | `dee0164f51d960a8…` |
| E10 | SWH-26 | glm-5.3-flash (codex) | 4 | T2-qutebrowser-search-url | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E10-traces.tar.xz` | 4.4 MB | `88bf74dd493d4eca…` |
| E11 | SWH-27 | claude-opus-5-5 (claude) | 2 | T2-qutebrowser-search-url | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E11-traces.tar.xz` | 6.5 MB | `5b276633b0d3876f…` |
| E12 | SWH-28 | claude-opus-5-5 (claude) | 4 | T2-qutebrowser-search-url | `s3://swarmharm-swh13-artifacts-906513713427/traces/swh13-E12-traces.tar.xz` | 37.8 MB | `db729fc46b007f72…` |
