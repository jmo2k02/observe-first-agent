# observe-first-agent

A tiny enterprise IT-helpdesk agent with **observability switched on in the first line**.
You chat with the agent, it calls a mock helpdesk service over HTTP, and [Arize Phoenix](https://phoenix.arize.com)
shows a trace of every model call, tool call and HTTP request.

Companion repository to the talk *"You can't secure what you can't see"*.

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
3. **Open the chat and Phoenix.**
   - Chat: <http://localhost:7860>. Paste one of the [demo prompts](#demo-prompts).
   - Phoenix: <http://localhost:6006>. Open the project `observe-first-agent` and click the newest trace.

(The helpdesk service's own API docs are at <http://localhost:8000/docs>.)

## Demo prompts

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

## How it fits together

| Part | Where | What it does |
|---|---|---|
| Agent | `agent/app.py`, `agent/helpdesk_agent.py` | smolagents `ToolCallingAgent` with a Gradio chat. Tracing is registered in the first lines of `app.py`. |
| Tools | `agent/tools.py` | Thin HTTP clients for the helpdesk service. |
| Helpdesk service | `service/` | FastAPI app with in-memory, fictional seed data. |
| Phoenix | `docker-compose.yml` | Official image; collects and shows the traces. |

## Changing the model

The default is a free OpenRouter model that supports tool calling (see `DEFAULT_MODEL` in
`agent/helpdesk_agent.py`). Free models get rate-limited or retired. To switch, set `OPENROUTER_MODEL` in `.env`
to any model ID from <https://openrouter.ai/models> that ends in `:free` and supports tools, then restart.

## Tests

```bash
uv run pytest
```

The tests run agent conversations (the normal flow and the payroll error) against the real helpdesk service, with a
scripted fake model instead of OpenRouter and an in-memory span exporter instead of Phoenix. They check that every
tool call becomes a span with its arguments, with the HTTP request nested under it, and that the payroll check is
an error span mentioning 503 while the run still ends with an answer. No API key or internet needed.

## Why pinned?

Every dependency is pinned to an exact version (`pyproject.toml`, `uv.lock`). Agent tooling is a supply-chain
target: LiteLLM versions 1.82.7 and 1.82.8 on PyPI were compromised
([BerriAI/litellm#24518](https://github.com/BerriAI/litellm/issues/24518)). This repository pins a version
outside that range.

## License and attribution

Apache License 2.0, see [LICENSE](LICENSE). The agent is based on the Apache-2.0
[OpenInference smolagents examples](https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-smolagents/examples);
see [NOTICE](NOTICE). Phoenix (Elastic License 2.0) is used only as a Docker image and dependency.
