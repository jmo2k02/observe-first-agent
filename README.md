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
   - Chat: <http://localhost:7860>. Ask: `Who is employee E-102?`
   - Phoenix: <http://localhost:6006>. Open the project `observe-first-agent` and click the newest trace.

(The helpdesk service's own API docs are at <http://localhost:8000/docs>.)

## What to look for in the trace

One question becomes one trace:

```
ToolCallingAgent.run          the whole agent run
├── Step 1
│   ├── LiteLLMModel.generate the model decides to call a tool (prompt, tokens, latency)
│   └── lookup_employee       the tool call, with its arguments and result
│       └── GET               the HTTP request to the helpdesk service
└── Step 2
    ├── LiteLLMModel.generate
    └── FinalAnswerTool
```

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

The test runs one agent conversation against the real helpdesk service, with a scripted fake model instead
of OpenRouter and an in-memory span exporter instead of Phoenix. No API key or internet needed.

## Why pinned?

Every dependency is pinned to an exact version (`pyproject.toml`, `uv.lock`). Agent tooling is a supply-chain
target: LiteLLM versions 1.82.7 and 1.82.8 on PyPI were compromised
([BerriAI/litellm#24518](https://github.com/BerriAI/litellm/issues/24518)). This repository pins a version
outside that range.

## License and attribution

Apache License 2.0, see [LICENSE](LICENSE). The agent is based on the Apache-2.0
[OpenInference smolagents examples](https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-smolagents/examples);
see [NOTICE](NOTICE). Phoenix (Elastic License 2.0) is used only as a Docker image and dependency.
