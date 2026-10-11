import agent.tracing  # noqa: F401  Observability first: switch on tracing before anything else runs.

import contextvars

import gradio as gr
from dotenv import load_dotenv
from smolagents import GradioUI

from agent.helpdesk_agent import build_agent


class TracedGradioUI(GradioUI):
    """smolagents' chat UI, keeping one trace per question and showing errors in the chat.

    Gradio advances the streaming agent on a different worker thread for each step, which would lose
    the active span and split one run into several traces. Running every step (and the final clean-up,
    when the browser disconnects) in the same captured context keeps all steps nested under one agent run.
    """

    def _stream_response(self, message, history):
        context = contextvars.copy_context()
        steps = super()._stream_response(message, history)
        messages = []
        try:
            while True:
                try:
                    messages = context.run(next, steps)
                except StopIteration:
                    return
                except Exception as error:  # for example a rate limit (429): say so instead of failing silently
                    yield messages + [gr.ChatMessage(role="assistant", content=f"**The run failed:** {error}")]
                    return
                yield messages
        finally:
            context.run(steps.close)


def build_ui(helpdesk_agent=None) -> TracedGradioUI:
    # reset_agent_memory: every question starts a fresh, independent run (and trace), with no earlier chat in it.
    return TracedGradioUI(helpdesk_agent or build_agent(), reset_agent_memory=True)


# Entry point. Adapted from the Apache-2.0 OpenInference smolagents examples (see NOTICE).
if __name__ == "__main__":
    load_dotenv()  # for the plain-Python fallback; Docker Compose passes .env in directly
    build_ui().launch(share=False, server_name="0.0.0.0", server_port=7860)
