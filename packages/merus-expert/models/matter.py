"""
Matter Data Models
Pydantic models for matter creation requests and responses
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class CaseType(str, Enum):
    """MerusCase case types"""
    IMMIGRATION = "Immigration"
    WORKERS_COMP = "Workers' Compensation"
    FAMILY_LAW = "Family Law"
    PERSONAL_INJURY = "Personal Injury"
    GENERAL = "General"


class CaseStatus(str, Enum):
    """Case status options"""
    OPEN = "Open"
    PENDING = "Pending"
    CLOSED = "Closed"
    ARCHIVED = "Archived"


class BillingInfo(BaseModel):
    """Billing information for matter"""
    amount_due: Optional[float] = None
    description: Optional[str] = None
    amount_received: Optional[float] = None
    check_number: Optional[str] = None
    memo: Optional[str] = None


class MatterDetails(BaseModel):
    """
    Complete matter details for creation.

    Required:
        primary_party: Client/party name

    Optional:
        All other fields with sensible defaults
    """
    # Required
    primary_party: str = Field(..., min_length=1, description="Primary party/client name")

    # Optional case details
    case_type: Optional[CaseType] = None
    case_status: CaseStatus = CaseStatus.OPEN
    venue_based_upon: Optional[str] = None
    office: Optional[str] = None
    attorney_responsible: Optional[str] = None
    date_opened: Optional[str] = None  # Defaults to today in MerusCase

    # Billing
    billing_info: Optional[BillingInfo] = None

    # Case type-specific
    immigration_filing_packet: Optional[list] = None
    workers_comp_eams_data: Optional[Dict[str, Any]] = None

    # Metadata
    custom_fields: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_form_mapping(self) -> Dict[str, Any]:
        """
        Convert to form field mapping for browser automation.

        Returns:
            Dictionary mapping field names to values
        """
        mapping = {
            "primary_party_name": self.primary_party,
            "case_type": self.case_type.value if self.case_type else None,
            "case_status": self.case_status.value,
            "venue": self.venue_based_upon,
            "office": self.office,
            "attorney": self.attorney_responsible,
            "date_opened": self.date_opened,
        }

        # Add billing fields
        if self.billing_info:
            mapping.update({
                "billing_amount_due": self.billing_info.amount_due,
                "billing_description": self.billing_info.description,
                "billing_amount_received": self.billing_info.amount_received,
                "billing_check_number": self.billing_info.check_number,
                "billing_memo": self.billing_info.memo,
            })

        # Remove None values
        return {k: v for k, v in mapping.items() if v is not None}


class MatterRequest(BaseModel):
    """Matter creation request with settings"""
    matter_details: MatterDetails
    dry_run: bool = False
    session_id: Optional[str] = None


class MatterCreationResult(BaseModel):
    """Result of matter creation attempt"""
    matter_id: Optional[int] = None
    session_id: str
    status: str  # pending, in_progress, success, failed, needs_review
    meruscase_url: Optional[str] = None
    meruscase_matter_id: Optional[str] = None
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    dry_run: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
