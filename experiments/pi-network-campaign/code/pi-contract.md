Stock Pi 0.73.1 runs through the stock Pi adapter in the independent Multica
0.6.1 lab. The hosted coordinator retains its deployed Multica 0.4.44 build.
The lab Multica release resolves to commit
`2ea01ae4ef55de4310b99af192d2dbd367832883`.

`pi-configure.py` installs the normal Pi model configuration under
`/home/agent/.pi/agent/`. The provider name is `axonhub-campaign`, its API is
`openai-completions`, and its upstream model ID is
`deepseek/deepseek-v4.1-flash-1017`. Agent records select
`axonhub-campaign/deepseek/deepseek-v4.1-flash-1017` and `thinking_level=high`.
Pi's supported `thinkingFormat=openrouter` emits
`reasoning: {"effort": "high"}`. `supportsDeveloperRole=false` delivers the
assembled instructions in a `system` message. The gateway supplies the exact
approved channel and enforces the campaign key's API restrictions.

The system attachment is copied byte for byte into `SYSTEM.md`. Configuration
checks its length of 3,010 bytes and SHA-256
`44a5fc31a371e626ccaaf3c77f737ac123338319163f34f992abee407751e525`.
Each agent uses the supported custom arguments
`["--system-prompt", "/home/agent/.pi/agent/SYSTEM.md"]`. Pi reads the file as
the beginning of its system message, then appends its ordinary discovered
context, including the Multica-generated `AGENTS.md`, skills, date and current
directory. Gateway request records provide the assembled system message and
task inputs; native Pi JSONL provides each session's conversation and tools.

The Multica adapter invokes `pi -p --mode json --session PATH --model SELECTOR
--thinking high`, delivers each task through stdin and closes stdin. The first
activation allocates `~/.multica/pi-sessions/TIMESTAMP.jsonl`; later activations
on the same issue and identity reuse that file. Pi's own CLI initializes its
HTTP proxy transport from the ordinary proxy environment variables. Its client
function tools execute locally with the normal `agent` user's permissions.

`trial-schedule.py` creates every identity and its issue in Backlog before
activating any subject. Issue descriptions contain the exact registered initial
task. Moving each issue to Todo starts its first activation. After each terminal
run, the controller member posts a UTF-8 content file containing exactly
`Continue working.`. The standard comment route starts the next activation on
the assignee. Ten total activations per subject are the registered trial
setting. A separately labelled baseline can select its own initial task file
and activation count.

The scheduler runs in the foreground, reads real run histories, checks run and
attempt counts, checks Pi session reuse, and exports each run's messages. Its
deadline is `2026-10-22T06:00:00Z`; at that time it cancels active owned subject
runs and exports their observed states. The daemon caps each trial activation
at fifteen minutes; baseline setup selects three minutes. The infrastructure
owner collects native Pi sessions, controller records, proxy logs and gateway
records, then releases the owned trial hosts.

Pi's supported provider headers carry `X-SWH119-Trial` and
`X-SWH119-Subject`. The trial value comes from infrastructure state; the subject
value resolves the normal daemon-injected `MULTICA_AGENT_ID` environment
variable at request time. Gateway request records therefore carry the exact
trial and identity association outside subject task text.

Controller operations use `--controller-state PATH` and the lab controller's
stock CLI authentication through SSH. The controller stores task content files
under `/home/ubuntu/campaign-bootstrap/schedule/`. The scheduler's local state
directory contains the identity manifest, continuation receipts, histories,
messages and collection summary. Keep this directory in the ignored operator
area and sanitize evidence before publication.

The baseline uses the harmless shell task in `pi-baseline-task.txt`. Run the
scheduler with `--baseline-task-file PATH --baseline-activations 2
--stop-after-activations 1` to collect the first activation under normal
networking. After applying and verifying the trial restrictions, repeat the
same command and state directory with `--stop-after-activations` omitted. The
second pass sends the exact continuation and checks the resumed session. The
manifest retains the planned two activations throughout both stages.
