# Human-only issue wakeup settings for Multica

Patch file: `multica-human-only-wakeups.patch`

Result: only people create, replace, enable, disable, delete or edit the instruction of an issue wakeup, and only people change the child-done system wakeup (per issue or as workspace default). Every agent credential receives `403`.

## Target and applicability

| Item | Value |
| --- | --- |
| Source | `github.com/multica-ai/multica` |
| Base release | `v0.6.1` (`2ea01ae4e`) |
| Also applies cleanly to | `main` at `b4ca5b4a2` (checked with `git apply --check`, built and tested) |
| Apply | `git apply --check multica-human-only-wakeups.patch && git apply multica-human-only-wakeups.patch` |
| Alternative | `patch -p1 < multica-human-only-wakeups.patch` |

On any other branch or version, run `git apply --reject multica-human-only-wakeups.patch`. Hunks that fit are applied and the remaining ones are written to `*.rej` files; finish those with the manual recipe below. Codebases without the wakeup feature (for example `v0.4.x`) have nothing to patch.

## How agents are recognised

The auth middleware turns an agent run's `mat_` task token into `X-Actor-Source: task_token` plus `X-Agent-ID` (cloud-node `mcn_` tokens become `X-Actor-Source: cloud_pat`). The header is server-set and any client-supplied value is stripped, so it is the authoritative signal. The patch reuses the existing `handler.RequireHumanActor` middleware and `isMachineCredentialActor(r)` helper in `server/internal/handler/actor_guards.go`. Every run the daemon starts holds a `mat_` token, so every agent is covered, including an agent acting for the person who started its run.

## Behaviour after the patch

| Request | Person (JWT or `mul_` PAT) | Agent run (`mat_`) |
| --- | --- | --- |
| `POST /api/issues/{id}/wakeups` | 201 | 403 |
| `PUT /api/issues/{id}/wakeups/{wid}` | 200 | 403 |
| `POST .../wakeups/{wid}/disable` and `/enable` | 200 | 403 |
| `PATCH .../wakeups/{wid}/instruction` | 204 | 403 |
| `DELETE .../wakeups/{wid}` | 204 | 403 |
| `PUT /api/issues/{id}/system-wakeups/{rule}` | 200 | 403 |
| `PUT /api/system-wakeups/{rule}` (workspace default) | 200 for owners and admins | 403 |
| `PUT` or `PATCH /api/workspaces/{id}` with a `settings` body that adds, edits or drops `system_wakeup_child_done` or `system_wakeup_child_done_instruction` | 200 | 403 |
| Reads: `GET .../wakeups`, `.../runs`, `.../system-wakeups`, `/api/issue-wakeups`, `/api/system-wakeups`, `/api/issue-wakeup-summaries` | 200 | 200 |
| `POST .../wakeups/{wid}/trigger` (queue one run of an existing rule) | unchanged | unchanged |
| `POST .../wakeups/{wid}/checkin` (a run a rule started ends its check) | unchanged | unchanged |

The 403 body from the handler guard is `{"error":"only people can create, change or remove wakeup settings","code":"wakeup_human_only"}`. The router middleware answers with `this endpoint is only available to human actors`.

## What the patch changes

Server enforcement uses three layers.

1. **Router** (`server/cmd/server/router.go`). Wrap the mutation routes with `handler.RequireHumanActor` through `r.With(...)`.
2. **Handlers** (`server/internal/handler/issue_wakeup.go`, `issue_system_wakeup.go`). Each mutation handler repeats the check, so a handler stays protected when it is mounted on another router.
3. **Workspace settings** (`server/internal/handler/workspace.go`). The workspace update replaces the whole `settings` object and stores the child-done default inside it. A machine credential may send settings only when the two wakeup keys keep their stored values.

Supporting changes: the daemon prompt and runtime brief tell agents that wakeup settings belong to members, the `multica-platform` built-in skill describes the new rule, the CLI help states it, and `docs/engineering/issue-wakeups.md` records it.

## Manual patch recipe for other branches or versions

Locate each anchor with the grep given, then apply the edit.

### 1. Router: `server/cmd/server/router.go`

