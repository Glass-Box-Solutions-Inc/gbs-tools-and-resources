"""
Claude AI Agent for MerusCase — tool-use loop with SSE streaming.

Uses claude-sonnet-4-6 with Anthropic's streaming API.
Yields SSE-compatible JSON events for each step.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import json
import logging
from typing import AsyncGenerator, Dict, Any, List

import anthropic

from merus_expert.core.agent import MerusAgent
from merus_expert.agent.tools import TOOLS, dispatch_tool
from merus_expert.agent.system_prompt import get_system_prompt

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"


class ClaudeAgent:
    """
    Claude AI agent with tool-use loop and SSE streaming.

    Wraps MerusAgent to provide natural language interface via Claude.

    Example:
        client = anthropic.AsyncAnthropic(api_key="...")
        agent = ClaudeAgent(anthropic_client=client, merus_agent=merus_agent)

        async for event in agent.chat_stream(messages):
            print(event)
    """

    def __init__(
        self,
        anthropic_client: anthropic.AsyncAnthropic,
        merus_agent: MerusAgent,
    ):
        self.client = anthropic_client
        self.merus_agent = merus_agent
        self._system_prompt = get_system_prompt()

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        max_iterations: int = 10,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Run Claude agent with tool-use loop, yielding SSE events.

        Events yielded:
        - {"type": "text", "content": "..."}
        - {"type": "tool_call", "name": "...", "input": {...}}
        - {"type": "tool_result", "name": "...", "result": {...}}
        - {"type": "done"}
        - {"type": "error", "message": "..."}

        Args:
            messages: Conversation history [{role, content}]
            max_iterations: Max tool-use cycles before stopping

        Yields:
            Dict SSE events
        """
        conversation = list(messages)

        for iteration in range(max_iterations):
            tool_calls_this_round = []

            try:
                # Stream from Claude
                async with self.client.messages.stream(
                    model=MODEL,
                    max_tokens=4096,
                    system=self._system_prompt,
                    tools=TOOLS,
                    messages=conversation,
                ) as stream:
                    # Collect streamed content
                    full_text = ""
                    async for text_chunk in stream.text_stream:
                        full_text += text_chunk
                        yield {"type": "text", "content": text_chunk}

                    # Get the final message to check for tool use
                    final_message = await stream.get_final_message()

            except anthropic.APIError as e:
                yield {"type": "error", "message": f"API error: {e}"}
                return

            # Check stop reason
            stop_reason = final_message.stop_reason

            if stop_reason == "end_turn":
                # Natural conversation end
                yield {"type": "done"}
                return

            if stop_reason != "tool_use":
                # Unexpected stop reason — finish cleanly
                yield {"type": "done"}
                return

            # Process tool calls
            assistant_content = final_message.content
            conversation.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                yield {"type": "tool_call", "name": tool_name, "input": tool_input}

                # Dispatch tool — never raises
                result = await dispatch_tool(self.merus_agent, tool_name, tool_input)

                yield {"type": "tool_result", "name": tool_name, "result": result}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(result),
                })

            # Add tool results to conversation
            conversation.append({"role": "user", "content": tool_results})

        # Hit max iterations
        yield {"type": "error", "message": f"Max iterations ({max_iterations}) reached"}
