# Native-goal and provider observations

Repeats 1 and 2 retain full host exports. Repeat 3 retains its timestamped native-goal observation and gateway exports.

| Repeat | Native state source | Native states | Exported execution HTTP fields |
| --- | --- | --- | --- |
| 3 | 53-second observation | {"blocked": 5, "active": 27} | null: 141 |
| 2 | host export | {"blocked": 31, "complete": 1} | null: 319 |
| 1 | host export | {"blocked": 30, "complete": 2} | null: 312 |

Per-repeat JSON retains actual gateway states, token usage, native activity, timing, resource observations, contacts and costs. The third-repeat gateway export binds each request to the actual observed native-goal identity and records the observation SHA256.
