# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Matter routes — matter submission via hybrid browser + API approach.
"""

import os
import logging
from fastapi import APIRouter, HTTPException

from service.models.requests import SubmitMatterRequest
from service.models.responses import MatterResponse
from service.services.conversation_flow import ConversationFlow, ConversationState
from service.services.chat_store import ChatStore
from merus_expert.automation.hybrid_matter_builder import HybridMatterBuilder
from merus_expert.security.config import SecurityConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matter", tags=["matter"])

# Initialize services using DB_PATH env var with fallback default
_db_path = os.getenv("DB_PATH", "./knowledge/db/merus_knowledge.db")
chat_store = ChatStore(_db_path)
conversation_flow = ConversationFlow()
config = SecurityConfig.from_env()


@router.post("/preview", response_model=MatterResponse)
async def preview_matter(request: SubmitMatterRequest):
    """
    Preview matter creation (dry-run).

    Shows what would be created without actually submitting to MerusCase.
    """
    return await _process_matter(request.session_id, dry_run=True)


@router.post("/submit", response_model=MatterResponse)
async def submit_matter(request: SubmitMatterRequest):
    """
    Submit matter to MerusCase.

    Creates the matter in MerusCase using collected conversation data.
    """
    return await _process_matter(request.session_id, dry_run=request.dry_run)


async def _process_matter(session_id: str, dry_run: bool = True) -> MatterResponse:
    """
    Internal function to process matter submission using hybrid approach.

    Uses browser automation for case creation, then MerusCase API for
    adding parties, activities, and notes.

    Args:
        session_id: Chat session ID
        dry_run: If True, preview only

    Returns:
        MatterResponse with result
    """
    try:
        # Get conversation context
        context = chat_store.get_context(session_id)
        if not context:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify conversation is complete enough to submit
        if "primary_party" not in context.collected_data:
            raise HTTPException(
                status_code=400,
                detail="Conversation incomplete: primary party name is required"
            )

        # Build MatterDetails from collected data
        matter = conversation_flow.build_matter_details(context)
        collected = context.collected_data

        # Extract additional data for API calls
        initial_note = collected.get("initial_note")

        # Build additional parties list if we have client contact info
        additional_parties = []
        if collected.get("client_email") or collected.get("client_phone"):
            # Parse primary party name into first/last
            name_parts = collected.get("primary_party", "").split(maxsplit=1)
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            additional_parties.append({
                "party_type": "Client",
                "first_name": first_name,
                "last_name": last_name,
                "email": collected.get("client_email"),
                "phone": collected.get("client_phone"),
            })

        logger.info(f"Processing matter for session {session_id} (dry_run={dry_run})")
        logger.info(f"Matter details: primary_party={matter.primary_party}, case_type={matter.case_type}")
        logger.info(f"Hybrid mode: {len(additional_parties)} additional parties, initial_note={bool(initial_note)}")

        # Use HybridMatterBuilder for combined browser + API approach
        async with HybridMatterBuilder(config=config, dry_run=dry_run) as builder:
            result = await builder.create_matter(
                matter,
                session_id=session_id,
                additional_parties=additional_parties if additional_parties else None,
                initial_note=initial_note,
            )

        # Map result to response
        if result.get("status") in ["success", "dry_run_success"]:
            return MatterResponse(
                session_id=session_id,
                matter_id=result.get("matter_id"),
                case_file_id=result.get("case_file_id"),
                status=result.get("status"),
                message=result.get("message", "Matter processed successfully"),
                meruscase_url=result.get("meruscase_url"),
                screenshot_path=result.get("browser_result", {}).get("screenshot_path"),
                filled_values=result.get("browser_result", {}).get("filled_values"),
                api_results=result.get("api_results")
            )
        else:
            errors = result.get("errors", [])
            error_msg = "; ".join(errors) if errors else result.get("error")
            return MatterResponse(
                session_id=session_id,
                matter_id=result.get("matter_id"),
                status="failed",
                message=result.get("message", "Matter processing failed"),
                error=error_msg
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process matter: {e}")
        return MatterResponse(
            session_id=session_id,
            status="failed",
            message=f"Error processing matter: {str(e)}",
            error=str(e)
        )


@router.get("/collected/{session_id}")
async def get_collected_data(session_id: str):
    """
    Get the collected matter data for a session.

    Useful for debugging or displaying summary.
    """
    try:
        context = chat_store.get_context(session_id)
        if not context:
            raise HTTPException(status_code=404, detail="Session not found")

        # Build matter details to see the final structure
        if "primary_party" in context.collected_data:
            matter = conversation_flow.build_matter_details(context)
            matter_dict = matter.model_dump()
        else:
            matter_dict = None

        # Serialize collected_data
        collected_data = {}
        for key, value in context.collected_data.items():
            if hasattr(value, 'value'):  # Enum
                collected_data[key] = value.value
            else:
                collected_data[key] = value

        # Handle state as either enum or string
        state_value = context.state.value if hasattr(context.state, 'value') else context.state

        return {
            "session_id": session_id,
            "state": state_value,
            "collected_data": collected_data,
            "matter_details": matter_dict
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collected data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
