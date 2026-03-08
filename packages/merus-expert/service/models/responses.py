"""
Response models for merus-expert service.
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class CaseResponse(BaseModel):
    id: str
    file_number: Optional[str] = None
    primary_party_name: Optional[str] = None
    case_status: Optional[str] = None
    case_type: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class BillTimeResponse(BaseModel):
    success: bool
    activity_id: Optional[str] = None
    case_id: str
    case_name: Optional[str] = None
    hours: float
    minutes: int
    description: str


class AddCostResponse(BaseModel):
    success: bool
    ledger_id: Optional[int] = None
    case_id: str
    case_name: Optional[str] = None
    amount: float
    description: str
    type: str


class AddNoteResponse(BaseModel):
    success: bool
    activity_id: Optional[str] = None
    case_id: str
    case_name: Optional[str] = None
    subject: str


class BillingResponse(BaseModel):
    case_id: str
    entries: Dict[str, Any] = Field(default_factory=dict)
    total_entries: int = 0


class PartiesResponse(BaseModel):
    case_id: str
    parties: List[Dict[str, Any]]


class BillingSummaryResponse(BaseModel):
    case_id: str
    case_name: Optional[str] = None
    total_amount: float
    total_entries: int
    entries: Dict[str, Any]
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ReferenceDataResponse(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)
    count: int = 0


class BulkBillTimeResponse(BaseModel):
    results: List[Dict[str, Any]]
    successful: int
    failed: int


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    service: str = "merus-expert"
    version: str = "2.0.0"


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    status_code: int


# ─────────────────────────────────────────────────────
# Chatbot / matter creation UI response models
# ─────────────────────────────────────────────────────

class SessionResponse(BaseModel):
    """Response for chat session creation."""
    session_id: str
    state: str
    created_at: datetime
    message: str  # Initial greeting message


class ChatResponse(BaseModel):
    """Response for each chat message turn."""
    session_id: str
    message: str  # Assistant's response
    state: str    # Current conversation state
    is_complete: bool = False  # Whether conversation is complete
    action: Optional[str] = None  # 'submit' or 'preview' if complete
    quick_chips: List[str] = []  # Contextual quick-reply chip suggestions
    collected_fields: Dict[str, Any] = {}  # All fields collected so far


class MessageHistoryItem(BaseModel):
    """Single message in chat history."""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime


class ChatHistoryResponse(BaseModel):
    """Response for chat history request."""
    session_id: str
    messages: List[MessageHistoryItem]
    state: str
    collected_data: Dict[str, Any]


class MatterResponse(BaseModel):
    """Response for matter submission or preview."""
    session_id: str
    matter_id: Optional[int] = None
    case_file_id: Optional[int] = None  # MerusCase case file ID
    status: str  # 'success', 'dry_run_success', 'failed'
    message: str
    meruscase_url: Optional[str] = None
    screenshot_path: Optional[str] = None
    filled_values: Optional[Dict[str, Any]] = None
    api_results: Optional[List[Dict[str, Any]]] = None  # Results from API operations
    error: Optional[str] = None
