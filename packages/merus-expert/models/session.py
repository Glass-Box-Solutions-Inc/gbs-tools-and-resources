"""
Session Data Models
Pydantic models for session state
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from persistence.constants import AgentPhase


class SessionState(BaseModel):
    """Agent session state"""
    session_id: str
    agent_phase: AgentPhase
    current_workflow: Optional[str] = None
    workflow_step: int = 0
    retry_count: int = 0
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    last_active_at: datetime
    ended_at: Optional[datetime] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
