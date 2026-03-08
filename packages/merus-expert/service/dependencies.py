"""
Singleton dependency injection for merus-expert service.
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import os
from functools import lru_cache
import anthropic
from merus_expert.core.agent import MerusAgent
from merus_expert.agent.claude_agent import ClaudeAgent


@lru_cache(maxsize=1)
def get_merus_agent() -> MerusAgent:
    """Singleton MerusAgent — initialized from MERUSCASE_ACCESS_TOKEN env var."""
    access_token = os.environ.get("MERUSCASE_ACCESS_TOKEN")
    token_file = os.environ.get("MERUSCASE_TOKEN_FILE", ".meruscase_token")
    return MerusAgent(
        access_token=access_token,
        token_file=token_file if not access_token else None,
        cache_ttl_seconds=int(os.environ.get("CACHE_TTL_SECONDS", 3600)),
    )


@lru_cache(maxsize=1)
def get_claude_agent() -> ClaudeAgent:
    """Singleton ClaudeAgent — shares MerusAgent singleton."""
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return ClaudeAgent(anthropic_client=client, merus_agent=get_merus_agent())
