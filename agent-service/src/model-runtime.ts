import { OpenAIProvider, setDefaultModelProvider, setTracingDisabled } from "@openai/agents";
import { OpenAI } from "openai";

export type AgentModelProvider = "ollama" | "openai";

export type AgentModelRuntime = {
  provider: AgentModelProvider;
  model: string;
  baseURL?: string;
  timeoutMs?: number;
};

function positiveInteger(value: string | undefined, fallback: number) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function parseKeepAlive(value: string | undefined): string | number {
  const normalized = String(value || "-1").trim();
  if (/^-?\d+$/.test(normalized)) return Number(normalized);
  return normalized || -1;
}

export function resolveAgentModelRuntime(env: NodeJS.ProcessEnv = process.env): AgentModelRuntime {
  const provider = String(env.V79_AGENT_MODEL_PROVIDER || "ollama").trim().toLowerCase();
  if (provider === "ollama") {
    return {
      provider: "ollama",
      model: String(env.OLLAMA_AGENT_MODEL || "qwen2.5:1.5b").trim(),
      baseURL: String(env.OLLAMA_OPENAI_BASE_URL || "http://ollama:11434/v1").trim().replace(/\/+$/, ""),
      timeoutMs: positiveInteger(env.OLLAMA_REQUEST_TIMEOUT_MS, 90_000),
    };
  }
  if (provider === "openai") {
    return {
      provider: "openai",
      model: String(env.OPENAI_AGENT_MODEL || "gpt-5.6-sol").trim(),
    };
  }
  throw new Error("V79_AGENT_MODEL_PROVIDER must be either 'ollama' or 'openai'.");
}

export function configureAgentModelRuntime(env: NodeJS.ProcessEnv = process.env) {
  const runtime = resolveAgentModelRuntime(env);

  if (runtime.provider === "ollama") {
    const client = new OpenAI({
      apiKey: String(env.OLLAMA_API_KEY || "ollama-local"),
      baseURL: runtime.baseURL,
      timeout: runtime.timeoutMs,
      maxRetries: 0,
    });
    setDefaultModelProvider(new OpenAIProvider({
      openAIClient: client,
      useResponses: false,
      strictFeatureValidation: false,
    }));
    setTracingDisabled(true);
  }

  return runtime;
}

export async function prewarmAgentModel(
  runtime: AgentModelRuntime = agentModelRuntime,
  env: NodeJS.ProcessEnv = process.env,
) {
  if (runtime.provider !== "ollama" || !runtime.baseURL) return { skipped: true as const };

  const nativeBaseURL = runtime.baseURL.replace(/\/v1$/i, "");
  const controller = new AbortController();
  const timeoutMs = positiveInteger(env.OLLAMA_PREWARM_TIMEOUT_MS, 120_000);
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${nativeBaseURL}/api/generate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model: runtime.model,
        prompt: "",
        stream: false,
        keep_alive: parseKeepAlive(env.OLLAMA_KEEP_ALIVE),
      }),
      signal: controller.signal,
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Ollama prewarm failed with HTTP ${response.status}: ${detail.slice(0, 300)}`);
    }
    await response.json().catch(() => null);
    return { skipped: false as const };
  } finally {
    clearTimeout(timeout);
  }
}

export const agentModelRuntime = configureAgentModelRuntime();
export const agentModelRuntime = configureAgentModelRuntime();
