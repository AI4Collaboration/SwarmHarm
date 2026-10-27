# SwarmHarm run dashboard (haiku-dev)

Local, read-only live view of one run directory. Standard-library Python server
plus a static page; no build step, no external scripts, no model calls.

```sh
.venv/bin/python experiments/haiku-dev/dashboard/serve.py runs/haiku-phase1-<stamp> --port 8765
# open http://127.0.0.1:8765  (binds 127.0.0.1 only; --phase <dir> picks a phase folder, default natural/)
```

The page polls `/api/run` every 4 s; the server re-reads files only when their
mtime or size changes and tolerates missing or half-written files. Clicking a
mark calls `/api/detail?actor=<id>&step=<n>` for the full step. Nothing in the
run directory is written.

| Tab | Shows |
|---|---|
| Header | Model, effort, status (`progress.json` / `completion.json`), elapsed, requests vs cap, filed checks (sum of `summary.json`), Phase 1 gate time, per-agent status |
| Agent timelines | One lane per agent over seconds since activation: response bars (coloured when the model wrote visible text), tool calls coloured by tool, platform updates (triangle), final answers (diamond), request/note writes (square), exact reads (R), gate line. Hover for a preview, click for the full text, arguments and results |
| Communication | Exact-read graph author → reader for `source-request-*` / `source-note-*`, first-read time per edge; table of every exact read (`full_body_output_matches`); record cards with replies nested by `parent_note_path` and who read each version when |
| Discovery funnel | `discoveries.json` (run root or phase folder) as a milestone × agent table plus a timeline; "not computed yet" when absent |
| Tokens | Cumulative tokens per agent over time (total, uncached input, output, cache read/write) and totals |
| Run metadata | Gate record and communication transcript, `run-meta.json`, `progress.json`, `completion.json`, `summary.json` |

Traces in Anthropic Messages format (`content` blocks, `_timing`) and OpenAI
Responses format (`output` items, `created_at`/`completed_at`, else file mtime)
are both normalised. The Responses path has not been tested on a real GLM/Sol run.
