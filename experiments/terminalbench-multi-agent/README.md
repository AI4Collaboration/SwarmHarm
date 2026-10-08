# Multi-agent persistence on the hardest Terminal-Bench 4.0 tasks (SWH-30)

Continuation of `../multi-agent-persistence/` (SWH-13). Teams of 2–4 identical coding agents (Multica squad, one EC2 runtime per agent) work on the three Terminal-Bench 4.0 tasks with the highest expert-time estimate in a network-restricted environment, while the platform wakes every agent 20 times after run endings through rules that only a person can change. Differences from SWH-13: passwordless `sudo` on the runtimes, one shared SSH key on every EC2 with SSH between the runtimes of an experiment, the Terminal-Bench verifier as grader, GLM only planned.

| Path | What it is |
|---|---|
| `design/SWH30-DESIGN.md` | Task selection, differences from SWH-13, task environments, matrix, GLM plan |
| `design/RUNBOOK.md` | Commands of one experiment from setup to teardown |
| `design/ENV-TEST-REPORT.md` | Results of the environment tests V1–V3 |
| `code/` | `provision/` (launch, setup, lockdown, checks, wipe, task issue and wakeup rules, monitor, collect, grade, trace export, teardown, final cleanup), `prompts/`, `tasks/` (`environment/`, `tests/` and `solution/` of the three Terminal-Bench tasks, used for the runtime build and for grading), `tasks.json`, `experiments.json`, `analysis/` |

`code/tasks/` contains the Terminal-Bench `tests/` and `solution/` directories. Keep this directory out of any corpus an agent or a model can read.

Experiments: `experiments.json` lists the environment tests `V1`–`V3`, the twelve experiments `TB01`–`TB12` (deepseek-flash × {2, 3} and claude-opus-5-5 × {2, 4} on three tasks) and the planned GLM runs `TB13`–`TB18`.
