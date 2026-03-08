"""
Spectacles Perception Module
DOM, Vision-Language Model, and Desktop perception

Browser: DOM extraction (80%) + VLM fallback (20%)
Desktop: OCR + VLM for native app understanding
"""

from .dom_extractor import DOMExtractor
from .vlm_perceiver import VLMPerceiver
from .perception_router import PerceptionRouter, CombinedPerception
from .perception_config import (
    PerceptionConfig,
    PerceptionMode,
    PerceptionTrigger,
    PERCEPTION_PRESETS,
    get_preset_config
)
from .perception_manager import PerceptionManager, PerceptionStats

# Desktop perceiver (lazy import to avoid loading on Cloud Run)
def __getattr__(name):
    if name == "DesktopPerceiver":
        from .desktop_perceiver import DesktopPerceiver
        return DesktopPerceiver
    elif name == "DesktopPerception":
        from .desktop_perceiver import DesktopPerception
        return DesktopPerception
    elif name == "OCRResult":
        from .desktop_perceiver import OCRResult
        return OCRResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Browser perception
    "DOMExtractor",
    "VLMPerceiver",
    "PerceptionRouter",
    "CombinedPerception",
    # Configuration
    "PerceptionConfig",
    "PerceptionMode",
    "PerceptionTrigger",
    "PerceptionManager",
    "PerceptionStats",
    "PERCEPTION_PRESETS",
    "get_preset_config",
    # Desktop perception (lazy loaded)
    "DesktopPerceiver",
    "DesktopPerception",
    "OCRResult",
]
