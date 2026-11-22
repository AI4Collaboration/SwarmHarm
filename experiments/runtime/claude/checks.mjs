import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setImmediate } from "node:timers/promises";
import { ClaudeBridge, SessionRecordStore } from "./bridge.mjs";

// Scripted SDK frames test fail-closed behavior. The Python integration check
// separately exercises the real SDK and CLI against localhost.
async function fixture(t, goalMode = "off") {
  const folder = mkdtempSync(join(tmpdir(), "swarmharm-claude-guard-"));
  const events = [];
  const frames = [];
  let sdkCwd;
  let wake;
  let closed = false;
  const query = (async function* () {
    while (!closed) {
      if (frames.length) yield frames.shift();
      else await new Promise((resolve) => { wake = resolve; });
    }
  })();
  Object.assign(query, {
    initializationResult: async () => ({}),
    supportedCommands: async () => [{ name: "goal", builtin: true }],
    setMcpServers: async () => ({ errors: {} }),
    close: () => { closed = true; wake?.(); },
  });
  const sdk = {
    query: (args) => {
      assert.deepEqual(args.options.tools, []);
      assert.deepEqual(args.options.systemPrompt, { type: "preset", preset: "claude_code" });
      sdkCwd = args.options.cwd;
      assert.equal(sdkCwd.startsWith(folder), false);
      assert.ok(existsSync(sdkCwd));
      writeFileSync(join(sdkCwd, "sdk-state.json"), "{}");
      return query;
    },
    createSdkMcpServer: (args) => args,
    tool: (name, description, inputSchema, handler) => ({ name, handler }),
  };
  const bridge = new ClaudeBridge(sdk, {
    emit: (event) => events.push(event),
    request: () => { throw new Error("A rejected SDK frame executed a tool"); },
    cancelAll: () => {},
  });
  await bridge.init({ folder, model: "claude-fixture-1",
    active_tools: [], tools: [], settings: { tools: [] }, request_timeout_ms: 100, goal_mode: goalMode,
    input_delivery: goalMode === "off" ? "atomic-sdk-replay-v1" : undefined });
  t.after(async () => {
    await bridge.close();
    assert.equal(existsSync(sdkCwd), false);
    assert.ok(existsSync(join(folder, "workspace", "sdk-state.json")));
    rmSync(folder, { recursive: true });
  });
  return { bridge, events, async feed(...messages) {
    frames.push(...messages); wake?.(); await setImmediate();
  } };
}

test("a changed provider model stops before controller execution", async (t) => {
  const f = await fixture(t);
  await f.feed({ type: "stream_event", event: { type: "message_start", message: {
    id: "message-1", model: "claude-other-1" } } });
  assert.equal(f.events.at(-1).type, "fatal");
  assert.match(f.events.at(-1).message, /expected claude-fixture-1/);
  assert.equal(f.events.filter((event) => event.type === "tool_call").length, 0);
});

test("a delegation is atomic and later queued input is not projected before SDK delivery", async (t) => {
  const f = await fixture(t);
  f.bridge.prompt(["Workspace metadata", "Deliver the qualified release."]);
  const initial = f.bridge.input.read();
  assert.equal(f.bridge.input.read(), null);
  assert.equal(initial.message.content, "Workspace metadata\n\nDeliver the qualified release.");
  await f.feed({ ...initial, isReplay: true });
  f.bridge.prompt(["Archive updated."]);
  const notice = f.bridge.input.read();
  await f.feed({ type: "stream_event", event: { type: "message_start", message: {
    id: "message-1", model: "claude-fixture-1" } } });
  const first = f.events.find((e) => e.type === "request");
  assert.deepEqual(first.payload.input.filter((v) => v.role === "user"), [initial.message]);
  await f.feed({ type: "stream_event", event: { type: "message_stop" } },
    { ...notice, isReplay: true },
    { type: "stream_event", event: { type: "message_start", message: {
      id: "message-2", model: "claude-fixture-1" } } });
  assert.deepEqual(f.events.at(-1).payload.input.filter((v) => v.role === "user"),
    [initial.message, notice.message]);
});

test("changed replay and inference before initial delivery fail closed", async (t) => {
  const f = await fixture(t);
  f.bridge.prompt(["Workspace", "Business task"]);
  const initial = f.bridge.input.read();
  await f.feed({ ...initial, message: { role: "user", content: "Changed task" } });
  assert.equal(f.events.at(-1).type, "fatal");
  assert.match(f.events.at(-1).message, /replay differs/);
  const g = await fixture(t);
  g.bridge.prompt(["Workspace", "Business task"]);
  await g.feed({ type: "stream_event", event: { type: "message_start", message: {
    id: "message-1", model: "claude-fixture-1" } } });
  assert.equal(g.events.at(-1).type, "fatal");
  assert.match(g.events.at(-1).message, /no SDK delivery/);
});

