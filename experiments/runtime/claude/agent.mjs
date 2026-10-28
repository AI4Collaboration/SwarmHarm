// JSON-lines entrypoint; replies remain live while ordered commands are applied.
import * as sdk from "@anthropic-ai/claude-agent-sdk";
import { createInterface } from "node:readline";
import { ClaudeBridge } from "./bridge.mjs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

export function serve(runtime = sdk) {
const waiters = new Map();
const emit = (value) => process.stdout.write(`${JSON.stringify(value)}\n`);
const channel = {
  emit,
  request: (value) => new Promise((resolve) => { waiters.set(value.id, resolve); emit(value); }),
  cancelAll: () => { for (const resolve of waiters.values()) resolve({ aborted: true }); waiters.clear(); },
};
const bridge = new ClaudeBridge(runtime, channel);
let commands = Promise.resolve();
const fatal = (error) => { emit({ type: "fatal", message: String(error.message ?? error) }); bridge.close().finally(() => process.exit(1)); };
const input = createInterface({ input: process.stdin });
input.on("line", (line) => {
  try {
    const message = JSON.parse(line);
    if (message.reply_to !== undefined) {
      const resolve = waiters.get(message.reply_to);
      if (!resolve) throw new Error("Unexpected controller tool reply");
      waiters.delete(message.reply_to); resolve(message); return;
    }
    if (message.type === "shutdown" || message.type === "abort") {
      bridge.close().then(() => { emit({ type: "closed" }); process.exit(0); }).catch(fatal);
      return;
    }
    commands = commands.then(async () => {
      if (message.type === "init") await bridge.init(message);
      else if (message.type === "set_tools") await bridge.setTools(message.tools);
      else if (message.type === "prompt") bridge.prompt(message.texts);
      else throw new Error(`Unknown controller message ${message.type}`);
    }).catch(fatal);
  } catch (error) { fatal(error); }
});
input.on("close", () => bridge.close().finally(() => process.exit(0)));
process.on("uncaughtException", fatal);
process.on("unhandledRejection", fatal);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) serve();