Find the routes with `grep -n "wakeups\|system-wakeups" server/cmd/server/router.go`. Replace

```go
r.Post("/wakeups", h.CreateIssueWakeup)
r.Put("/wakeups/{wakeupID}", h.CreateIssueWakeup)
r.Post("/wakeups/{wakeupID}/disable", h.DisableIssueWakeup)
r.Post("/wakeups/{wakeupID}/enable", h.EnableIssueWakeup)
r.Patch("/wakeups/{wakeupID}/instruction", h.EditIssueWakeupInstruction)
r.Delete("/wakeups/{wakeupID}", h.DeleteIssueWakeup)
...
r.Put("/system-wakeups/{rule}", h.UpdateIssueSystemWakeup)
...
r.Put("/api/system-wakeups/{rule}", h.UpdateWorkspaceSystemWakeup)
```

with the same lines prefixed by `r.With(handler.RequireHumanActor).`, for example

```go
r.With(handler.RequireHumanActor).Post("/wakeups", h.CreateIssueWakeup)
r.With(handler.RequireHumanActor).Put("/system-wakeups/{rule}", h.UpdateIssueSystemWakeup)
r.With(handler.RequireHumanActor).Put("/api/system-wakeups/{rule}", h.UpdateWorkspaceSystemWakeup)
```

Leave `trigger`, `checkin`, `runs` and every `Get` untouched. Any additional route a version adds for creating, changing or deleting a wakeup (for example a bulk or batch endpoint) receives the same wrapper.

### 2. Handler guard: `server/internal/handler/issue_wakeup.go`

Add above `CreateIssueWakeup`:

```go
// requireHumanWakeupManager lets only people create, change, enable, disable
// and delete wakeup settings. Agents and every other machine credential are
// refused, including an agent acting for the person who started its run.
func (h *Handler) requireHumanWakeupManager(w http.ResponseWriter, r *http.Request, workspaceID string) bool {
	actorType, _ := h.resolveActor(r, requestUserID(r), workspaceID)
	if actorType == "agent" || isMachineCredentialActor(r) {
		writeErrorCode(w, http.StatusForbidden, "wakeup_human_only", "only people can create, change or remove wakeup settings")
		return false
	}
	return true
}
```

Insert this call directly after `loadIssueForUser` succeeds (after the `if !ok { return }` block, and after the wakeup-id parse when the handler has one) in `CreateIssueWakeup`, `DisableIssueWakeup`, `EnableIssueWakeup`, `EditIssueWakeupInstruction` and `DeleteIssueWakeup`:

```go
if !h.requireHumanWakeupManager(w, r, uuidToString(issue.WorkspaceID)) {
	return
}
```

In `CreateIssueWakeup`, delete the branch that defaults the target to the calling agent (`if in.AgentID == "" && actorType == "agent" { in.AgentID = actorID }`).

### 3. System wakeup human check: `server/internal/handler/issue_system_wakeup.go`

In `systemWakeupHuman`, change `if actorType != "member" {` to `if actorType != "member" || isMachineCredentialActor(r) {`. Both `UpdateIssueSystemWakeup` and `UpdateWorkspaceSystemWakeup` call it.

Add the settings comparison helper (and `"reflect"` to the imports):

```go
// systemWakeupSettingsChanged reports whether replacing the stored workspace
// settings with incoming adds, removes or edits a workspace default of a
// platform wakeup rule. The settings write replaces the whole object, so a
// payload that leaves these keys out changes them too.
func systemWakeupSettingsChanged(stored []byte, incoming any) bool {
	raw, err := json.Marshal(incoming)
	if err != nil {
		return true
	}
	var next, current map[string]any
	if json.Unmarshal(raw, &next) != nil {
		return true
	}
	_ = json.Unmarshal(stored, &current)
	for _, key := range []string{service.WorkspaceSettingChildDone, service.WorkspaceSettingChildDoneInstruction} {
		before, hadBefore := current[key]
		after, hasAfter := next[key]
		if hadBefore != hasAfter || !reflect.DeepEqual(before, after) {
			return true
		}
	}
	return false
}
```

