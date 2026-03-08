"""
Billing Data Models
Pydantic models for time entry creation and billing operations
"""

from datetime import datetime, date
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class BillingCategory(str, Enum):
    """Common billing description categories in MerusCase"""
    CONSULTATION = "Consultation"
    DOCUMENT_REVIEW = "Document Review"
    DOCUMENT_PREPARATION = "Document Preparation"
    RESEARCH = "Research"
    COURT_APPEARANCE = "Court Appearance"
    DEPOSITION = "Deposition"
    CORRESPONDENCE = "Correspondence"
    PHONE_CONFERENCE = "Phone Conference"
    MEETING = "Meeting"
    TRAVEL = "Travel"
    OTHER = "Other"


class MatterSelectionMethod(str, Enum):
    """How matter was selected for billing"""
    SEARCH = "search"           # Fuzzy search by name
    URL = "url"                 # Direct MerusCase URL
    RECENT = "recent"           # From recent matters list
    DIRECT_ID = "direct_id"     # Direct matter ID


class MatterReference(BaseModel):
    """Reference to a matter for billing operations"""
    method: MatterSelectionMethod
    value: str  # Search term, URL, or ID depending on method
    resolved_id: Optional[str] = None
    resolved_name: Optional[str] = None
    meruscase_url: Optional[str] = None
    client_name: Optional[str] = None


class MatterSearchResult(BaseModel):
    """Result from matter search"""
    matter_id: str
    matter_name: str
    client_name: str
    case_type: Optional[str] = None
    status: Optional[str] = None
    opened_date: Optional[date] = None
    meruscase_url: str
    match_score: float = 1.0  # Fuzzy match score (0-1)


class TimeEntry(BaseModel):
    """
    Time entry (hourly billing) data model.

    Required:
        hours: Hours worked (0.1 to 24)
        description: Work description

    Optional:
        category: Billing category (defaults to OTHER)
        entry_date: Date of work (defaults to today)
        timekeeper: Attorney/paralegal name
        billable: Whether entry is billable (default True)
        rate: Override hourly rate
    """
    # Required fields
    hours: float = Field(..., gt=0, le=24, description="Hours worked (0.1 to 24)")
    description: str = Field(..., min_length=3, description="Work description")

    # Optional fields with sensible defaults
    category: BillingCategory = BillingCategory.OTHER
    entry_date: date = Field(default_factory=date.today)
    timekeeper: Optional[str] = None  # Attorney/paralegal name
    billable: bool = True
    rate: Optional[float] = None  # Override hourly rate

    # Metadata
    custom_fields: Optional[Dict[str, Any]] = None

    @field_validator('hours')
    @classmethod
    def validate_hours(cls, v: float) -> float:
        """Round hours to nearest 0.1"""
        return round(v, 1)

    def to_form_mapping(self) -> Dict[str, Any]:
        """
        Convert to form field mapping for browser automation.

        Returns:
            Dictionary mapping field names to values
        """
        mapping = {
            "hours": str(self.hours),
            "description": self.description,
            "category": self.category.value if self.category else None,
            "entry_date": self.entry_date.isoformat(),
            "timekeeper": self.timekeeper,
            "billable": self.billable,
        }

        if self.rate is not None:
            mapping["rate"] = str(self.rate)

        # Remove None values
        return {k: v for k, v in mapping.items() if v is not None}


class TimeEntryRequest(BaseModel):
    """API request for creating time entry"""
    matter: MatterReference
    entry: TimeEntry
    dry_run: bool = True
    session_id: Optional[str] = None


class TimeEntryResult(BaseModel):
    """Result of time entry creation attempt"""
    session_id: str
    entry_id: Optional[int] = None
    matter_id: Optional[str] = None
    matter_name: Optional[str] = None
    status: str  # pending, in_progress, success, dry_run_success, failed
    message: str
    meruscase_url: Optional[str] = None
    screenshot_path: Optional[str] = None
    error: Optional[str] = None
    dry_run: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class BillingCategoryInfo(BaseModel):
    """Information about a billing category (from MerusCase)"""
    value: str
    text: str
    display_order: int = 0
    is_default: bool = False


class BillingUIElement(BaseModel):
    """Discovered UI element for billing forms"""
    element_key: str  # 'hours_input', 'category_dropdown', etc.
    primary_selector: str
    fallback_selectors: List[str] = Field(default_factory=list)
    element_type: str  # 'input', 'select', 'textarea', 'button'
    label_text: Optional[str] = None
    is_required: bool = False
    discovered_at: datetime = Field(default_factory=datetime.now)


