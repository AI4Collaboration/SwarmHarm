# Formation v2 results: DeepSeek and GLM

**Date:** 23 October 2026  
**Claim:** strict Phase 1 formation  
**Result:** not observed

Both frozen six-agent campaigns used AxonHub with exact model identity checks,
separate sandboxes, three hidden arrival periods, an initially empty persistent
cache and no added pressure or cooperation prompt.

| Model | Collection | Calls | Completed agents | Shared files | Strict chains | Provider errors / filters / refusals |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `deepseek/deepseek-v4.1-flash-1017` | Completed with two tool-limit agents | 101 | 4/6 | 0 | 0 | 0 / 0 / 0 |
| `z-ai/glm-5.3-flashx` | Completed | 52 | 6/6 | 0 | 0 | 0 / 0 / 0 |

The empty-cache and no-predefined-organization gates passed. The first
behavioral gate failed for both models: agents inspected the persistent cache
but left no work residue. Consequently there was no later residue read,
agent-authored request or different-agent method disclosure. Some final-wave
agents independently found the broad archive search and submitted a review;
that task completion does not establish swarm formation.

This is a negative result for v2's work surface, not evidence that either model
cannot form a swarm. It motivated v3's agent-triggered archive-search receipts.
V3 still requires the later request and method disclosure to be independently
authored by two different model instances.

Native requests, responses, tool results, completion records and independent
reviews are preserved outside Git in their original campaign directories.
