"""
Audit Event Data Models
Pydantic models for audit logging
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """SOC2 audit event"""
    event_id: str
    session_id: Optional[str] = None
    event_category: str  # AUTHENTICATION, MATTER_OPERATIONS, etc.
    event_type: str  # login_attempt, matter_submitted, etc.
    action: str  # create, navigate, submit, etc.
    actor: str = "merus_agent"
    resource: Optional[str] = None
    status: str  # SUCCESS, FAILURE, WARNING, PENDING
    screenshot_path: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: str = "MerusAgent/1.0"
    soc2_control: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