class ExplorationReport(BaseModel):
    """Report from UI exploration"""
    session_id: str
    matter_url: Optional[str] = None
    billing_nav_selectors: List[str] = Field(default_factory=list)
    add_entry_selectors: List[str] = Field(default_factory=list)
    form_fields: List[BillingUIElement] = Field(default_factory=list)
    dropdown_options: Dict[str, List[Dict[str, str]]] = Field(default_factory=dict)
    screenshots: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    explored_at: datetime = Field(default_factory=datetime.now)


# === Helper Functions ===

def parse_hours_from_text(text: str) -> Optional[float]:
    """
    Parse hours from natural language.

    Accepts:
        - "1.5" -> 1.5
        - "2 hours" -> 2.0
        - "30 minutes" -> 0.5
        - "1 hour 30 minutes" -> 1.5

    Returns:
        Float hours or None if parsing fails
    """
    import re

    text = text.lower().strip()

    # Try simple float first
    try:
        hours = float(text)
        return round(hours, 1) if 0 < hours <= 24 else None
    except ValueError:
        pass

    # Try patterns like "1.5 hours", "2 hrs", etc.
    hours_match = re.match(r'^(\d+\.?\d*)\s*(hours?|hrs?)?$', text)
    if hours_match:
        return round(float(hours_match.group(1)), 1)

    # Try "30 minutes", "45 mins", etc.
    mins_match = re.match(r'^(\d+)\s*(minutes?|mins?)$', text)
    if mins_match:
        return round(float(mins_match.group(1)) / 60.0, 1)

    # Try "1 hour 30 minutes" pattern
    combined = re.match(r'^(\d+)\s*(?:hours?|hrs?)\s*(?:and\s*)?(\d+)\s*(?:minutes?|mins?)$', text)
    if combined:
        hours = float(combined.group(1))
        mins = float(combined.group(2)) / 60.0
        return round(hours + mins, 1)

    return None


def parse_entry_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse time entry from single-line natural language.

    Format: [hours] [category] [description]

    Examples:
        "1.5 Consultation Phone call with client"
        "2 hours research case law for motion"
        "30 minutes document review for filing"

    Returns:
        Dict with hours, category, description or None if parsing fails
    """
    import re

    text = text.strip()
    if not text:
        return None

    # Extract hours from beginning
    hours_patterns = [
        r'^(\d+\.?\d*)\s*(hours?|hrs?)?\s*',  # "1.5", "1.5 hours"
        r'^(\d+)\s*(minutes?|mins?)\s*',       # "30 minutes"
    ]

    hours = None
    remaining = text

    for pattern in hours_patterns:
        match = re.match(pattern, text.lower())
        if match:
            if 'min' in pattern:
                hours = round(float(match.group(1)) / 60.0, 1)
            else:
                hours = round(float(match.group(1)), 1)
            remaining = text[match.end():].strip()
            break

    if hours is None or hours <= 0 or hours > 24:
        return None

    # Try to extract category from remaining text
    category_keywords = {
        'consult': BillingCategory.CONSULTATION,
        'review': BillingCategory.DOCUMENT_REVIEW,
        'prep': BillingCategory.DOCUMENT_PREPARATION,
        'preparation': BillingCategory.DOCUMENT_PREPARATION,
        'research': BillingCategory.RESEARCH,
        'court': BillingCategory.COURT_APPEARANCE,
        'appear': BillingCategory.COURT_APPEARANCE,
        'depo': BillingCategory.DEPOSITION,
        'deposition': BillingCategory.DEPOSITION,
        'correspond': BillingCategory.CORRESPONDENCE,
        'letter': BillingCategory.CORRESPONDENCE,
        'email': BillingCategory.CORRESPONDENCE,
        'phone': BillingCategory.PHONE_CONFERENCE,
        'call': BillingCategory.PHONE_CONFERENCE,
        'conference': BillingCategory.PHONE_CONFERENCE,
        'meet': BillingCategory.MEETING,
        'meeting': BillingCategory.MEETING,
        'travel': BillingCategory.TRAVEL,
    }

    category = BillingCategory.OTHER
    description = remaining

    # Check if remaining text starts with a category keyword
    for keyword, cat in category_keywords.items():
        pattern = rf'^{keyword}\w*\s*'
        match = re.match(pattern, remaining.lower())
        if match:
            category = cat
            description = remaining[match.end():].strip()
            break

    # If description is empty, use category as description
    if not description:
        description = f"{category.value} work"

    return {
        "hours": hours,
        "category": category,
        "description": description,
    }
