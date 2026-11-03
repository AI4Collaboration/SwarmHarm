// Claude owns the loop. Only controller MCP tools can execute subject actions.
import { appendFileSync, cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { PassThrough } from "node:stream";
import { z } from "zod";

const PREFIX = /^mcp__(work|continuation)__/;
const SYSTEM_PROMPT = { type: "preset", preset: "claude_code" };
const copy = (value) => structuredClone(value);
class ProviderHold extends Error {}
const canonical = (value) => JSON.stringify(value, (_, entry) =>
  entry && typeof entry === "object" && !Array.isArray(entry)
    ? Object.fromEntries(Object.entries(entry).sort(([a], [b]) => a.localeCompare(b))) : entry);

export class ClaudeBridge {
  constructor(sdk, channel) {
    this.sdk = sdk;
    this.channel = channel;
    this.input = new PassThrough({ objectMode: true });
    this.sessionId = randomUUID();
    this.turn = 0;
    this.nativeIndex = 0;
    this.history = [];
    this.pendingInputs = [];
    this.calls = new Map();
    this.callWaiters = new Set();
    this.toolChain = Promise.resolve();
    this.servers = {};
    this.closed = false;
  }

  native(message) {
    const path = join("native", `${String(++this.nativeIndex).padStart(6, "0")}.json`);
    writeFileSync(join(this.config.folder, path), `${JSON.stringify(message)}\n`, { flag: "wx" });
    return path;
  }

  async init(config) {
    this.config = config;
    mkdirSync(join(config.folder, "native"), { recursive: true });
    // Claude Code can put cwd in model context. Keep operator run labels out.
    this.cwd = mkdtempSync(join(tmpdir(), "workspace-"));
    this.active = new Set(config.active_tools);
    // A configuration descriptor, never an invented copy of the SDK's prompt.
    this.history.push({ role: "system", content: JSON.stringify(SYSTEM_PROMPT) });
    this.servers.work = this.server("work", config.active_tools);
    this.session = this.sdk.query({
      prompt: this.input,
      options: {
        ...config.settings, cwd: this.cwd, model: config.model, effort: config.effort,
        pathToClaudeCodeExecutable: config.claude_binary,
        env: { ...process.env }, sessionId: this.sessionId,
        systemPrompt: copy(SYSTEM_PROMPT),
        includePartialMessages: true,
        extraArgs: { "replay-user-messages": null },
        allowedTools: ["mcp__work__*", "mcp__continuation__*"],
        canUseTool: async (name, args) => this.active.has(name.replace(PREFIX, "")) && PREFIX.test(name)
          ? { behavior: "allow", updatedInput: args }
          : { behavior: "deny", message: "Tool unavailable." },
        sessionStore: {
          append: async (key, entries) => {
            if (key.sessionId !== this.sessionId || key.subpath) throw new Error("Unexpected transcript identity");
            appendFileSync(join(config.folder, "session.jsonl"), entries.map((entry) => JSON.stringify(entry)).join("\n") + "\n");
          },
          load: async () => null,
        },
        sessionStoreFlush: "eager",
      },
    });
    await this.session.initializationResult();
    await this.syncTools();
    const commands = config.goal_mode === "claude_goal" ? await this.session.supportedCommands() : [];
    if (config.goal_mode === "claude_goal" && !commands.some((command) => command.name === "goal" && command.builtin)) {
      this.session.close();
      throw new Error("Claude Code does not expose native /goal for this session");
    }
    this.reading = this.consume().catch((error) => {
      if (error instanceof ProviderHold) this.session.close();
      if (!this.closed) this.channel.emit(error instanceof ProviderHold
        ? { type: "settled", turn: this.turn, aborted: false, text: "", error_message: error.message }
        : { type: "fatal", message: String(error.message ?? error) });
    });
    this.channel.emit({ type: "ready", session_id: this.sessionId,
      session_file: join(config.folder, "session.jsonl"),
      native_dir: join(config.folder, "native"),
      active_tools: [...this.active], system_prompt: copy(SYSTEM_PROMPT),
      commands, harness: "claude-code" });
  }

  server(name, names) {
    return this.sdk.createSdkMcpServer({ name, version: "1.0.0", tools: names.map((name) => {
      const definition = this.config.tools.find((tool) => tool.name === name);
      if (!definition) throw new Error(`Unregistered tool ${name}`);
      const schema = z.fromJSONSchema(definition.parameters);
      return this.sdk.tool(name, definition.description, schema.shape,
        (args) => this.execute(name, args));
    }) });
  }

  async syncTools() {
    const { errors } = await this.session.setMcpServers(this.servers);
    if (Object.keys(errors).length) throw new Error("Claude MCP registration failed");
  }

  async setTools(names) {
    if ([...this.active].some((name) => !names.includes(name))) throw new Error("Tools may only be added at the phase transition");
    const added = names.filter((name) => !this.active.has(name));
    if (!added.length) return;
    if (this.servers.continuation) throw new Error("Phase 2 tools were already installed");
    this.servers.continuation = this.server("continuation", added);
    this.active = new Set(names);
    await this.syncTools();
    this.native({ type: "controller_tools", active_tools: names, session_id: this.sessionId });
  }

  prompt(texts) {
    for (const text of texts) {
      const message = { type: "user", session_id: this.sessionId, uuid: randomUUID(),
        parent_tool_use_id: null, message: { role: "user", content: text } };
      this.native({ type: "controller_input", input: message });
      this.pendingInputs.push({ role: "user", content: text });
      this.input.write(message);
    }
  }

  start(message, source) {
    if (this.current) throw new Error("Overlapping Claude model messages");
    if (!(this.config.accepted_native_model_ids ?? [this.config.model]).includes(message.model)) throw new Error(`Claude returned model ${message.model}; expected ${this.config.model}`);
    this.history.push(...this.pendingInputs.splice(0));
    this.current = { id: message.id, turn: ++this.turn, blocks: [], usage: message.usage ?? {}, source };
    this.channel.emit({ type: "request", turn: this.turn, attempt: 1, payload: {
      record_kind: "controller_projection", model: this.config.model, native_model: message.model,
      system_prompt_config: copy(SYSTEM_PROMPT),
      input: copy(this.history), reasoning: { effort: this.config.effort },
      tools: this.config.tools.filter((tool) => this.active.has(tool.name)),
      sdk_message_id: message.id, native_record: source,
    } });
  }

  finish(source) {
    const current = this.current;
    if (!current) throw new Error("Claude message_stop without message_start");
    if (current.stopReason === "refusal") throw new ProviderHold("Claude refused the request");
    const output = [];
    for (const block of current.blocks) {
      if (block.type === "tool_use") {
        if (!PREFIX.test(block.name) || !this.active.has(block.name.replace(PREFIX, "")))
          throw new Error(`Unexpected Claude tool ${block.name}`);
        const call = { type: "function_call", call_id: block.id,
          name: block.name.replace(PREFIX, ""), arguments: JSON.stringify(block.input) };
        output.push(call);
        this.calls.set(block.id, { ...call, turn: current.turn, input: block.input, claimed: false });
      } else if (block.type === "text") {
        output.push({ type: "message", role: "assistant", content: [{ type: "output_text", text: block.text }] });
      } else if (block.type === "thinking" || block.type === "redacted_thinking") {
        // Thinking is preserved verbatim in native SDK records, outside Git.
        output.push({ type: "reasoning", id: `${current.id}:${output.length}` });
      } else throw new Error(`Unsupported Claude content block ${block.type}`);
    }
    const response = { record_kind: "controller_projection", id: current.id,
      model: this.config.model, status: "completed", output, usage: current.usage,
      native_record: source, native_start_record: current.source };
    current.calls = output.filter((item) => item.type === "function_call").length;
    current.completed = 0;
    this.turns ??= new Map();
    this.turns.set(current.turn, current);
    this.history.push(...copy(output));
    this.channel.emit({ type: "provider_response", turn: current.turn, attempt: 1,
      event: { type: "response.completed", response } });
    this.current = null;
    for (const wake of this.callWaiters) wake();
    if (!current.calls) this.turnEnd(current);
  }

  turnEnd(current) {
    this.channel.emit({ type: "turn_end", turn: current.turn, stop_reason: current.calls ? "toolUse" : "stop",
      error_message: null, tool_calls: current.calls,
      text: current.blocks.filter((block) => block.type === "text").map((block) => block.text).join("\n") });
    this.turns.delete(current.turn);
  }

  async execute(name, args) {
    // SDK tool requests can arrive before the consumer receives message_stop.
    let call;
    const find = () => [...this.calls.values()].find((entry) => !entry.claimed
      && entry.name === name && canonical(entry.input) === canonical(args));
    while (!(call = find())) {
      if (this.closed) throw new Error("Session closed");
      await new Promise((resolve, reject) => {
        const wake = () => { clearTimeout(timer); this.callWaiters.delete(wake); resolve(); };
        const timer = setTimeout(() => { this.callWaiters.delete(wake); reject(new Error("Tool has no native SDK call")); }, this.config.request_timeout_ms);
        this.callWaiters.add(wake);
      });
    }
    call.claimed = true;
    const run = this.toolChain.then(async () => {
      if (this.closed) throw new Error("Session closed");
      const reply = await this.channel.request({ type: "tool_call", id: call.call_id,
        call_id: call.call_id, name, turn: call.turn });
      if (reply.aborted) throw new Error("Operation aborted");
      this.history.push({ type: "function_call_output", call_id: call.call_id, output: reply.output });
      this.calls.delete(call.call_id);
      const current = this.turns.get(call.turn);
      if (++current.completed === current.calls) this.turnEnd(current);
      return { content: [{ type: "text", text: reply.output }] };
    });
    this.toolChain = run.catch(() => {});
    return run;
  }

  async consume() {
    // Iterate Query itself so disposal cannot wait behind a pending CLI read.
    // Same lifecycle pattern as T3 Code's Claude query runner.
    for await (const message of { [Symbol.asyncIterator]: () => this.session }) {
      const source = this.native(message);
      if (message.session_id && message.session_id !== this.sessionId) throw new Error("Claude changed session identity");
      // Tool heartbeats refer to their running tool, not a nested model context.
      if (message.type === "tool_progress") continue;
      if (message.parent_tool_use_id) throw new Error("Unexpected nested Claude session");
      if (message.type === "system" && message.subtype === "init") {
        if (message.tools.some((name) => !PREFIX.test(name) || !this.active.has(name.replace(PREFIX, ""))))
          throw new Error("Claude exposed unregistered tools");
      } else if (message.type === "stream_event") {
        const event = message.event;
        if (event.type === "message_start") this.start(event.message, source);
        else if (event.type === "message_delta" && this.current) {
          Object.assign(this.current.usage, event.usage ?? {});
          this.current.stopReason = event.delta?.stop_reason;
        }
        else if (event.type === "message_stop") this.finish(source);
      } else if (message.type === "assistant") {
        if (message.local_command_run) continue;
        if (message.error) throw new ProviderHold(`Claude assistant error: ${message.error}`);
        if (message.supersedes?.length) throw new ProviderHold("Claude superseded prior messages");
        if (!this.current || this.current.id !== message.message.id) throw new Error("Claude content has no matching stream start");
        this.current.blocks.push(...message.message.content);
      } else if (message.type === "result") {
        this.channel.emit({ type: "settled", turn: this.turn, aborted: false,
          text: message.result ?? "", error_message: message.is_error || message.subtype !== "success"
            ? `Claude result: ${message.subtype}` : null });
      } else if (message.type === "system" && ["compact_boundary", "mirror_error", "model_refusal_fallback", "model_refusal_no_fallback"].includes(message.subtype)) {
        throw new ProviderHold(`Claude context or provider hold: ${message.subtype}`);
      } else if (message.type === "rate_limit_event" && message.rate_limit_info?.status === "rejected") {
        throw new ProviderHold("Claude provider rate limit reached; session held");
      }
    }
    if (!this.closed) throw new Error("Claude session exited before global termination");
  }

  async close() {
    this.closed = true;
    this.input.end();
    for (const wake of this.callWaiters) wake();
    this.channel.cancelAll();
    try {
      this.session?.close();
      await this.reading;
    } finally {
      if (this.cwd) {
        cpSync(this.cwd, join(this.config.folder, "workspace"), { recursive: true });
        rmSync(this.cwd, { recursive: true });
        this.cwd = null;
      }
    }
  }
}