If a version names the two settings keys differently, find them with `grep -rn "system_wakeup" server/internal/service` and use those constants.

### 4. Workspace settings guard: `server/internal/handler/workspace.go`

In `UpdateWorkspace`, immediately before the existing `if req.Settings != nil {` block that marshals the settings, add:

```go
if req.Settings != nil && isMachineCredentialActor(r) {
	existing, err := h.Queries.GetWorkspace(r.Context(), idUUID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to read workspace settings")
		return
	}
	if systemWakeupSettingsChanged(existing.Settings, req.Settings) {
		writeErrorCode(w, http.StatusForbidden, "wakeup_human_only", "only people can create, change or remove wakeup settings")
		return
	}
}
```

When a version stores wakeup defaults in another place that the workspace update endpoint reaches, extend `systemWakeupSettingsChanged` to compare those keys as well.

### 5. Agent-facing text (recommended)

These edits keep agents from retrying commands that return 403.

- `server/internal/daemon/execenv/runtime_config_sections.go`: the CLI bullet for `multica issue wakeup` lists only `<list|get|runs|events|trigger|checkin>` and says people manage wakeup settings. Keep the word `schedule` out of this brief; an existing test asserts it stays out.
- `server/internal/daemon/prompt.go` (`buildPromptBody`, wakeup branch): replace the "disable it with `multica issue wakeup disable ...`" sentence with "Wakeup settings are managed by members only; if recurring work is no longer needed, say so in your comment so a member can disable it."
- `server/internal/service/builtin_skills/multica-platform/references/issues.md`, section "Issue wakeups": state that agents read wakeups, queue `trigger` and `checkin`, and report needed follow-ups in the final comment.
- `server/cmd/multica/cmd_issue_wakeup.go`: add a `Long` description to the `wakeup` command with the same rule.
- `docs/engineering/issue-wakeups.md`: add the "People manage wakeup settings" paragraph.

### 6. Tests

- `server/internal/handler/issue_wakeup_human_only_test.go`: direct handler calls with `task_token`, bare agent headers and `cloud_pat` credentials for create, replace, disable, enable, instruction and delete; each answers 403 and the stored wakeup stays enabled. Unit cases for `systemWakeupSettingsChanged`.
- `server/cmd/server/wakeup_human_only_integration_test.go`: real router, real `mat_` token. A person creates a wakeup; the agent token receives 403 for the eight mutation routes and for settings updates that touch the wakeup keys, keeps read access, and may resend an unchanged settings body; the person then disables and deletes the wakeup.
- `server/internal/daemon/wakeup_prompt_test.go`: expects `wakeup get issue wake` and `managed by members only` in the wakeup prompt, and checks that `wakeup disable` is absent.

## Verification

Run from `server/` with PostgreSQL (pgvector image) and migrations applied (`DATABASE_URL=... go run ./cmd/migrate up`):

```sh
go build ./...
go vet ./cmd/server ./internal/handler ./internal/daemon/... ./cmd/multica
go test -p 1 -count=1 ./cmd/server ./cmd/multica ./internal/handler ./internal/service/... ./internal/daemon/... ./internal/middleware
```

Quick check of the new behaviour only:

```sh
go test -count=1 ./cmd/server ./internal/handler ./internal/daemon \
  -run 'TestWakeupSettingsAreHumanOnly|TestWakeupSettingHandlersRefuseMachineCredentials|TestSystemWakeupSettingsChanged|TestWakeupPromptPreservesInstructionAndDeliveryThread'
```

Manual smoke test on a deployed server: inside an agent run, `multica issue wakeup create <issue> --kind at --after 10m --instruction "x"` returns 403; the same command under a member login returns 201.

## Rollout notes

- Deploy the server image built from the patched source. The patch adds no migration and changes no API response shape for people.
- Existing wakeups created earlier by agents keep running. People can disable or delete them from the issue sidebar or with `multica issue wakeup` under their own login.
- Older agent CLI binaries print the 403 message when they try a blocked command; the server is the single enforcement point.
- Autopilots (scheduled agent automations) are a separate feature and keep their current permissions.
