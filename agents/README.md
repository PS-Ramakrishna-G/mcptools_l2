# Agent Prompt Suite

These files separate stable instructions from per-request data:

- `systemprompt.md` defines the assistant persona, capabilities, answer rules, and trust boundaries.
- `guardrails.md` defines supported scope, exclusions, fallback behavior, and privacy/safety constraints.
- `router_prompt.md` classifies the raw request into known tool names and extracts optional parameters using local Qwen JSON output.
- `user_prompt.md` supplies the user's request, classifier decisions, banned tools, and MCP results to the final-answer model.

## Runtime Flow

1. `orchastrator.agent_fun.process_user_query()` writes a request ID and `request_received` log event.
2. `routing_engine.decision.classify_user_intent()` reads `router_prompt.md` and calls local Qwen through `llm_client.classify_json()` with JSON mode.
3. The classifier's tool names are checked against the known tool allowlist. Coordinates, book topics, and dog-breed paths are validated. Explicit exclusions from both the Qwen result and the existing guardrail parser are merged, then removed from `executable_tools`. If Qwen classification fails, the existing embedding router is used as fallback.
4. The orchestrator executes only `executable_tools` through the MCP client, in parallel, and records each tool result.
5. It reads `systemprompt.md` and `guardrails.md` as stable system instructions. It reads `user_prompt.md` as a template and interpolates `{user_query}`, `{detected_intents}`, `{executable_tools}`, `{banned_tools}`, and `{tool_outputs}` with the current request data.
6. `llm_client.generate_answer()` uses `GEMINI_API_KEY` or `gemini_apikey` when configured. If neither is set, it uses `DEFAULT_QWEN_MODEL` locally; if Gemini fails, it falls back to local Qwen.
7. The final response includes the provider and request ID. Lifecycle events are appended to `%TEMP%\mcp_tool_l2\requests.jsonl`; console summaries omit prompt/response text and credential values.

## Prompt Boundary

System files are loaded separately from the formatted user context. Do not insert a raw user query into a system prompt. MCP output is serialized into the user context and explicitly treated as untrusted data, not instructions. The classifier's structured output is validated against the known tool and parameter schema before any tool can run.

## Run

From the project root, activate the virtual environment and run:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

The app prints the selected localhost URL and emits concise request lifecycle events in the server terminal. To follow the detailed JSONL trace in another PowerShell window:

```powershell
Get-Content (Join-Path $env:TEMP 'mcp_tool_l2\requests.jsonl') -Wait
```