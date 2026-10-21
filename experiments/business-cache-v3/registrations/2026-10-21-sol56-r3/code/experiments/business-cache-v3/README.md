# Business tasks with durable observation

**Infrastructure revision · 21 October 2026. No new model trial.** This family
keeps business v2's task text, fixtures, tools, ordinary service responses, model
settings, actor order and subject budgets. It imports the frozen v2 business
logic. The infrastructure changes are explicit and separately versioned:

- Commit the actual business/tool result and relevant public snapshot before
  observation. Save the regular tool trace and native output pair before holding
  for a persistent reader failure. Pending measurements remain explicit.
- Use [content-addressed public receipts](../infra-reader-v1/README.md), staged
  Docker budgets, completed-log recovery and bounded reader-only retries. Every
  observation identifies its exact receipt and whether it reused verified bytes.
- Save files atomically with fsync while preserving scheduler/input order. Handle
  operator interruption with a terminal status and resource cleanup.
- Launch the collector in its own process session with a recorded PID. This is
  a local process, not an automation or scheduled task. Duplicate launches of an
  output directory are rejected.

No warning, communication ban, ACL inventory, pressure, cooperation prompt,
fake peer, model substitution, new credential or hosted runtime change is added.
Old trajectories and primary scores stay frozen. The new outcome revision names
the durable observer; timing and observation execution differ from v2 and must
not be relabeled as the historical setting.

Prepare a fresh world with `run.py --phase prepare --output <fresh-output>`.
Preparation seals v3, its reader, the v2 business dependency, input audit and
reader configuration. Push that registration before subject calls. Then use the
same project interpreter with `launch.py --output <prepared-output>` and monitor
its saved PID, controller progress, lifecycle journal and tool commits directly.
A fresh native preflight and all six fully staged capabilities still gate the
six experimental contexts. Never resume, replace or overwrite an old world.

`review.py` verifies native histories, durable commits, public-receipt provenance,
actual client values and two fresh public-only reads per distinct recorded state.
It separately reports pending measurements and undispatched native calls. A
passed history audit with `measurement_complete: false` is not a completed eval
or evidence of zero exposure. Reports must distinguish delivered work from final
contexts and observer faults from provider/model behavior.

[Infrastructure report](../infra-reader-v1/REPORT.md). Model-free regression and
failure controls validate this integration; real-model behavior under v3 is
untested until a new registered study passes its fresh gates. Preserve Multica
0.4.44 and the maintainer's public-server security patch.
