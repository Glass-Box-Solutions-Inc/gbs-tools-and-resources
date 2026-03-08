"""
Request models for merus-expert service.
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class BillTimeRequest(BaseModel):
    """Request to bill time to a case."""
    case_search: str = Field(..., description="Case file number or party name")
    hours: float = Field(..., gt=0, description="Time in hours (e.g., 0.2 for 12 minutes)")
    description: str = Field(..., description="Detailed description of work")
    subject: Optional[str] = Field(None, description="Short subject line")
    activity_type_id: Optional[int] = Field(None, description="Activity type ID")
    billing_code_id: Optional[int] = Field(None, description="Billing code ID")


class AddCostRequest(BaseModel):
    """Request to add a cost/fee to a case."""
    case_search: str = Field(..., description="Case file number or party name")
    amount: float = Field(..., gt=0, description="Dollar amount")
    description: str = Field(..., description="Entry description")
    ledger_type: str = Field("cost", description="Type: fee, cost, or expense")


class AddNoteRequest(BaseModel):
    """Request to add a non-billable note to a case."""
    case_search: str = Field(..., description="Case file number or party name")
    subject: str = Field(..., description="Note subject")
    description: Optional[str] = Field(None, description="Note details")
    activity_type_id: Optional[int] = Field(None, description="Activity type ID")


class BulkBillTimeEntry(BaseModel):
    """Single entry in bulk billing request."""
    case_search: str
    hours: float = Field(..., gt=0)
    description: str
    subject: Optional[str] = None


class BulkBillTimeRequest(BaseModel):
    """Request to bill time to multiple cases."""
    entries: List[BulkBillTimeEntry] = Field(..., min_length=1)


class ChatRequest(BaseModel):
    """Request to chat with the Claude AI agent."""
    messages: List[dict] = Field(..., description="Conversation messages [{role, content}]")
    max_iterations: int = Field(10, ge=1, le=20, description="Max tool-use iterations")


# ─────────────────────────────────────────────────────
# Chatbot / matter creation UI request models
# ─────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    """Request to create a new chat session."""
    user_id: Optional[str] = None
    metadata: Optional[dict] = None


class ChatMessageRequest(BaseModel):
    """Request to send a chat message."""
    session_id: str = Field(..., description="Chat session ID")
    message: str = Field(..., min_length=1, description="User's message")


class SubmitMatterRequest(BaseModel):
    """Request to submit or preview a matter."""
    session_id: str = Field(..., description="Chat session ID")
    dry_run: bool = Field(default=True, description="If true, preview only without submitting")