test("built-in host tools are rejected at session initialization", async (t) => {
  const f = await fixture(t);
  await f.feed({ type: "system", subtype: "init", tools: ["Bash", "Read"] });
  assert.equal(f.events.at(-1).type, "fatal");
  assert.match(f.events.at(-1).message, /unregistered tools/);
});

test("a tool heartbeat leaves the main context active while nested inference is rejected", async (t) => {
  const f = await fixture(t);
  await f.feed({ type: "tool_progress", tool_use_id: "call-1-heartbeat-0",
    tool_name: "mcp__work__bash", parent_tool_use_id: "call-1",
    elapsed_time_seconds: 30, heartbeat: true });
  await f.feed({ type: "stream_event", event: { type: "message_start", message: {
    id: "message-1", model: "claude-fixture-1" } } });
  assert.equal(f.events.at(-1).type, "request");
  await f.feed({ type: "stream_event", parent_tool_use_id: "call-1",
    event: { type: "message_start", message: { id: "nested", model: "claude-fixture-1" } } });
  assert.equal(f.events.at(-1).type, "fatal");
  assert.match(f.events.at(-1).message, /nested Claude session/);
});

test("an unavailable Phase 2 tool is rejected by the SDK without controller execution", async (t) => {
  const f = await fixture(t);
  await f.feed(
    { type: "stream_event", event: { type: "message_start", message: { id: "message-1", model: "claude-fixture-1" } } },
    { type: "assistant", message: { id: "message-1", content: [
      { type: "tool_use", id: "call-1", name: "mcp__continuation__book_replica_upgrade", input: {} }] } },
    { type: "stream_event", event: { type: "message_stop" } },
  );
  assert.equal(f.events.at(-1).type, "provider_response");
  await f.feed({ type: "user", message: { content: [{ type: "tool_result",
    tool_use_id: "call-1", is_error: true, content: "Tool unavailable." }] } });
  assert.equal(f.events.at(-1).type, "turn_end");
  assert.equal(f.events.filter((event) => event.type === "tool_result_error").length, 1);
  assert.equal(f.events.filter((event) => event.type === "fatal").length, 0);
  assert.equal(f.bridge.history.at(-1).output, "Tool unavailable.");
});

test("an unexecuted host tool cannot claim successful execution", async (t) => {
  const f = await fixture(t);
  await f.feed(
    { type: "stream_event", event: { type: "message_start", message: { id: "message-1", model: "claude-fixture-1" } } },
    { type: "assistant", message: { id: "message-1", content: [
      { type: "tool_use", id: "call-1", name: "Bash", input: { command: "pwd" } }] } },
    { type: "stream_event", event: { type: "message_stop" } },
    { type: "user", message: { content: [{ type: "tool_result", tool_use_id: "call-1", content: "/host" }] } },
  );
  assert.equal(f.events.at(-1).type, "fatal");
  assert.match(f.events.at(-1).message, /Unexecuted Claude tool returned success/);
});

test("provider exhaustion is a hold with no client fallback query", async (t) => {
  const f = await fixture(t);
  await f.feed({ type: "rate_limit_event", rate_limit_info: { status: "rejected" } });
  assert.equal(f.events.at(-1).type, "settled");
  assert.match(f.events.at(-1).error_message, /provider rate limit reached/);
  assert.equal(f.events.filter((event) => event.type === "request").length, 0);
});

test("compaction preserves a held attempt instead of accepting rewritten history", async (t) => {
  const f = await fixture(t);
  await f.feed({ type: "system", subtype: "compact_boundary" });
  assert.equal(f.events.at(-1).type, "settled");
  assert.match(f.events.at(-1).error_message, /compact_boundary/);
});

test("native goal command output is recorded without treating it as model inference", async (t) => {
  const f = await fixture(t, "claude_goal");
  f.bridge.prompt(["/goal Receipts are filed."]);
  await f.feed({ type: "assistant", local_command_run: { command: "goal", args: "Receipts are filed." },
    message: { model: "<synthetic>", content: [{ type: "text", text: "Goal set: Receipts are filed." }] } });
  await f.feed({ type: "stream_event", event: { type: "message_start", message: {
    id: "message-1", model: "claude-fixture-1" } } });
  assert.equal(f.events.at(-1).type, "request");
});

test("a goal refusal stops the SDK before any continuation", async (t) => {
  const f = await fixture(t, "claude_goal");
  await f.feed(
    { type: "stream_event", event: { type: "message_start", message: { id: "message-1", model: "claude-fixture-1" } } },
    { type: "stream_event", event: { type: "message_delta", delta: { stop_reason: "refusal" } } },
    { type: "stream_event", event: { type: "message_stop" } },
  );
  assert.equal(f.events.at(-1).type, "settled");
  assert.match(f.events.at(-1).error_message, /refused/);
  assert.equal(f.events.filter((event) => event.type === "request").length, 1);
});


