# observe-first-agent

A tiny enterprise IT-helpdesk agent with **observability switched on in the first line**.
You chat with the agent, it calls a mock helpdesk service over HTTP, and [Arize Phoenix](https://phoenix.arize.com)
shows a trace of every model call, tool call and HTTP request.

Companion repository to the talk *"You can't secure what you can't see"* (Agents in the Enterprise:
Governance, Security, Observability), given at the STADS student initiative on 12 October 2026.

## Quickstart (three steps)

You need Docker and a free [OpenRouter API key](https://openrouter.ai/keys). Nothing else.

1. **Add your key.** Copy the example env file and paste your key into `.env`:
   ```bash
   cp .env.example .env
   ```
2. **Start everything.**
   ```bash
   docker compose up
   ```
   The terminal shows the agent's log: each step and tool call as it happens. (Phoenix's own log stays out of
   the way; see it with `docker compose logs phoenix`.)
3. **Open the chat and Phoenix.**
   - Chat: <http://localhost:7860>. Paste one of the [demo prompts](#demo-prompts).
   - Phoenix: <http://localhost:6006>. Open the project `observe-first-agent` and click the newest trace.

The first `docker compose up` builds the image (about 2 minutes in our test) and downloads the Phoenix image
(about 320 MB). Later starts take seconds.

(The helpdesk service's own API docs are at <http://localhost:8000/docs>.)

## Demo prompts

Each question starts a fresh run: the agent does not remember earlier chat messages, so every question gets its
own trace and you can run a prompt again to compare.

**Warm-up: one tool.**

```text
Who is employee E-102?
```

**Normal flow: several tools in one run.** An employee reports a VPN problem. The agent looks up the employee,
searches the knowledge base and opens a ticket:

```text
I'm employee E-102 and my VPN keeps disconnecting every few minutes since this morning. Please look up my details, search the knowledge base for a fix, and open an IT ticket for me.
```

Afterwards, ask about the ticket it created (use the ID from the answer, for example `What is the status of ticket T-1004?`).

**Error: a service that is down.** The payroll system is broken on purpose: its status check answers
HTTP 503 (service unavailable) on every call, so this failure is the same on every run:

```text
Payroll seems broken for E-102, check it and open a ticket if needed.
```

The agent has five tools: `lookup_employee`, `search_knowledge_base`, `get_ticket`, `create_ticket` and
`check_service_status`. `create_ticket` is the only one that changes data. The helpdesk keeps everything in memory, so a restart of the
`service` container resets all tickets.

## What to look for in the trace

One question becomes one trace. The normal flow looks like this:

```
ToolCallingAgent.run              the whole agent run
├── Step 1
│   ├── LiteLLMModel.generate     the model decides to call a tool (prompt, tokens, latency)
│   └── lookup_employee           the tool call, with its arguments and result
│       └── GET                   the HTTP request to the helpdesk service
├── Step 2
│   ├── LiteLLMModel.generate
│   └── search_knowledge_base
│       └── GET
├── Step 3
│   ├── LiteLLMModel.generate
│   └── create_ticket             the only write: look at the arguments the model chose
│       └── POST
└── Step 4
    ├── LiteLLMModel.generate
    └── FinalAnswerTool
```

Models are not deterministic: run the same prompt twice and compare the traces. The order or number of steps
can differ.

### Find the red span (payroll error)

Run the payroll prompt, then open its trace in Phoenix:

- **The red span.** `check_service_status` has status ERROR (red). Its `GET` child is red too: it is the request
  that failed. The step around it is marked as failed as well.
- **The status code.** The tool span's exception event says `HTTPStatusError: Server error '503 Service
  Unavailable'`. On the `GET` span, `http.status_code` is `503`.
- **How the agent reacted.** The error is not the end of the run: smolagents passes it back to the model as an
  observation. Read the next `LiteLLMModel.generate` span to see what the model made of it. It may retry, open a
  ticket instead (`create_ticket`), or give up and explain. The run still ends with a final answer, and its
  reaction can differ from run to run.
- **No red span?** Now and then the model skips the status check and opens a ticket straight away. That is
  non-determinism again, and the trace shows it: no `check_service_status` span. Ask again: the new run starts
  fresh, without the earlier answer.
- **A red run at the top?** If the whole `ToolCallingAgent.run` span is red, the run itself died, usually
  because the model was rate-limited. Its exception says why, and the chat shows the same error.

## How it fits together

| Part | Where | What it does |
|---|---|---|
| Tracing | `agent/tracing.py` | Registers Phoenix tracing. The very first statement of `app.py` imports it, before anything else runs. |
| Agent | `agent/app.py`, `agent/helpdesk_agent.py` | smolagents `ToolCallingAgent` with a Gradio chat. |
| Tools | `agent/tools.py` | Thin HTTP clients for the helpdesk service. |
| Helpdesk service | `service/` | FastAPI app with in-memory, fictional seed data. |
| Phoenix | `docker-compose.yml` | Official image; collects and shows the traces. |

## Changing the model

The default model is **`nvidia/nemotron-3-super-120b-a12b:free`** (free on OpenRouter, tested on 2026-10-11; see
[How the default was chosen](#how-the-default-was-chosen)). Free models get rate-limited or retired, so you will
probably need to switch at some point. Signs: the chat answers with **The run failed:** and `RateLimitError` / `429`,
or `404 No endpoints found`. A short rate limit is retried once after 5 seconds; if it persists, the error shows up
in the chat within seconds, so you can switch models or ask again.

Free models also share a daily limit per OpenRouter account: 50 requests per day without credit (1,000 after a
one-time top-up of 10 credits, per OpenRouter's error message on 2026-10-11). One agent run makes one model request
per step, so a demo prompt costs about 4 to 7 requests. If the error says `free-models-per-day`, switching models
will not help: wait until the limit resets (midnight UTC).

1. **Find a free model that supports tool calling.** Open <https://openrouter.ai/models?supported_parameters=tools&max_price=0>,
   or list them in the terminal:
   ```bash
   curl -s "https://openrouter.ai/api/v1/models?supported_parameters=tools" | grep -o '"id":"[^"]*:free"'
   ```
2. **Set it in `.env`** (the ID as OpenRouter shows it, without an `openrouter/` prefix):
   ```bash
   OPENROUTER_MODEL=poolside/laguna-s-2.1:free
   ```
3. **Restart the agent:** `docker compose up -d agent`.
4. **Check it.** Run the payroll prompt twice. A good model calls `check_service_status` and ends with an answer.
   Small models sometimes describe a tool call in text instead of making it, or loop until the step limit:
   you will see that in the trace too.

### How the default was chosen

On 2026-10-11, OpenRouter listed 14 free models with tool calling. Each candidate was run on the two demo
prompts with the real agent and helpdesk. A run counts as a success when the model makes the right tool calls
(normal flow: `lookup_employee`, `search_knowledge_base` and `create_ticket`; payroll: `check_service_status`) and
the run ends with a final answer instead of hitting the step limit.

| Model (all `:free`) | Normal flow | Payroll error | Notes |
|---|---|---|---|
| `nvidia/nemotron-3-super-120b-a12b` | 3 of 3 | 2 of 3 | **Default.** Fast (6 to 35 s per run). In one payroll run it skipped the status check and opened a ticket straight away, so that trace had no red span: just ask again. (Since then, the `check_service_status` description tells the model to always check first.) |
| `poolside/laguna-s-2.1` | not rated | not rated | Made a correct single tool call earlier that day; rate-limited upstream during the full test. Good first thing to try. |
| `apodex/apodex-1.1-mini` | not rated | 0 of 1 | Retried the failing check until the step limit and wrote its last tool call as text. |
| `nvidia/nemotron-3-ultra-550b-a55b` | not rated | 0 of 1 | Sent tool calls without the required `system` argument until the step limit. |
| `google/gemma-4-31b-it` | not rated | not rated | Rate-limited (429) when tried. |
| `thinkingmachines/inkling` | not rated | not rated | Refused: "only available on agentic harnesses". |

The remaining free models were not rated because the test account hit OpenRouter's daily limit for free models
(see above). Free models change often, so treat this table as a snapshot and re-check with step 4.

## Tests

```bash
uv run pytest
```

The tests run agent conversations (the normal flow and the payroll error) against the real helpdesk service, with a
scripted fake model instead of OpenRouter and an in-memory span exporter instead of Phoenix. They check that every
tool call becomes a span with its arguments, with the HTTP request nested under it, and that the payroll check is
an error span mentioning 503 while the run still ends with an answer. Through the chat, they check that every
question is a fresh run with its own trace and that a rate-limit error shows up in the chat at once and turns the
run red. No API key or internet needed.

## Next steps: add human approval for write tools (`create_ticket`)

This is the governance exercise from the talk. Right now the agent opens tickets on its own: the trace shows
you *that* it happened, but nothing stops it. A line in the prompt ("always ask before creating a ticket") is
not a control: the model can ignore it. Build the control into the harness instead:

1. Make `create_ticket` in `agent/tools.py` refuse to write until a human has approved it, for example by
   returning a pending request ("Ticket draft waiting for approval: ...") instead of calling `POST /tickets`.
2. Let the user approve or reject the draft in the chat, and only then send the request.
3. Put the decision in the trace: add an attribute such as `approval.decision=approved` to the tool span, so
   Phoenix shows who allowed each write.
4. Run the normal-flow prompt again and compare the traces before and after.

Further ideas: limit which tools the agent gets (least privilege), add an evaluation in Phoenix that flags runs
with errors, or treat tool outputs as untrusted input (prompt injection arrives through data).

## Without Docker (plain Python)

If you cannot use Docker, run the three parts in three terminals. You need Python 3.12 and
[uv](https://docs.astral.sh/uv/getting-started/installation/) (a single binary, no admin rights needed).

```bash
cp .env.example .env            # add your OpenRouter key
uv sync                         # installs the exact versions from uv.lock into .venv

# Terminal 1: Phoenix (same version as the Docker image)
uvx --from arize-phoenix==20.20.0 phoenix serve

# Terminal 2: the helpdesk service
uv run uvicorn service.main:app --port 8000

# Terminal 3: the agent chat
uv run python -m agent.app
```

Then open <http://localhost:7860> and <http://localhost:6006> as in step 3. Without uv, use a virtual
environment and `pip install --require-hashes -r requirements.txt` (generated from `uv.lock`), then
`pip install arize-phoenix==20.20.0` and drop the `uv run` / `uvx --from ...` prefixes. Outside Docker, Phoenix
keeps its traces in `~/.phoenix`; delete that folder to start fresh. Local models (Ollama) are not supported.

## Smoke test of the whole stack

```bash
scripts/smoke.sh             # starts the stack, checks the service, Phoenix and the chat (no API key used)
scripts/smoke.sh --real-run  # also asks the agent one question with your key and checks that a trace arrives
```

Add `--down` to stop the stack at the end.

## Why pinned?

Every dependency is pinned to an exact version: the direct ones in `pyproject.toml`, every transitive one with
hashes in `uv.lock` (and `requirements.txt`), and the Docker images by tag and digest. Agent tooling is a
supply-chain target. In March 2026, LiteLLM versions 1.82.7 and 1.82.8 were published to PyPI by an attacker; they
stole SSH keys, API keys and cloud credentials from machines that installed them
([BerriAI/litellm#24518](https://github.com/BerriAI/litellm/issues/24518)). A loose `litellm>=1.80` would have
pulled them in automatically. This repository pins 1.104.2, outside that range. Upgrade on purpose: read the
changelog, then run `uv lock --upgrade-package <name>` and the tests.

## License and attribution

Apache License 2.0, see [LICENSE](LICENSE). Modified from Arize-ai/openinference: the agent is based on the Apache-2.0
[OpenInference smolagents examples](https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-smolagents/examples);
see [NOTICE](NOTICE). Phoenix (Elastic License 2.0) is used only as a Docker image and dependency.
