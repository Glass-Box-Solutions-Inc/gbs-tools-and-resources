"""
Spectacles Runtime Capabilities Detection
Detects available automation modes based on environment
"""

import os
import platform
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class DeploymentEnvironment(str, Enum):
    """Detected deployment environment"""
    LOCAL = "local"              # Local development machine
    CLOUD_RUN = "cloud_run"      # GCP Cloud Run (sandboxed)
    VM = "vm"                    # GCP Compute Engine or similar
    CONTAINER = "container"       # Generic Docker container
    UNKNOWN = "unknown"


@dataclass
class RuntimeCapabilities:
    """
    Detected runtime capabilities based on environment.

    Desktop automation (PyAutoGUI, mss, etc.) requires:
    - Display server (DISPLAY env var on Linux, always available on Windows/Mac)
    - Not running in Cloud Run sandbox
    - Required libraries installed
    """
    # Environment detection
    has_display: bool = False
    is_cloud_run: bool = False
    platform: str = "unknown"
    deployment: DeploymentEnvironment = DeploymentEnvironment.UNKNOWN

    # Library availability
    has_pyautogui: bool = False
    has_mss: bool = False
    has_pygetwindow: bool = False
    has_easyocr: bool = False
    has_watchdog: bool = False

    # Available modes
    available_modes: List[str] = field(default_factory=list)

    # Detailed info
    display_info: Optional[str] = None
    python_version: str = ""
    os_version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_display": self.has_display,
            "is_cloud_run": self.is_cloud_run,
            "platform": self.platform,
            "deployment": self.deployment.value,
            "available_modes": self.available_modes,
            "libraries": {
                "pyautogui": self.has_pyautogui,
                "mss": self.has_mss,
                "pygetwindow": self.has_pygetwindow,
                "easyocr": self.has_easyocr,
                "watchdog": self.has_watchdog,
            },
            "display_info": self.display_info,
            "python_version": self.python_version,
            "os_version": self.os_version,
        }


def _check_library(module_name: str) -> bool:
    """Check if a Python module is available"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False
    except SystemExit:
        # Some libraries (e.g., pyautogui's mouseinfo) call sys.exit()
        # when optional dependencies like tkinter are missing
        logger.warning("Library %s triggered SystemExit (missing optional dep)", module_name)
        return False
    except Exception as e:
        logger.warning("Library %s check failed: %s", module_name, e)
        return False


def _detect_deployment() -> DeploymentEnvironment:
    """Detect deployment environment"""

    # Cloud Run sets K_SERVICE environment variable
    if os.environ.get('K_SERVICE'):
        return DeploymentEnvironment.CLOUD_RUN

    # Check for Docker container
    if os.path.exists('/.dockerenv'):
        return DeploymentEnvironment.CONTAINER

    # Check for GCP VM (metadata server available)
    try:
        import urllib.request
        req = urllib.request.Request(
            'http://metadata.google.internal/computeMetadata/v1/instance/id',
            headers={'Metadata-Flavor': 'Google'}
        )
        urllib.request.urlopen(req, timeout=1)
        return DeploymentEnvironment.VM
    except Exception:
        pass

    # Default to local development
    return DeploymentEnvironment.LOCAL


def _detect_display() -> tuple[bool, Optional[str]]:
    """
    Detect if display is available.

    Returns:
        Tuple of (has_display, display_info)
    """
    system = platform.system().lower()

    if system == 'windows':
        # Windows always has display available
        return True, "Windows desktop"

    elif system == 'darwin':
        # macOS - check for display
        display = os.environ.get('DISPLAY')
        if display:
            return True, f"macOS DISPLAY={display}"
        # macOS apps typically have display
        return True, "macOS desktop"

    elif system == 'linux':
        # Linux - check DISPLAY env var
        display = os.environ.get('DISPLAY')
        if display:
            return True, f"X11 DISPLAY={display}"

        # Check for Wayland
        wayland = os.environ.get('WAYLAND_DISPLAY')
        if wayland:
            return True, f"Wayland DISPLAY={wayland}"

        # Check if running in a GUI session
        xdg_session = os.environ.get('XDG_SESSION_TYPE')
        if xdg_session in ('x11', 'wayland'):
            return True, f"XDG session: {xdg_session}"

        return False, "No display detected"

    return False, f"Unknown platform: {system}"


def detect_capabilities() -> RuntimeCapabilities:
    """
    Detect what automation modes are available in current environment.

    Returns:
        RuntimeCapabilities with detected information
    """
    # Basic platform info
    system = platform.system().lower()
    deployment = _detect_deployment()
    has_display, display_info = _detect_display()

    # Cloud Run cannot do desktop automation
    if deployment == DeploymentEnvironment.CLOUD_RUN:
        has_display = False
        display_info = "Cloud Run sandbox - no display"

    # Check libraries
    has_pyautogui = _check_library('pyautogui')
    has_mss = _check_library('mss')
    has_pygetwindow = _check_library('pygetwindow')
    has_easyocr = _check_library('easyocr')
    has_watchdog = _check_library('watchdog')

    # Determine available modes
    available_modes = ["browser"]  # Browser is always available via Playwright

    # Desktop requires display + libraries + not Cloud Run
    can_desktop = (
        has_display and
        has_pyautogui and
        has_mss and
        deployment != DeploymentEnvironment.CLOUD_RUN
    )
    if can_desktop:
        available_modes.append("desktop")

    # File operations available if watchdog present
    if has_watchdog:
        available_modes.append("files")

    caps = RuntimeCapabilities(
        has_display=has_display,
        is_cloud_run=(deployment == DeploymentEnvironment.CLOUD_RUN),
        platform=system,
        deployment=deployment,
        has_pyautogui=has_pyautogui,
        has_mss=has_mss,
        has_pygetwindow=has_pygetwindow,
        has_easyocr=has_easyocr,
        has_watchdog=has_watchdog,
        available_modes=available_modes,
        display_info=display_info,
        python_version=platform.python_version(),
        os_version=platform.version(),
    )

    logger.info(
        "Runtime capabilities detected: modes=%s, deployment=%s, display=%s",
        available_modes, deployment.value, has_display
    )

    return caps


def can_use_desktop() -> bool:
    """Quick check if desktop automation is available"""
    caps = detect_capabilities()
    return "desktop" in caps.available_modes


def can_use_files() -> bool:
    """Quick check if file operations are available"""
    caps = detect_capabilities()
    return "files" in caps.available_modes


def require_desktop() -> RuntimeCapabilities:
    """
    Get capabilities and raise if desktop not available.

    Raises:
        RuntimeError if desktop automation not available
    """
    caps = detect_capabilities()
    if "desktop" not in caps.available_modes:
        raise RuntimeError(
            f"Desktop automation not available. "
            f"Deployment: {caps.deployment.value}, "
            f"Display: {caps.has_display}, "
            f"PyAutoGUI: {caps.has_pyautogui}, "
            f"mss: {caps.has_mss}"
        )
    return caps


# Cache capabilities to avoid repeated detection
_cached_capabilities: Optional[RuntimeCapabilities] = None


def get_capabilities(refresh: bool = False) -> RuntimeCapabilities:
    """
    Get cached capabilities (or detect fresh if refresh=True).

    Args:
        refresh: Force re-detection

    Returns:
        RuntimeCapabilities
    """
    global _cached_capabilities

    if _cached_capabilities is None or refresh:
        _cached_capabilities = detect_capabilities()

    return _cached_capabilities
