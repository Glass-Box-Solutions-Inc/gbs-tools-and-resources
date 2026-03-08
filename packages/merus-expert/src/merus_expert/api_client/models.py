"""
MerusCase API Models
Data models for API requests and responses
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class PartyType(str, Enum):
    """Party types in MerusCase"""
    CLIENT = "Client"
    OPPOSING_PARTY = "Opposing Party"
    WITNESS = "Witness"
    EXPERT = "Expert"
    INSURANCE = "Insurance Company"
    EMPLOYER = "Employer"
    OTHER = "Other"


class Party(BaseModel):
    """Party/Contact to add to a case"""
    party_id: Optional[int] = None
    case_file_id: int
    party_type: PartyType = PartyType.CLIENT
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    notes: Optional[str] = None


class ActivityType(str, Enum):
    """Common activity types"""
    NOTE = "Note"
    PHONE_CALL = "Phone Call"
    EMAIL = "Email"
    MEETING = "Meeting"
    COURT_DATE = "Court Date"
    DEADLINE = "Deadline"
    TASK = "Task"


class Activity(BaseModel):
    """Activity/Event to add to a case"""
    activity_id: Optional[int] = None
    case_file_id: int
    activity_type: str = "Note"
    activity_type_id: Optional[int] = None
    subject: str
    description: Optional[str] = None
    date: datetime = Field(default_factory=datetime.now)
    duration_minutes: Optional[int] = None
    billable: bool = False
    billing_code_id: Optional[int] = None
    user_id: Optional[int] = None


class LedgerType(int, Enum):
    """Ledger entry types for direct fees/costs"""
    FEE = 1       # Attorney fees, service fees
    COST = 2      # Filing fees, court costs
    EXPENSE = 3   # Reimbursable expenses


class LedgerEntry(BaseModel):
    """
    Ledger entry for direct fees/costs (not time-based).

    Use this for filing fees, court costs, expenses, etc.
    For time-based billing, use Activity with billable=True.
    """
    ledger_id: Optional[int] = None
    case_file_id: int
    amount: float = Field(..., gt=0, description="Dollar amount (e.g., 25.00)")
    description: str = Field(..., min_length=1, description="Entry description")
    date: datetime = Field(default_factory=datetime.now)
    ledger_type_id: LedgerType = LedgerType.FEE
    billing_code_id: Optional[int] = None

    def to_api_payload(self) -> Dict[str, Any]:
        """
        Convert to MerusCase API format (CakePHP wrapper).

        Returns:
            Dict ready for POST /caseLedgers/add
        """
        return {
            "CaseLedger": {
                "case_file_id": str(self.case_file_id),
                "amount": f"{self.amount:.2f}",
                "description": self.description,
                "date": self.date.strftime("%Y-%m-%d"),
                "ledger_type_id": self.ledger_type_id.value,
            }
        }


class Document(BaseModel):
    """Document to upload to a case"""
    document_id: Optional[int] = None
    case_file_id: int
    filename: str
    file_path: str
    description: Optional[str] = None
    document_type: Optional[str] = None
    folder_id: Optional[int] = None


class CaseFile(BaseModel):
    """Case file details from API"""
    case_file_id: int
    file_number: Optional[str] = None
    case_type: Optional[str] = None
    case_status: Optional[str] = None
    branch_office: Optional[str] = None
    open_date: Optional[datetime] = None
    close_date: Optional[datetime] = None
    description: Optional[str] = None
    parties: List[Party] = []

    # Additional details
    venue: Optional[str] = None
    statute_of_limitations: Optional[datetime] = None
    responsible_attorney: Optional[str] = None
    originating_attorney: Optional[str] = None


class APIResponse(BaseModel):
    """Standard API response wrapper"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None           # human-readable summary
    errors: Optional[List[Dict]] = None   # raw MerusCase error list (errors-in-200)
    error_code: Optional[int] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None


class OAuthToken(BaseModel):
    """OAuth token data"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

    def is_expired(self) -> bool:
        """Check if token is expired"""
        if not self.expires_in:
            return False
        elapsed = (datetime.now() - self.created_at).total_seconds()
        return elapsed >= self.expires_in
