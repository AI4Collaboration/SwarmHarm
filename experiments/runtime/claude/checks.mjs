import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setImmediate } from "node:timers/promises";
import { ClaudeBridge } from "./bridge.mjs";

// Scripted SDK frames test fail-closed behavior. The Python integration check
// separately exercises the real SDK and CLI against localhost.
async function fixture(t, goalMode = "off") {
  const folder = mkdtempSync(join(tmpdir(), "swarmharm-claude-guard-"));
  const events = [];
  const frames = [];
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
    active_tools: [], tools: [], settings: { tools: [] }, request_timeout_ms: 100, goal_mode: goalMode });
  t.after(async () => { await bridge.close(); rmSync(folder, { recursive: true }); });
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

test("built-in host tools are rejected at session initialization", async (t) => {
  const f = await fixture(t);
  await f.feed({ type: "system", subtype: "init", tools: ["Bash", "Read"] });
  assert.equal(f.events.at(-1).type, "fatal");
  assert.match(f.events.at(-1).message, /unregistered tools/);
});

test("a Phase 2 tool cannot run before it is installed", async (t) => {
  const f = await fixture(t);
  await f.feed(
    { type: "stream_event", event: { type: "message_start", message: { id: "message-1", model: "claude-fixture-1" } } },
    { type: "assistant", message: { id: "message-1", content: [
      { type: "tool_use", id: "call-1", name: "mcp__continuation__book_replica_upgrade", input: {} }] } },
    { type: "stream_event", event: { type: "message_stop" } },
  );
  assert.equal(f.events.at(-1).type, "fatal");
  assert.match(f.events.at(-1).message, /Unexpected Claude tool/);
});

test("subscription exhaustion is a hold with no fallback query", async (t) => {
  const f = await fixture(t);
  await f.feed({ type: "rate_limit_event", rate_limit_info: { status: "rejected" } });
  assert.equal(f.events.at(-1).type, "settled");
  assert.match(f.events.at(-1).error_message, /subscription limit reached/);
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
