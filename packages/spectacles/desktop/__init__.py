"""
Spectacles Desktop Automation Module
Screen capture and input simulation for native app control
"""

# Lazy imports to avoid loading on Cloud Run
__all__ = [
    "DesktopClient",
    "WindowManager",
]


def __getattr__(name):
    """Lazy import to avoid loading desktop libraries on Cloud Run"""
    if name == "DesktopClient":
        from .client import DesktopClient
        return DesktopClient
    elif name == "WindowManager":
        from .window_manager import WindowManager
        return WindowManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
