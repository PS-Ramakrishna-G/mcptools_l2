# Weekend Wizard

Weekend Wizard is a local-first, intent-aware multi-tool assistant. A user can ask naturally for current weather, book recommendations, dog photos, or a safe joke. The app classifies the request with local Qwen, applies negative-tool guardrails, calls approved tools through MCP, and synthesizes an answer. Weather can use a city name or explicit coordinates; it does not silently default to Hyderabad.

## Architecture

```text
Browser / CLI
	-> FastAPI app (`app.py`)
	-> Qwen intent + parameter extraction (`routing_engine/decision.py`)
	-> negative-constraint filtering
	-> MCP client (`orchastrator/agent_fun.py`)
	-> MCP server (`orchastrator/server_fun.py`)
	-> Open-Meteo / Open Library / Dog CEO / JokeAPI
	-> Gemini when configured, otherwise local Qwen, for final wording
```

Independent approved tools execute concurrently. The final response includes the provider and request ID. If weather is requested without a city or coordinate pair, the app asks for a location instead of using a fixed one.

## Requirements

- Python 3.12 (the current workspace environment is 3.12).
- Ollama installed and running locally.
- `qwen2.5:7b` pulled locally for the configured Qwen path.
- Internet access for the public data APIs. Gemini is optional.

## Setup

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull qwen2.5:7b
```

The `.env` file selects the local model and Ollama host:

```dotenv
DEFAULT_OLLAMA_HOST="http://localhost:11434"
DEFAULT_QWEN_MODEL="qwen2.5:7b"
```

The default flow uses local Qwen for classification and final answers. To enable Gemini for final answer synthesis, set `GEMINI_API_KEY` in the local process environment before starting the app. If Gemini is missing or unavailable, final synthesis falls back to Qwen. Never commit a real API key.

## Run the Web App

```powershell
python app.py
```

The app starts on the first available localhost port from `8000` through `8099` and prints the URL. Open that URL in a browser. The health endpoint is `/api/health`; chat requests are sent to `/api/chat`.

Weather locations can be entered in the optional latitude/longitude fields or named in the request, for example:

- `How is the weather in Bengaluru?`
- `What is the temperature at 40.7128, -74.0060?`
- `Find books about finance and show me a German Shepherd photo.`
- `Tell me a joke, but do not show dog photos.`

## Request Observability

Each request gets a request ID and lifecycle events for classification, allowed/banned tools, tool results and timings, provider, and completion/error status. The detailed JSONL log is stored at:

```text
%TEMP%\mcp_tool_l2\requests.jsonl
```

Follow new log entries in PowerShell:

```powershell
Get-Content (Join-Path $env:TEMP 'mcp_tool_l2\requests.jsonl') -Wait
```

Console summaries omit prompt and response text; JSONL events retain request data for debugging, so treat the log as local user data.

## Run the Question Bank Through the App

`qeustion.json` contains the 1,000 natural-language questions. `testquestion.py` sends each question through the same FastAPI chat route, MCP session, tools, and answer generation used by the app. It writes one JSON object per line to `testquestion_results.jsonl`, including the answer, detected/allowed/banned tools, parameters, MCP results, timing, provider, request ID, and an audit trace. This trace records observable evidence, not hidden model reasoning.

Start with a single live request:

```powershell
python .\testquestion.py --limit 1
```

Run all remaining questions and skip IDs already recorded:

```powershell
python .\testquestion.py --resume
```

Run the full bank from the beginning:

```powershell
python .\testquestion.py
```

The full run makes up to 1,000 real agent requests and may take a long time or call public APIs. Use `--limit` first. Existing question records without expected labels are marked `UNSCORED`; only categories with unambiguous tool expectations are automatically compared. Add `expected_tools` and `expected_banned` to individual JSON entries for explicit ground-truth scoring.

The result path can be overridden with `RESULTS_FILE`, and the question path with `QUESTIONS_FILE`.

## Main Files

- `app.py`: FastAPI application, request validation, MCP lifespan, direct `python app.py` launcher.
- `orchastrator/agent_fun.py`: request lifecycle, MCP tool dispatch, synthesis, timings, and trace events.
- `orchastrator/server_fun.py`: MCP tool definitions.
- `routing_engine/decision.py`: Qwen JSON classification, parameter validation, and fallback routing.
- `routing_engine/guardrail_engine.py`: explicit negative-constraint detection and embedding fallback.
- `api_connections/`: HTTP clients for weather, books, dog photos, and jokes.
- `agents/`: router, system, user-context, and guardrail prompts. See [agents/README.md](agents/README.md) for prompt loading and interpolation details.
- `logs.py`: request IDs, JSONL event persistence, and concise console summaries.
- `qeustion.json`: question bank input.
- `testquestion.py`: end-to-end question-bank runner.
- `plan.txt`: next-step engineering plan for multi-topic book counts and deterministic rendering.
