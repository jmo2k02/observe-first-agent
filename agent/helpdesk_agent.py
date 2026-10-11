# Based on the OpenInference smolagents example "tool_calling_agent.py"
# (https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-smolagents/examples),
# Copyright The OpenInference Authors, licensed under the Apache License 2.0. Modified: OpenRouter model, HTTP tools.
"""Builds the helpdesk agent. Kept separate from the entry point so tests can swap in a fake model."""

import os

from smolagents import LiteLLMModel, Model, ToolCallingAgent
from smolagents.models import is_rate_limit_error
from smolagents.utils import Retrying

from agent.tools import TOOLS

# A free OpenRouter model that supports tool calling, chosen by testing both demo prompts on 2026-10-11.
# Free models rotate: see README, "Changing the model", to pick another.
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


def _worth_retrying(error: BaseException) -> bool:
    # A short upstream rate limit (HTTP 429) often clears within seconds. The daily free quota does not:
    # it resets at midnight UTC, so waiting for it would only leave the chat silent.
    return is_rate_limit_error(error) and "per-day" not in str(error)


def build_model() -> Model:
    # LiteLLM's OpenRouter provider reads OPENROUTER_API_KEY from the environment.
    model_id = os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
    model = LiteLLMModel(model_id=f"openrouter/{model_id}", timeout=90)  # seconds per model call
    # smolagents would wait 1, 2 and 4+ minutes on a rate limit before giving up, with nothing shown in the chat.
    # Retry once after 5 seconds instead, then show the error.
    model.retryer = Retrying(max_attempts=2, wait_seconds=5, exponential_base=1, jitter=False,
                             retry_predicate=_worth_retrying, reraise=True)
    return model


def build_agent(model: Model | None = None) -> ToolCallingAgent:
    return ToolCallingAgent(tools=TOOLS, model=model or build_model(), max_steps=8)
