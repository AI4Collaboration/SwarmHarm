// Subscription CLI model capabilities, without submitting any inference prompt.
import { query } from "@anthropic-ai/claude-agent-sdk";

const [model, effort, binary] = process.argv.slice(2);
const input = { async *[Symbol.asyncIterator]() { await new Promise(() => {}); } };
const session = query({ prompt: input, options: {
  model, effort, pathToClaudeCodeExecutable: binary, env: { ...process.env },
  tools: [], settingSources: [], strictMcpConfig: true, persistSession: false,
} });
try {
  await session.initializationResult();
  const models = (await session.supportedModels()).map(({
    value, resolvedModel, displayName, supportsEffort, supportedEffortLevels,
  }) => ({ value, resolvedModel, displayName, supportsEffort, supportedEffortLevels }));
  const matching = models.filter((row) => row.value === model || row.resolvedModel === model);
  const found = matching.some((row) => row.supportsEffort && row.supportedEffortLevels?.includes(effort));
  process.stdout.write(`${JSON.stringify({ model, effort, model_and_effort_found: found, models, inference_calls: 0 })}\n`);
} finally { session.close(); }