test("SDK appends during a tool preserve an authored edit and later native bytes", async (t) => {
  const folder = mkdtempSync(join(tmpdir(), "record-transaction-"));
  t.after(() => rmSync(folder, { recursive: true }));
  const store = new SessionRecordStore(folder, "session-1");
  const key = { sessionId: "session-1" };
  const file = join(folder, "session.jsonl");
  const original = { type: "user", uuid: "one", message: { content: "original" } };
  const later = { type: "assistant", uuid: "two", message: { content: "later native entry" } };
  store.append(key, [original]);
  const before = readFileSync(file, "utf8");
  await store.duringTool(async () => {
    // The SDK can invoke its eager store callback while the controller awaits Docker.
    store.append(key, [later]);
    await setImmediate();
    assert.equal(readFileSync(file, "utf8"), before);
    assert.equal(readdirSync(join(folder, "native-store")).length, 2);
    writeFileSync(file, before.replace("original", "edited"));
  });
  const rows = readFileSync(file, "utf8").trim().split("\n").map(JSON.parse);
  assert.equal(rows[0].message.content, "edited");
  assert.deepEqual(rows[1], later);
  const journal = JSON.parse(readFileSync(join(folder, "native-store", "000001.json")));
  assert.deepEqual(journal.entries, [original]);
});

test("tool errors and no-op commands flush SDK appends exactly once", async (t) => {
  const folder = mkdtempSync(join(tmpdir(), "record-error-"));
  t.after(() => rmSync(folder, { recursive: true }));
  const store = new SessionRecordStore(folder, "session-1");
  const key = { sessionId: "session-1" };
  store.append(key, [{ id: 1 }]);
  await assert.rejects(store.duringTool(async () => {
    store.append(key, [{ id: 2 }]);
    throw new Error("tool failed");
  }), /tool failed/);
  await store.duringTool(async () => { store.append(key, [{ id: 3 }]); });
  store.flush();
  assert.deepEqual(readFileSync(join(folder, "session.jsonl"), "utf8").trim().split("\n").map(JSON.parse),
    [{ id: 1 }, { id: 2 }, { id: 3 }]);
  assert.throws(() => store.append({ sessionId: "other" }, [{ id: 4 }]), /identity/);
  assert.equal(readdirSync(join(folder, "native-store")).length, 3);
});


test("native API failures retain their diagnostic and never become subject content", async (t) => {
  for (const error of ["unknown", undefined]) {
    const f = await fixture(t);
    const initialHistory = structuredClone(f.bridge.history);
    await f.feed({ type: "assistant", error, is_api_error_message: true,
      message: { content: [{ type: "text", text: "Malformed stream; HTTP 200 JSON is not a Message." }] } });
    assert.equal(f.events.at(-1).type, "settled");
    assert.match(f.events.at(-1).error_message, /Malformed stream; HTTP 200 JSON is not a Message/);
    assert.match(f.events.at(-1).error_message, /native=/);
    assert.equal(f.events.filter((event) => event.type === "request" || event.type === "tool_call").length, 0);
    assert.deepEqual(f.bridge.history, initialHistory);
  }
});

// No later SDK hook is needed to seal a fully completed response budget.
test("a completed response closes the cap before a queued input can reopen it", async (t) => {
  const f = await fixture(t);
  f.bridge.turnLimit = 1;
  await f.feed(
    { type: "stream_event", event: { type: "message_start", message: { id: "message-1", model: "claude-fixture-1" } } },
    { type: "assistant", message: { id: "message-1", content: [{ type: "text", text: "Waiting." }] } },
    { type: "stream_event", event: { type: "message_stop" } },
  );
  const limit=f.events.find((v)=>v.type === "budget_limit");
  assert.equal(limit.limit.subject_turns,1);
  assert.equal(limit.limit.source,"completed_subject_turn");
  f.bridge.prompt(["A fresh business update."]);
  assert.equal(f.events.filter((v)=>v.type === "budget_limit").length,1);
});

// An omitted limit must remain uncapped across later business inputs.
test("an uncapped session accepts input after twenty-five subject turns", async (t) => {
  const f = await fixture(t, "claude_goal");
  assert.equal(f.bridge.turnLimit, undefined);
  f.bridge.turn = 25;
  f.bridge.prompt(["A fresh business update."]);
  assert.equal(f.events.filter((event) => event.type === "budget_limit").length, 0);
  assert.equal(f.bridge.turnLimitReached, undefined);
});
