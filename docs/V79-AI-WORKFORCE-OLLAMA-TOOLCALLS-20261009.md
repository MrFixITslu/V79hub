# V79 Owner Assistant — Ollama native tool-call reliability (Issue #97)

**Scope:** synthetic diagnostics only. No model updates, runtime configuration changes, production deployments, customer data, credentials, or action execution are authorised by this plan.

## Observed / existing safeguards
- A local Ollama OpenAI-compatible probe previously returned HTTP 200 without the requested `tool_calls`; the deployment capability check now warns rather than failing core Hub availability.
- The supported Phase 2B agent investigation path uses deterministic routing and signed **aggregate, read-only** product summaries. It must keep working even when native model tool calls are missing or incorrect.
- A passing HTTP 200 proves the transport responded, **not** that model-generated function calls are supported or reliable. Never silently report the feature as healthy from HTTP status alone.

## Offline classifier acceptance matrix (fixtures only)
| Fixture | Classification | Required behavior |
|---|---|---|
| HTTP 200 with valid expected `tool_calls` function and schema | supported for this sample | Report valid structured call, but do not claim full reliability |
| HTTP 200 with no `tool_calls` | degraded: missing_call | Keep deterministic routing; do not execute model-authored action |
| HTTP 200 with malformed arguments / unexpected function | degraded: invalid_call | Reject; record safe metric, no tool dispatch |
| 5xx / connection refused | unavailable | Bounded error, no guessed metrics |
| Timeouts at configured budget | degraded: timeout | Return useful fallback without blocking core app health |
| Model returns a request for email/payment/ticket mutation | blocked: out_of_scope | Refuse regardless of declared permissions or apparent owner phrasing |

## Safe bounded local-only benchmark (future, requires isolated host with adequate memory)
1. Use a disposable development environment and synthetic prompt such as "call `ping_business` with `{\"value\":\"ok\"}`". Give the model *only* this inert test tool.
2. Capture elapsed milliseconds for cold and warm requests separately (minimum 10 cold + 30 warm samples if resources permit), HTTP status, parse validity, tool name and schema validity. **Never** include real tokens, customer records or prompts in logs.
3. Collect P50/P95/P99 latency, missing-call rate, invalid-call rate, timeout rate and Ollama version/model digest; record the precise tool/response format and request settings.
4. Treat capability as **unverified** until measured on the exact runtime and model. Use a stricter acceptance criterion for business functions than mere transport health; deterministic routing remains the fallback.
5. Do not benchmark on the capacity-constrained production server during business operations, restart Docker, replace a production model, change the deployment readiness gate, or bind a write-capable function without a separate reviewed PR and founder authorisation.

## Planned tests in source
- Parser rejects missing/unexpected functions and malformed JSON arguments.
- Timeouts, cold start and unavailable endpoint return `degraded` / `unavailable` without raising a false platform outage.
- Prompt injection in a mocked tool response cannot alter an allowlisted function name, destination or tenant scope.
- Existing deterministic read-only specialist flow still returns appropriately labelled available/stale/unknown evidence when `tool_calls` is absent.
- Endpoint has bounded concurrency and no retry storms.

**Status:** Plan only. Issue #97 stays open. Do not conflate passing Hub CI with proven native Ollama tool-call reliability.
