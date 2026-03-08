"""
Spectacles Constants
Enums and constants for agent state management
"""

from enum import Enum


class AgentState(str, Enum):
    """Agent execution states"""
    PLANNING = "PLANNING"           # Analyzing task, creating execution plan
    NAVIGATING = "NAVIGATING"       # Navigating to target URL
    OBSERVING = "OBSERVING"         # Perceiving page state (DOM/VLM)
    ACTING = "ACTING"               # Executing browser action
    EVALUATING = "EVALUATING"       # Checking if goal achieved
    AWAITING_HUMAN = "AWAITING_HUMAN"  # Paused for HITL response
    ERROR_RECOVERY = "ERROR_RECOVERY"  # Handling errors/retries
    COMPLETED = "COMPLETED"         # Task finished successfully
    FAILED = "FAILED"               # Unrecoverable failure
    CANCELLED = "CANCELLED"         # Task cancelled by user


class PerceptionMethod(str, Enum):
    """Page perception methods"""
    DOM = "DOM"         # DOM Accessibility Tree (fast, 80% of cases)
    VLM = "VLM"         # Vision-Language Model (complex cases)
    HYBRID = "HYBRID"   # DOM + VLM combined


class HITLRequestType(str, Enum):
    """Human-in-the-loop request types"""
    APPROVAL = "APPROVAL"           # Action needs approval
    CAPTCHA = "CAPTCHA"             # CAPTCHA/visual challenge
    CREDENTIALS = "CREDENTIALS"      # Login credentials needed
    TWO_FACTOR = "TWO_FACTOR"       # 2FA required
    INTERVENTION = "INTERVENTION"    # Complex situation needs human
    LOW_CONFIDENCE = "LOW_CONFIDENCE"  # Agent unsure, needs confirmation


class HITLStatus(str, Enum):
    """HITL request status"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    TUNNEL = "TUNNEL"  # Human took browser control


class ActionType(str, Enum):
    """Browser action types"""
    # Navigation
    NAVIGATE = "NAVIGATE"

    # Click variants
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"

    # Form interaction
    FILL = "FILL"
    SELECT = "SELECT"

    # Input control
    KEYBOARD = "KEYBOARD"        # Key press/combo (Ctrl+C, Enter, etc.)
    HOVER = "HOVER"              # Mouse hover for tooltips/dropdowns
    SCROLL = "SCROLL"            # Scroll page/element
    DRAG_DROP = "DRAG_DROP"      # Drag and drop interaction

    # Waiting
    WAIT = "WAIT"
    WAIT_FOR = "WAIT_FOR"        # Wait for element/condition

    # Capture/Extract
    SCREENSHOT = "SCREENSHOT"
    EXTRACT = "EXTRACT"

    # File operations (browser)
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"

    # Desktop actions (Phase 3 - VM only)
    DESKTOP_CLICK = "DESKTOP_CLICK"
    DESKTOP_TYPE = "DESKTOP_TYPE"
    DESKTOP_KEY = "DESKTOP_KEY"
    DESKTOP_SCREENSHOT = "DESKTOP_SCREENSHOT"
    DESKTOP_SCROLL = "DESKTOP_SCROLL"
    DESKTOP_DRAG = "DESKTOP_DRAG"
    OPEN_APP = "OPEN_APP"
    SWITCH_WINDOW = "SWITCH_WINDOW"

    # File system actions (Phase 5)
    FILE_READ = "FILE_READ"
    FILE_WRITE = "FILE_WRITE"
    FILE_LIST = "FILE_LIST"
    FILE_COPY = "FILE_COPY"
    FILE_MOVE = "FILE_MOVE"
    FILE_DELETE = "FILE_DELETE"
    FILE_WATCH = "FILE_WATCH"
    FILE_SEARCH = "FILE_SEARCH"


class AutomationMode(str, Enum):
    """Automation mode for task execution"""
    BROWSER = "browser"      # Browser-only automation
    DESKTOP = "desktop"      # Desktop-only automation
    HYBRID = "hybrid"        # Both browser and desktop
    FILE = "file"            # File system operations only


class ActionStatus(str, Enum):
    """Action result status"""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    PENDING = "PENDING"


class AuditEventType(str, Enum):
    """Audit log event types"""
    AUTHENTICATION = "AUTHENTICATION"
    BROWSER_AUTOMATION = "BROWSER_AUTOMATION"
    HITL_INTERACTION = "HITL_INTERACTION"
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"
    SECURITY_EVENT = "SECURITY_EVENT"
    TASK_LIFECYCLE = "TASK_LIFECYCLE"


# Default configuration values
DEFAULT_SESSION_TIMEOUT_MIN = 30
DEFAULT_MAX_SESSION_HOURS = 8
DEFAULT_SCREENSHOT_RETENTION_HR = 24
DEFAULT_AUDIT_RETENTION_DAYS = 90
DEFAULT_MAX_RETRIES = 3
DEFAULT_ELEMENT_TIMEOUT_MS = 10000
DEFAULT_NAVIGATION_TIMEOUT_MS = 30000


# State transition rules
VALID_STATE_TRANSITIONS = {
    AgentState.PLANNING: [AgentState.NAVIGATING, AgentState.FAILED, AgentState.CANCELLED],
    AgentState.NAVIGATING: [AgentState.OBSERVING, AgentState.ERROR_RECOVERY, AgentState.CANCELLED],
    AgentState.OBSERVING: [
        AgentState.ACTING,
        AgentState.EVALUATING,
        AgentState.AWAITING_HUMAN,
        AgentState.ERROR_RECOVERY,
        AgentState.CANCELLED
    ],
    AgentState.ACTING: [AgentState.OBSERVING, AgentState.ERROR_RECOVERY, AgentState.CANCELLED],
    AgentState.EVALUATING: [
        AgentState.NAVIGATING,
        AgentState.COMPLETED,
        AgentState.FAILED,
        AgentState.OBSERVING,
        AgentState.CANCELLED
    ],
    AgentState.AWAITING_HUMAN: [
        AgentState.ACTING,
        AgentState.PLANNING,
        AgentState.FAILED,
        AgentState.OBSERVING,
        AgentState.CANCELLED
    ],
    AgentState.ERROR_RECOVERY: [
        AgentState.PLANNING,
        AgentState.AWAITING_HUMAN,
        AgentState.FAILED,
        AgentState.CANCELLED
    ],
    AgentState.COMPLETED: [],  # Terminal state
    AgentState.FAILED: [],     # Terminal state
    AgentState.CANCELLED: [],  # Terminal state
}


def is_valid_transition(from_state: AgentState, to_state: AgentState) -> bool:
    """Check if state transition is valid"""
    valid_next_states = VALID_STATE_TRANSITIONS.get(from_state, [])
    return to_state in valid_next_states
