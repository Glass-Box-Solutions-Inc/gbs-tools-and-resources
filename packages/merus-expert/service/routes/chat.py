# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Chat routes — conversational matter data collection UI.
"""

import os
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException

from service.models.requests import CreateSessionRequest, ChatMessageRequest
from service.models.responses import (
    SessionResponse,
    ChatResponse,
    ChatHistoryResponse,
    MessageHistoryItem,
)
from service.services.conversation_flow import ConversationFlow, ConversationState
from service.services.chat_store import ChatStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

# Initialize services using DB_PATH env var with fallback default
_db_path = os.getenv("DB_PATH", "./knowledge/db/merus_knowledge.db")
chat_store = ChatStore(_db_path)
conversation_flow = ConversationFlow()


@router.post("/session", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest = None):
    """
    Create a new chat session.

    Returns a new session ID and the initial greeting message.
    """
    try:
        # Generate unique session ID
        session_id = f"chat_{uuid.uuid4().hex[:12]}"

        # Create session in store
        context = chat_store.create_session(session_id)

        # Get initial greeting
        greeting = conversation_flow.get_initial_message()

        # Save greeting as first message
        chat_store.add_message(session_id, "assistant", greeting)

        logger.info(f"Created new chat session: {session_id}")

        return SessionResponse(
            session_id=session_id,
            state=context.state.value,
            created_at=datetime.now(),
            message=greeting
        )

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatMessageRequest):
    """
    Send a message and get the AI response.

    Processes user input through the intelligent conversation flow.
    """
    try:
        session_id = request.session_id

        # Get existing context
        context = chat_store.get_context(session_id)
        if not context:
            raise HTTPException(status_code=404, detail="Session not found")

        # Save user message
        chat_store.add_message(session_id, "user", request.message)

        # Process through conversation flow (async - uses intelligent entity extraction)
        response, updated_context, quick_chips, collected_fields = await conversation_flow.process_input(
            context,
            request.message
        )

        # Save context
        chat_store.save_context(updated_context)

        # Save assistant response
        chat_store.add_message(session_id, "assistant", response)

        # Check if conversation is complete
        is_complete = updated_context.state == ConversationState.COMPLETED
        action = conversation_flow.get_action(updated_context) if is_complete else None

        logger.info(f"Session {session_id}: {context.state.value} -> {updated_context.state.value}")

        return ChatResponse(
            session_id=session_id,
            message=response,
            state=updated_context.state.value,
            is_complete=is_complete,
            action=action,
            quick_chips=quick_chips,
            collected_fields=collected_fields
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_history(session_id: str):
    """
    Get conversation history for a session.
    """
    try:
        # Verify session exists
        context = chat_store.get_context(session_id)
        if not context:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get messages
        messages = chat_store.get_messages(session_id)

        # Convert to response format
        history_items = [
            MessageHistoryItem(
                role=msg['role'],
                content=msg['content'],
                timestamp=datetime.fromisoformat(msg['timestamp']) if isinstance(msg['timestamp'], str) else msg['timestamp']
            )
            for msg in messages
        ]

        # Serialize collected_data for response
        collected_data = {}
        for key, value in context.collected_data.items():
            if hasattr(value, 'value'):  # Enum
                collected_data[key] = value.value
            else:
                collected_data[key] = value

        return ChatHistoryResponse(
            session_id=session_id,
            messages=history_items,
            state=context.state.value if hasattr(context.state, 'value') else context.state,
            collected_data=collected_data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a chat session.
    """
    try:
        deleted = chat_store.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"message": "Session deleted", "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail=str(e))
