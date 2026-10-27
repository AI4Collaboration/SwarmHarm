// One Pi SDK agent session driven by the SwarmHarm controller over JSON lines.
//
// stdin  (controller -> agent): init, prompt, set_tools, tool replies, abort, shutdown
// stdout (agent -> controller): ready, request, provider_response, tool_call, tool_result_error,
//                               turn_end, retry, settled, closed, fatal
//
// Pi owns the system prompt, request building, retries and session file. Every model-visible
// tool is executed by the controller, which keeps the offline workstation and shared state.
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import {
	createAgentSession,
	DefaultResourceLoader,
	ModelRuntime,
	SessionManager,
	SettingsManager,
} from "@earendil-works/pi-coding-agent";

const PI_PREAMBLE =
	"You are an expert coding assistant operating inside pi, a coding agent harness. You help users by reading files, executing commands, editing code, and writing new files.";
const DOCS_SECTION = /\n*<docs>\n[\s\S]*?\n<\/docs>/;
const CWD_SECTION = /<cwd>\n[^\n]*\n<\/cwd>/;
const PROVIDER = "swarmharm";
const RESPONSE_EVENTS = new Set(["response.completed", "response.failed", "response.incomplete", "error"]);

function emit(value) {
	process.stdout.write(`${JSON.stringify(value)}\n`);
}

function fatal(error) {
	emit({ type: "fatal", message: String(error?.stack ?? error) });
	process.exit(1);
}

// Pi's structured prompt minus its harness preamble and host documentation pointers.
export function neutralSystemPrompt(rendered, preamble, workspace) {
	if (!rendered.startsWith(PI_PREAMBLE)) throw new Error("Pi system prompt preamble changed; review the pinned version");
	let value = preamble + rendered.slice(PI_PREAMBLE.length);
	if (!DOCS_SECTION.test(value)) throw new Error("Pi system prompt docs section changed; review the pinned version");
	value = value.replace(DOCS_SECTION, "");
	if (!CWD_SECTION.test(value)) throw new Error("Pi system prompt cwd section changed; review the pinned version");
	return value.replace(CWD_SECTION, `<cwd>\n${workspace}\n</cwd>`);
}

function firstSentence(text) {
	const match = /^[\s\S]*?[.!?](?=\s|$)/.exec(text.trim());
	return (match ? match[0] : text).replace(/\s+/g, " ").trim();
}

class Channel {
	constructor() {
		this.waiters = new Map();
		this.handlers = {};
		this.buffer = "";
		process.stdin.setEncoding("utf8");
		process.stdin.on("data", (chunk) => this.feed(chunk));
		process.stdin.on("end", () => process.exit(0));
	}
	feed(chunk) {
		this.buffer += chunk;
		let index = this.buffer.indexOf("\n");
		while (index >= 0) {
			const line = this.buffer.slice(0, index);
			this.buffer = this.buffer.slice(index + 1);
			if (line.trim()) this.dispatch(JSON.parse(line));
			index = this.buffer.indexOf("\n");
		}
	}
	dispatch(message) {
		const key = message.reply_to;
		if (key !== undefined && this.waiters.has(key)) {
			const resolve = this.waiters.get(key);
			this.waiters.delete(key);
			resolve(message);
			return;
		}
		const handler = this.handlers[message.type];
		if (!handler) return fatal(new Error(`Unknown controller message ${message.type}`));
		Promise.resolve(handler(message)).catch(fatal);
	}
	request(value) {
		return new Promise((resolve) => {
			this.waiters.set(value.id, resolve);
			emit(value);
		});
	}
	cancelAll(reply) {
		for (const [key, resolve] of this.waiters) resolve({ reply_to: key, ...reply });
		this.waiters.clear();
	}
}

const channel = new Channel();
let session;
let config;
let turn = 0;
let requestIndex = 0;
let requestId = 0;
// Pi retries a failed request as a new turn; keep it as another attempt of the same request.
let retryPending = false;

function nextId(prefix) {
	requestId += 1;
	return `${prefix}-${requestId}`;
}

function toolDefinition(tool) {
	return {
		name: tool.name,
		label: tool.name,
		description: tool.description,
		promptSnippet: firstSentence(tool.description),
		parameters: tool.parameters,
		constrainedSampling: tool.strict ? { type: "json_schema", strict: "require" } : false,
		executionMode: "sequential",
		async execute(toolCallId) {
			const reply = await channel.request({ type: "tool_call", id: nextId("tool"), turn, call_id: toolCallId, name: tool.name });
			if (reply.aborted) throw new Error("Operation aborted");
			return { content: [{ type: "text", text: reply.output }], details: {} };
		},
	};
}

function controllerExtension(pi) {
	pi.on("before_agent_start", (event) => ({
		systemPrompt: neutralSystemPrompt(event.systemPrompt, config.preamble, config.workspace),
	}));
	pi.on("turn_start", () => {
		if (retryPending) {
			retryPending = false;
			return;
		}
		turn += 1;
		requestIndex = 0;
	});
	pi.on("before_provider_request", (event) => {
		requestIndex += 1;
		emit({ type: "request", turn, attempt: requestIndex, payload: event.payload });
		return undefined;
	});
	pi.on("provider_stream_event", (event) => {
		const data = event.data;
		if (data && RESPONSE_EVENTS.has(data.type)) emit({ type: "provider_response", turn, attempt: requestIndex, event: data });
	});
	pi.on("tool_execution_end", (event) => {
		if (event.isError) emit({ type: "tool_result_error", turn, call_id: event.toolCallId, name: event.toolName, result: event.result });
	});
	// Observed only; Pi's loop continues without waiting for the controller.
	pi.on("turn_end", (event) => {
		const message = event.message;
		emit({
			type: "turn_end",
			turn,
			stop_reason: message.stopReason,
			error_message: message.errorMessage ?? null,
			response_id: message.responseId ?? null,
			tool_calls: event.toolResults.length,
			text: message.content.filter((block) => block.type === "text").map((block) => block.text).join("\n"),
		});
	});
	pi.on("agent_settled", (event) => {
		const last = session?.messages.findLast((message) => message.role === "assistant");
		emit({
			type: "settled",
			turn,
			aborted: event.aborted,
			text: session?.getLastAssistantText() ?? "",
			// Set only when the run ended on an error that outlasted Pi's retries.
			error_message: last?.stopReason === "error" ? (last.errorMessage ?? "error") : null,
		});
	});
}

