"""
API Key Authentication for merus-expert service.
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import os
from typing import Optional
from fastapi import Header, HTTPException, status


def get_api_key() -> str:
    """Get the configured API key from environment."""
    api_key = os.getenv("MERUS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MERUS_API_KEY environment variable not set. "
            "Please configure API key for authentication."
        )
    return api_key


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """
    Verify API key from X-API-Key header.
    Raises HTTPException 401 if missing or invalid.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Include X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    expected_key = get_api_key()
    if x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key
