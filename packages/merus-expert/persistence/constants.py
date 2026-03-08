"""
Persistence Layer Constants
Enums and constants for the MerusCase matter automation framework
"""

from enum import Enum


class AgentPhase(str, Enum):
    """Agent execution phases"""
    INITIALIZATION = "INITIALIZATION"
    READY = "READY"
    EXECUTING = "EXECUTING"
    EXPLORATION = "EXPLORATION"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class MatterStatus(str, Enum):
    """Matter creation status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class MatterType(str, Enum):
    """Types of legal matters"""
    IMMIGRATION = "immigration"
    WORKERS_COMP = "workers_comp"
    FAMILY_LAW = "family_law"
    PERSONAL_INJURY = "personal_injury"
    GENERAL = "general"


class AuditEventCategory(str, Enum):
    """Categories for audit logging (SOC2)"""
    AUTHENTICATION = "AUTHENTICATION"
    MATTER_OPERATIONS = "MATTER_OPERATIONS"
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"
    BROWSER_AUTOMATION = "BROWSER_AUTOMATION"
    SECURITY_EVENTS = "SECURITY_EVENTS"
    DATA_ACCESS = "DATA_ACCESS"


class AuditEventStatus(str, Enum):
    """Status of audit events"""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    WARNING = "WARNING"
    PENDING = "PENDING"


class ElementType(str, Enum):
    """Types of UI elements"""
    INPUT = "input"
    SELECT = "select"
    BUTTON = "button"
    LINK = "link"
    FORM = "form"
    TABLE = "table"
    MODAL = "modal"


class InputType(str, Enum):
    """Input field types"""
    TEXT = "text"
    SELECT = "select"
    DATE = "date"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    TEXTAREA = "textarea"
    NUMBER = "number"
    EMAIL = "email"
    PHONE = "phone"


# Database configuration
DEFAULT_DB_PATH = "./knowledge/db/merus_knowledge.db"

# Timeout configuration (from .env, with defaults)
DEFAULT_SESSION_TIMEOUT_MIN = 30
DEFAULT_MAX_SESSION_HOURS = 8
DEFAULT_AUDIT_RETENTION_DAYS = 90
DEFAULT_SCREENSHOT_RETENTION_HR = 24

# SOC2 Controls
SOC2_CONTROLS = {
    "CC6.1": "Logical Access",
    "CC6.6": "Encryption",
    "CC6.8": "Audit Logging",
    "PI1.2": "Audit Trail",
    "C1.1": "Confidentiality"
}

# Screenshot naming constants
SCREENSHOT_STEPS = [
    "login_page",
    "post_login",
    "cases_menu",
    "new_case_form",
    "primary_party_filled",
    "conflict_check_complete",
    "case_type_selected",
    "attorney_selected",
    "office_selected",
    "billing_info_filled",
    "form_complete_preview",
    "pre_submit",
    "post_submit",
    "case_details_page"
]

# Navigation path names
NAVIGATION_PATHS = {
    "NEW_CASE": "new_case",
    "CASE_DETAILS": "case_details",
    "CASE_LIST": "case_list"
}

# Form field names (common across case types)
COMMON_FORM_FIELDS = [
    "primary_party_name",
    "case_type",
    "case_status",
    "venue_based_upon",
    "office",
    "attorney_responsible",
    "date_opened"
]

# Billing form fields
BILLING_FORM_FIELDS = [
    "billing_amount_due",
    "billing_description",
    "billing_amount_received",
    "billing_check_number",
    "billing_memo"
]
