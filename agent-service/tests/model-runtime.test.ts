import test from "node:test";
import assert from "node:assert/strict";
import { resolveAgentModelRuntime } from "../src/model-runtime.js";

test("Ollama is the default model provider", () => {
  assert.deepEqual(resolveAgentModelRuntime({}), {
    provider: "ollama",
    model: "qwen2.5:1.5b",
    baseURL: "http://ollama:11434/v1",
    timeoutMs: 90000,
  });
});

test("Ollama runtime accepts bounded local overrides", () => {
  assert.deepEqual(resolveAgentModelRuntime({
    V79_AGENT_MODEL_PROVIDER: "ollama",
    OLLAMA_AGENT_MODEL: "qwen2.5:3b",
    OLLAMA_OPENAI_BASE_URL: "http://ollama:11434/v1/",
    OLLAMA_REQUEST_TIMEOUT_MS: "45000",
  }), {
    provider: "ollama",
    model: "qwen2.5:3b",
    baseURL: "http://ollama:11434/v1",
    timeoutMs: 45000,
  });
});

test("OpenAI remains an explicit optional provider", () => {
  assert.deepEqual(resolveAgentModelRuntime({
    V79_AGENT_MODEL_PROVIDER: "openai",
    OPENAI_AGENT_MODEL: "gpt-5.6-sol",
  }), {
    provider: "openai",
    model: "gpt-5.6-sol",
  });
});