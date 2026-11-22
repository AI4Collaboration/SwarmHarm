// Claude owns the loop. Only controller MCP tools can execute subject actions.
import { appendFileSync, cpSync, mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
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

// Keep the disposable record stable while a controller tool observes/edits it.
// Every SDK append is durably journaled first, even when its visible write waits.
export class SessionRecordStore {
  constructor(folder, sessionId) {
    this.folder = folder;
    this.sessionId = sessionId;
    this.pending = [];
    this.busy = false;
    this.sequence = 0;
    mkdirSync(join(folder, "native-store"), { recursive: true });
  }

  append(key, entries) {
    if (key.sessionId !== this.sessionId || key.subpath)
      throw new Error("Unexpected transcript identity");
    const bytes = entries.map((entry) => JSON.stringify(entry)).join("\n") + "\n";
    writeFileSync(join(this.folder, "native-store", `${String(++this.sequence).padStart(6, "0")}.json`),
      JSON.stringify({ key, entries }) + "\n", { flag: "wx" });
    this.pending.push(bytes);
    if (!this.busy) this.flush();
  }

  flush() {
    if (this.pending.length) {
      appendFileSync(join(this.folder, "session.jsonl"), this.pending.join(""));
      this.pending = [];
    }
  }

  async duringTool(action) {
    if (this.busy) throw new Error("Overlapping record transaction");
    this.flush();
    this.busy = true;
    try { return await action(); }
    finally {
      this.busy = false;
      this.flush();
    }
  }
}

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
    this.deliveredInputs = [];
    this.calls = new Map();
    this.earlyToolErrors = [];
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
    this.turnLimit = config.settings.maxTurns;
    if (this.turnLimit !== undefined && (!Number.isSafeInteger(this.turnLimit) || this.turnLimit < 1))
      throw new Error("maxTurns must be a positive integer");
    this.systemPrompt = copy(config.system_prompt ?? SYSTEM_PROMPT);
    mkdirSync(join(config.folder, "native"), { recursive: true });
    // Claude Code can put cwd in model context. Keep operator run labels out.
    this.cwd = realpathSync(mkdtempSync("/tmp/workspace-"));
    this.recordStore = new SessionRecordStore(config.folder, this.sessionId);
    this.active = new Set(config.active_tools);
    // A configuration descriptor, never an invented copy of the SDK's prompt.
    this.history.push({ role: "system", content: JSON.stringify(this.systemPrompt) });
    this.servers.work = this.server("work", config.active_tools);
    const limitHooks = {};
    if (this.turnLimit !== undefined) for (const name of ["Stop", "PostToolBatch", "UserPromptSubmit"]) {
      limitHooks[name] = [{ hooks: [async (input) => {
        if (this.turn < this.turnLimit && !this.turnLimitReached) return {};
        this.limitReached(input.hook_event_name ?? name);
        return { continue: false, stopReason: "Registered actor turn budget exhausted." };
      }] }];
    }
    this.session = this.sdk.query({
      prompt: this.input,
      options: {
        ...config.settings, cwd: this.cwd, model: config.model, effort: config.effort,
        ...(this.turnLimit === undefined ? {} : { hooks: limitHooks }),
        pathToClaudeCodeExecutable: config.claude_binary,
        env: { ...process.env }, sessionId: this.sessionId,
        systemPrompt: copy(this.systemPrompt),
        includePartialMessages: true,
        extraArgs: { "replay-user-messages": null },
        allowedTools: ["mcp__work__*", "mcp__continuation__*"],
        canUseTool: async (name, args) => this.active.has(name.replace(PREFIX, "")) && PREFIX.test(name)
          ? { behavior: "allow", updatedInput: args }
          : { behavior: "deny", message: "Tool unavailable." },
        sessionStore: {
          append: async (key, entries) => this.recordStore.append(key, entries),
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
    this.channel.emit({ type: "ready", session_id: this.sessionId, cwd: this.cwd,
      session_file: join(config.folder, "session.jsonl"),
      native_dir: join(config.folder, "native"),
      active_tools: [...this.active], system_prompt: copy(this.systemPrompt),
      commands, harness: "claude-code" });
  }

  server(name, names) {
    return this.sdk.createSdkMcpServer({ name, version: "1.0.0", tools: names.map((name) => {
      const definition = this.config.tools.find((tool) => tool.name === name);
      if (!definition) throw new Error(`Unregistered tool ${name}`);
      const schema = z.fromJSONSchema(definition.parameters);
      const tool = this.sdk.tool(name, definition.description, schema.shape,
        (args) => this.execute(name, args));
      // Explicit supported MCP limit preserves ordinary large workstation reads
      // inline instead of pointing the model at an inaccessible host temp file.
      tool._meta = { ...tool._meta, "anthropic/maxResultSizeChars": 500000 };
      return tool;
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
    if (this.turnLimitReached || (this.turnLimit !== undefined && this.turn >= this.turnLimit)) {
      this.limitReached("controller_input");
      return;
    }
    // One controller delegation must reach one model context atomically. Two
    // writes race with the CLI consuming the first before the task arrives.
    // Native /goal commands retain their separate command semantics.
    const groups = this.config.input_delivery === "atomic-sdk-replay-v1" && texts.length ? [texts.join("\n\n")] : texts;
    for (const text of groups) {
      const message = { type: "user", session_id: this.sessionId, uuid: randomUUID(),
        parent_tool_use_id: null, message: { role: "user", content: text } };
      this.native({ type: "controller_input", input: message });
      this.pendingInputs.push({ uuid: message.uuid, role: "user", content: text });
      this.input.write(message);
    }
  }

  limitReached(source, nativeResult = null) {
    if (this.turnLimitReached) return;
    this.turnLimitReached = true;
    const record = { type: "registered_actor_turn_limit", source,
      limit: this.turnLimit, subject_turns: this.turn,
      scope: "persistent_actor_session", native_result: nativeResult };
    writeFileSync(join(this.config.folder, "actor-turn-limit.json"), `${JSON.stringify(record)}\n`, { flag: "wx" });
    this.channel.emit({ type: "budget_limit", turn: this.turn, limit: record });
  }

  start(message, source) {
    if (this.current) throw new Error("Overlapping Claude model messages");
    if (!(this.config.accepted_native_model_ids ?? [this.config.model]).includes(message.model)) throw new Error(`Claude returned model ${message.model}; expected ${this.config.model}`);
    if (this.config.input_delivery !== "atomic-sdk-replay-v1") {
      this.history.push(...this.pendingInputs.splice(0).map(({ role, content }) => ({ role, content })));
    } else if (this.turn === 0 && this.pendingInputs.length && !this.deliveredInputs.length) {
      throw new Error("Initial Claude input has no SDK delivery before inference");
    }
    this.current = { id: message.id, turn: ++this.turn, blocks: [], usage: message.usage ?? {}, source };
    this.channel.emit({ type: "request", turn: this.turn, attempt: 1, payload: {
      record_kind: "controller_projection", model: this.config.model, native_model: message.model,
      system_prompt_config: copy(this.systemPrompt),
      input: copy(this.history), reasoning: { effort: this.config.effort },
      tools: this.config.tools.filter((tool) => this.active.has(tool.name)),
      sdk_message_id: message.id, native_record: source,
      ...(this.config.input_delivery === "atomic-sdk-replay-v1" ? { input_delivery: "atomic-sdk-replay-v1",
        delivered_input_records: copy(this.deliveredInputs) } : {}),
    } });
  }

  finish(source) {
    const current = this.current;
    if (!current) throw new Error("Claude message_stop without message_start");
    if (current.stopReason === "refusal") throw new ProviderHold("Claude refused the request");
    const output = [];
    for (const block of current.blocks) {
      if (block.type === "tool_use") {
        // Preserve attempted calls, including hallucinated names. The SDK owns
        // rejection; an unavailable tool is never installed or dispatched here.
        const call = { type: "function_call", call_id: block.id,
          name: block.name.replace(PREFIX, ""), native_name: block.name,
          arguments: JSON.stringify(block.input) };
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
    for (const [message, record] of this.earlyToolErrors.splice(0))
      this.rejectedResults(message, record);
    for (const wake of this.callWaiters) wake();
    if (!current.calls) this.turnEnd(current);
  }

  turnEnd(current) {
    this.channel.emit({ type: "turn_end", turn: current.turn, stop_reason: current.calls ? "toolUse" : "stop",
      error_message: null, tool_calls: current.calls,
      text: current.blocks.filter((block) => block.type === "text").map((block) => block.text).join("\n") });
    this.turns.delete(current.turn);
    if (this.turnLimit !== undefined && this.turn >= this.turnLimit)
      this.limitReached("completed_subject_turn");
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
      const reply = await this.recordStore.duringTool(() =>
        this.channel.request({ type: "tool_call", id: call.call_id,
          call_id: call.call_id, name, turn: call.turn }));
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

  rejectedResults(message, source) {
    if (!Array.isArray(message.message?.content)) return;
    for (const block of message.message.content) {
      if (block.type !== "tool_result") continue;
      const call = this.calls.get(block.tool_use_id);
      // Successful controller calls were completed by execute(). Schema and
      // unknown-name errors never enter that handler; await their real SDK result.
      if (!call) {
        // Claude Code may reject an unknown name before streaming message_stop.
        if (block.is_error === true && this.current)
          this.earlyToolErrors.push([{ message: { content: [block] } }, source]);
        continue;
      }
      if (call.claimed) continue;
      if (block.is_error !== true) throw new Error("Unexecuted Claude tool returned success");
      const output = typeof block.content === "string" ? block.content
        : block.content.map((part) => part.text ?? "").join("\n");
      this.history.push({ type: "function_call_output", call_id: call.call_id, output });
      this.calls.delete(call.call_id);
      this.channel.emit({ type: "tool_result_error", call_id: call.call_id,
        name: call.name, turn: call.turn, error: output, native_record: source });
      const current = this.turns.get(call.turn);
      if (++current.completed === current.calls) this.turnEnd(current);
    }
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
        if (message.error || message.is_api_error_message) {
          const detail = (message.message?.content ?? []).filter((part) => part.type === "text")
            .map((part) => part.text).join("\n");
          throw new ProviderHold(`Claude assistant error: ${message.error ?? "api_error"}; native=${source}${detail ? `; ${detail}` : ""}`);
        }
        if (message.supersedes?.length) throw new ProviderHold("Claude superseded prior messages");
        if (!this.current || this.current.id !== message.message.id) throw new Error("Claude content has no matching stream start");
        this.current.blocks.push(...message.message.content);
      } else if (message.type === "user") {
        if (this.config.input_delivery === "atomic-sdk-replay-v1") {
          const index = this.pendingInputs.findIndex((input) => input.uuid === message.uuid);
          if (index !== -1) {
            const input = this.pendingInputs[index];
            if (canonical(message.message) !== canonical({ role: input.role, content: input.content }))
              throw new Error("Claude SDK input replay differs from controller delegation");
            this.pendingInputs.splice(index, 1);
            this.history.push({ role: input.role, content: input.content });
            this.deliveredInputs.push({ uuid: input.uuid, native_record: source });
          }
        }
        this.rejectedResults(message, source);
      } else if (message.type === "result") {
        if (message.subtype === "error_max_turns") {
          this.limitReached("sdk_max_turns", message);
          continue;
        }
        if (this.turnLimitReached) continue;
        this.channel.emit({ type: "settled", turn: this.turn, aborted: false,
          text: message.result ?? "", error_message: message.is_error || message.subtype !== "success"
            ? `Claude result: ${message.subtype}` : null });
      } else if (message.type === "system" && ["compact_boundary", "mirror_error", "model_refusal_fallback", "model_refusal_no_fallback"].includes(message.subtype)) {
        throw new ProviderHold(`Claude context or provider hold: ${message.subtype}`);
      } else if (message.type === "rate_limit_event" && message.rate_limit_info?.status === "rejected") {
        throw new ProviderHold("Claude provider rate limit reached; session held");
      }
    }
    if (!this.closed && !this.turnLimitReached) throw new Error("Claude session exited before global termination");
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
      await this.toolChain;
      this.recordStore?.flush();
      if (this.cwd) {
        cpSync(this.cwd, join(this.config.folder, "workspace"), { recursive: true });
        rmSync(this.cwd, { recursive: true });
        this.cwd = null;
      }
    }
  }
}
