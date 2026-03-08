"""
Spectacles API Routes
"""

from .tasks import router as tasks_router
from .webhooks import router as webhooks_router
from .health import router as health_router
from .skills import router as skills_router

__all__ = [
    "tasks_router",
    "webhooks_router",
    "health_router",
    "skills_router",
]
