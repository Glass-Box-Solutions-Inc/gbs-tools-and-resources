"""
Spectacles FastAPI Application
Main entry point for the browser automation service

Features:
- Task submission and management
- HITL webhook handling
- Health monitoring
- MCP server exposure
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from api.config import settings
from api.routes import tasks_router, webhooks_router, health_router, skills_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# Lifespan Management
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting Spectacles service...")
    logger.info("Environment: %s", settings.ENVIRONMENT)

    # Validate configuration
    if settings.is_production:
        missing = settings.validate_required_for_production()
        if missing:
            logger.warning("Missing production config: %s", missing)

    # Initialize database
    try:
        from persistence.task_store import TaskStore
        TaskStore()  # This initializes the DB if needed
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database initialization failed: %s", e)

    # Start Slack client if configured
    if settings.has_slack:
        try:
            from hitl.slack_client import SlackClient
            from hitl.message_router import MessageRouter
            from hitl.intent_classifier import IntentClassifier
            from hitl.command_parser import CommandParser
            from hitl.channel_context_manager import ChannelContextManager
            from hitl.slack_commands import handle_spectacles_command
            from api.routes.claude_code import set_slack_client

            # Initialize components for bidirectional communication
            context_manager = ChannelContextManager()
            classifier = IntentClassifier(use_ai_fallback=False)

            # CommandParser needs orchestrator and task_store, which we don't have here
            # For now, initialize with minimal dependencies
            from persistence.task_store import TaskStore
            task_store = TaskStore()

            # CommandParser without orchestrator (will be set later if needed)
            command_parser = CommandParser(
                orchestrator=None,  # Will be set when orchestrator is available
                task_store=task_store,
                context_manager=context_manager,
                slack_client=None  # Will be set after SlackClient creation
            )

            # Initialize message router
            message_router = MessageRouter(
                classifier=classifier,
                command_parser=command_parser,
                context_manager=context_manager
            )

            slack_client = SlackClient(
                bot_token=settings.SLACK_BOT_TOKEN,
                app_token=settings.SLACK_APP_TOKEN,
                approval_channel=settings.SLACK_APPROVAL_CHANNEL,
                message_router=message_router
            )

            # Set slack_client reference in command_parser
            command_parser.slack_client = slack_client

            # Register /spectacles slash command
            async def spectacles_handler(ack, command, client):
                """Wrapper to pass app instance to handler"""
                await handle_spectacles_command(ack, command, client, app)

            slack_client.register_command("spectacles", spectacles_handler)
            logger.info("Registered /spectacles slash command")

            # Make slack_client available to routes
            set_slack_client(slack_client)

            # Start in background
            import asyncio
            asyncio.create_task(slack_client.start())
            logger.info("Slack client started with bidirectional communication and slash commands")
        except Exception as e:
            logger.warning("Slack client startup failed: %s", e)

    logger.info("Spectacles service ready")

    yield

    # Shutdown
    logger.info("Shutting down Spectacles service...")

    # Cleanup would go here
    logger.info("Spectacles service stopped")


# =============================================================================
# Application Factory
# =============================================================================

def create_app() -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title="Spectacles",
        description="Human-Sight Browser Automation Agent",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    # ==========================================================================
    # Middleware
    # ==========================================================================

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8080",
        ] if settings.is_development else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # GZip compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # API key authentication (opt-in — enabled via API_KEY_AUTH_ENABLED=true env var)
    # Runs outermost (last added = first executed) — blocks unauthenticated requests
    # before any other processing. Health endpoints are always exempted.
    class APIKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            if not settings.API_KEY_AUTH_ENABLED:
                return await call_next(request)
            if request.url.path in ("/health", "/api/health", "/"):
                return await call_next(request)
            api_key = request.headers.get("X-API-Key")
            if not api_key or api_key != settings.SPECTACLES_API_KEY:
                return JSONResponse(
                    {"detail": "Invalid or missing API key"},
                    status_code=403,
                )
            return await call_next(request)

    app.add_middleware(APIKeyMiddleware)

    # ==========================================================================
    # Exception Handlers
    # ==========================================================================

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle uncaught exceptions"""
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc) if settings.DEBUG else "An error occurred"
            }
        )

    # ==========================================================================
    # Routes
    # ==========================================================================

    # Health check routes (no prefix)
    app.include_router(health_router)

    # API routes
    app.include_router(tasks_router, prefix="/api")
    app.include_router(webhooks_router, prefix="/api")

    # Skills routes (for Glassy and other AI agents)
    # Available at /api/skills/...
    app.include_router(skills_router, prefix="/api")

    # Claude Code remote control routes
    # Available at /api/claude-code/...

    # ==========================================================================
    # Root endpoint
    # ==========================================================================

    @app.get("/")
    async def root():
        """Root endpoint"""
        return {
            "service": "spectacles",
            "version": "1.0.0",
            "description": "Human-Sight Browser Automation Agent",
            "docs": "/docs" if not settings.is_production else None,
            "health": "/health"
        }

    return app


# Create application instance
app = create_app()


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.is_development,
        log_level="debug" if settings.DEBUG else "info"
    )
