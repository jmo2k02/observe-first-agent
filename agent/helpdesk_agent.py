# Based on the OpenInference smolagents example "tool_calling_agent.py"
# (https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-smolagents/examples),
# Copyright The OpenInference Authors, licensed under the Apache License 2.0. Modified: OpenRouter model, HTTP tools.
"""Builds the helpdesk agent. Kept separate from the entry point so tests can swap in a fake model."""

import os

from smolagents import LiteLLMModel, Model, ToolCallingAgent

from agent.tools import TOOLS

# A free OpenRouter model that supports tool calling. Free models rotate: see README to pick another.
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


def build_model() -> Model:
    # LiteLLM's OpenRouter provider reads OPENROUTER_API_KEY from the environment.
    model_id = os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
    return LiteLLMModel(model_id=f"openrouter/{model_id}")


def build_agent(model: Model | None = None) -> ToolCallingAgent:
    return ToolCallingAgent(tools=TOOLS, model=model or build_model(), max_steps=6)
