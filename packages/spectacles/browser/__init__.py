"""
Spectacles Browser Module
Browserless CDP connection and element interaction
"""

from .client import BrowserClient
from .element_handler import ElementHandler

__all__ = ["BrowserClient", "ElementHandler"]