// Controller tools follow the registered phase; tools from a registered extension file stay
// active. Pi's built-in tools act on the host, so none may ever become active.
function activateTools(controllerTools) {
	const own = new Set(config.tools.map((tool) => tool.name));
	const fromExtension = (tool) => config.extension_paths.some((path) => tool.sourceInfo?.path === path);
	const extensionTools = session.getAllTools().filter((tool) => !own.has(tool.name) && fromExtension(tool));
	const names = [...controllerTools, ...extensionTools.map((tool) => tool.name)];
	session.setActiveToolsByName(names);
	const unexpected = session.getActiveToolNames().filter((name) => !names.includes(name));
	if (unexpected.length) throw new Error(`Unregistered tools became active: ${unexpected.join(", ")}`);
	for (const tool of session.getAllTools()) {
		if (session.getActiveToolNames().includes(tool.name) && !own.has(tool.name) && !fromExtension(tool)) {
			throw new Error(`Host tool ${tool.name} is active`);
		}
	}
}

channel.handlers.init = async (message) => {
	config = message;
	mkdirSync(config.agent_dir, { recursive: true });
	mkdirSync(config.session_dir, { recursive: true });
	mkdirSync(config.empty_cwd, { recursive: true });
	writeFileSync(join(config.agent_dir, "models.json"), `${JSON.stringify({
		providers: {
			[PROVIDER]: {
				baseUrl: config.api_base,
				api: "openai-responses",
				apiKey: "$SWARMHARM_MODEL_API_KEY",
				compat: config.compat,
				models: [{
					id: config.model,
					reasoning: true,
					contextWindow: config.context_window,
					maxTokens: config.max_output_tokens,
					cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
				}],
			},
		},
	}, null, 2)}\n`);
	const modelRuntime = await ModelRuntime.create({
		authPath: join(config.agent_dir, "auth.json"),
		modelsPath: join(config.agent_dir, "models.json"),
		allowModelNetwork: false,
		refreshOnCreate: false,
	});
	const model = modelRuntime.getModel(PROVIDER, config.model);
	if (!model) throw new Error(`Model ${config.model} is not configured`);
	const settingsManager = SettingsManager.inMemory(config.settings);
	const resourceLoader = new DefaultResourceLoader({
		cwd: config.empty_cwd,
		agentDir: config.agent_dir,
		settingsManager,
		noSkills: true,
		noPromptTemplates: true,
		noThemes: true,
		noContextFiles: true,
		appendSystemPrompt: config.append_system_prompt,
		additionalExtensionPaths: config.extension_paths,
		extensionFactories: [{ name: "swarmharm-controller", factory: controllerExtension }],
	});
	await resourceLoader.reload();
	({ session } = await createAgentSession({
		cwd: config.empty_cwd,
		agentDir: config.agent_dir,
		modelRuntime,
		model,
		thinkingLevel: config.thinking_level,
		noTools: "builtin",
		customTools: config.tools.map(toolDefinition),
		resourceLoader,
		settingsManager,
		sessionManager: SessionManager.create(config.empty_cwd, config.session_dir),
	}));
	activateTools(config.active_tools);
	session.subscribe((event) => {
		if (event.type !== "auto_retry_start") return;
		retryPending = true;
		emit({ type: "retry", turn, attempt: event.attempt, max_attempts: event.maxAttempts, delay_ms: event.delayMs, error_message: event.errorMessage });
	});
	await session.bindExtensions({
		onError: (error) => emit({ type: "extension_error", error: String(error?.error ?? error?.message ?? error) }),
	});
	emit({
		type: "ready",
		session_file: session.sessionManager.getSessionFile() ?? null,
		session_id: session.sessionManager.getSessionId(),
		active_tools: session.getActiveToolNames(),
		system_prompt: neutralSystemPrompt(session.systemPrompt, config.preamble, config.workspace),
		commands: session.extensionRunner.getRegisteredCommands().map((command) => command.name),
	});
};

// Idle: the first text starts a run. During a run: Pi queues each text for its next turn.
channel.handlers.prompt = async (message) => {
	const [first, ...rest] = message.texts;
	if (session.isStreaming) {
		for (const text of message.texts) await session.steer(text);
		return;
	}
	const run = session.prompt(first);
	for (const text of rest) await session.steer(text);
	await run;
};

channel.handlers.set_tools = async (message) => {
	activateTools(message.tools);
};

channel.handlers.abort = async () => {
	channel.cancelAll({ aborted: true });
	await session.abort();
};

channel.handlers.shutdown = async () => {
	channel.cancelAll({ aborted: true });
	if (session) {
		// A pending extension continuation must not hold the context open past global termination.
		await Promise.race([session.abort(), new Promise((resolve) => setTimeout(resolve, 5000))]);
		session.dispose();
	}
	emit({ type: "closed" });
	process.exit(0);
};

process.on("uncaughtException", fatal);
process.on("unhandledRejection", fatal);
