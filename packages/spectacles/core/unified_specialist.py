"""
Spectacles Unified Specialist
Routes tasks to Browser or Desktop Specialist based on context

Provides a unified interface for automation regardless of target
(web browser vs native desktop application).

SOC2/HIPAA Compliant: All actions are audit logged with PII filtering.
"""

import logging
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from persistence.constants import ActionType, ActionStatus, AutomationMode
from security.audit import AuditLogger, get_audit_logger
from core.capabilities import get_capabilities, RuntimeCapabilities

logger = logging.getLogger(__name__)


class TaskTarget(str, Enum):
    """Target environment for task execution"""
    BROWSER = "browser"
    DESKTOP = "desktop"
    AUTO = "auto"  # Auto-detect based on context


@dataclass
class UnifiedActionResult:
    """Result from unified specialist"""
    action_type: ActionType
    status: ActionStatus
    target_mode: AutomationMode
    specialist: str  # "browser" or "desktop"
    target: Optional[str] = None
    duration_ms: int = 0
    confidence: float = 1.0
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    audit_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "status": self.status.value,
            "target_mode": self.target_mode.value,
            "specialist": self.specialist,
            "target": self.target,
            "duration_ms": self.duration_ms,
            "confidence": self.confidence,
            "data": self.data,
            "error": self.error,
            "screenshot_path": self.screenshot_path,
            "audit_id": self.audit_id,
        }


class UnifiedSpecialist:
    """
    Unified Specialist - routes to Browser or Desktop Specialist.

    Responsibilities:
    - Detect appropriate automation mode for task
    - Route actions to correct specialist
    - Provide unified action interface
    - Maintain compliance (audit logging, PII filtering)
    - Handle cross-mode operations (e.g., download then open file)

    SOC2 Compliance:
    - All actions logged with timestamps
    - PII/PHI filtered from logs
    - Screenshot retention per policy
    - Full audit trail maintained
    """

    def __init__(
        self,
        browser_specialist=None,
        desktop_specialist=None,
        file_specialist=None,
        audit_logger: Optional[AuditLogger] = None,
        default_mode: TaskTarget = TaskTarget.AUTO
    ):
        """
        Initialize unified specialist.

        Args:
            browser_specialist: Browser specialist instance
            desktop_specialist: Desktop specialist instance (optional, VM only)
            file_specialist: File specialist instance (optional)
            audit_logger: Audit logger for compliance
            default_mode: Default task target when not specified
        """
        self.audit_logger = audit_logger or get_audit_logger()
        self.default_mode = default_mode

        # Specialists (lazy-loaded based on capabilities)
        self._browser_specialist = browser_specialist
        self._desktop_specialist = desktop_specialist
        self._file_specialist = file_specialist

        # Detect capabilities
        self._capabilities = get_capabilities()

        logger.info(
            "UnifiedSpecialist initialized (modes=%s, default=%s)",
            self._capabilities.available_modes,
            default_mode.value
        )

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Get runtime capabilities"""
        return self._capabilities

    @property
    def browser_specialist(self):
        """Get browser specialist (always available)"""
        if self._browser_specialist is None:
            raise RuntimeError("Browser specialist not initialized")
        return self._browser_specialist

    @property
    def desktop_specialist(self):
        """Get desktop specialist (VM only)"""
        if self._desktop_specialist is None:
            if "desktop" not in self._capabilities.available_modes:
                raise RuntimeError(
                    f"Desktop automation not available. "
                    f"Deployment: {self._capabilities.deployment.value}, "
                    f"Display: {self._capabilities.has_display}"
                )
            # Lazy init
            from core.desktop_specialist import DesktopSpecialist
            self._desktop_specialist = DesktopSpecialist(
                audit_logger=self.audit_logger
            )
        return self._desktop_specialist

    @property
    def file_specialist(self):
        """Get file specialist"""
        if self._file_specialist is None:
            if "files" not in self._capabilities.available_modes:
                raise RuntimeError("File operations not available")
            from core.file_specialist import FileSpecialist
            self._file_specialist = FileSpecialist(
                audit_logger=self.audit_logger
            )
        return self._file_specialist

    def can_use_mode(self, mode: AutomationMode) -> bool:
        """Check if a mode is available"""
        mode_map = {
            AutomationMode.BROWSER: "browser",
            AutomationMode.DESKTOP: "desktop",
            AutomationMode.FILE: "files",
            AutomationMode.HYBRID: True,  # Hybrid always possible if browser available
        }
        check = mode_map.get(mode)
        if check is True:
            return True
        return check in self._capabilities.available_modes

    def detect_target_mode(self, context: Dict[str, Any]) -> AutomationMode:
        """
        Detect appropriate automation mode from context.

        Args:
            context: Task context with hints about target

        Returns:
            Appropriate AutomationMode
        """
        # Check explicit hints
        if context.get("url") or context.get("browser"):
            return AutomationMode.BROWSER

        if context.get("app_name") or context.get("desktop") or context.get("native"):
            if "desktop" in self._capabilities.available_modes:
                return AutomationMode.DESKTOP
            else:
                logger.warning("Desktop requested but not available, falling back to browser")
                return AutomationMode.BROWSER

        if context.get("file_path") or context.get("file_operation"):
            if "files" in self._capabilities.available_modes:
                return AutomationMode.FILE
            else:
                logger.warning("File operations requested but not available")
                return AutomationMode.BROWSER

        # Check goal text for hints
        goal = context.get("goal", "").lower()

        desktop_keywords = [
            "excel", "word", "outlook", "powerpoint", "notepad",
            "terminal", "finder", "explorer", "desktop", "native",
            "application", "app", "software"
        ]

        browser_keywords = [
            "website", "webpage", "browser", "chrome", "firefox",
            "url", "http", "login", "form", "web"
        ]

        file_keywords = [
            "file", "folder", "directory", "read", "write",
            "create file", "save to", "download"
        ]

        for keyword in desktop_keywords:
            if keyword in goal:
                if "desktop" in self._capabilities.available_modes:
                    return AutomationMode.DESKTOP
                break

        for keyword in file_keywords:
            if keyword in goal:
                if "files" in self._capabilities.available_modes:
                    return AutomationMode.FILE
                break

        # Default to browser
        return AutomationMode.BROWSER

    async def navigate(
        self,
        target: str,
        mode: TaskTarget = TaskTarget.AUTO,
        task_id: Optional[str] = None,
        **kwargs
    ) -> UnifiedActionResult:
        """
        Navigate to URL or open application.

        Args:
            target: URL for browser, app name for desktop
            mode: Target mode
            task_id: Task ID for logging
            **kwargs: Additional arguments for specialist

        Returns:
            UnifiedActionResult
        """
        audit_id = self._log_action_start("navigate", target, mode, task_id)

        try:
            # Determine mode
            if mode == TaskTarget.AUTO:
                if target.startswith(("http://", "https://", "www.")):
                    resolved_mode = TaskTarget.BROWSER
                elif "desktop" in self._capabilities.available_modes:
                    resolved_mode = TaskTarget.DESKTOP
                else:
                    resolved_mode = TaskTarget.BROWSER
            else:
                resolved_mode = mode

            if resolved_mode == TaskTarget.BROWSER:
                result = await self.browser_specialist.navigate(
                    url=target,
                    task_id=task_id,
                    **kwargs
                )
                automation_mode = AutomationMode.BROWSER
            else:
                result = await self.desktop_specialist.open_application(
                    app_name=target,
                    task_id=task_id,
                    **kwargs
                )
                automation_mode = AutomationMode.DESKTOP

            self._log_action_complete(audit_id, result.status.value)

            return UnifiedActionResult(
                action_type=result.action_type,
                status=result.status,
                target_mode=automation_mode,
                specialist=resolved_mode.value,
                target=target,
                duration_ms=result.duration_ms,
                data=result.data,
                error=result.error,
                audit_id=audit_id
            )

        except Exception as e:
            self._log_action_complete(audit_id, "FAILED", str(e))
            return UnifiedActionResult(
                action_type=ActionType.NAVIGATE,
                status=ActionStatus.FAILED,
                target_mode=AutomationMode.BROWSER,
                specialist=mode.value,
                target=target,
                error=str(e),
                audit_id=audit_id
            )

    async def click(
        self,
        target: str,
        mode: TaskTarget = TaskTarget.AUTO,
        task_id: Optional[str] = None,
        **kwargs
    ) -> UnifiedActionResult:
        """
        Click on element by description or coordinates.

        Args:
            target: Element description or coordinates
            mode: Target mode
            task_id: Task ID for logging
            **kwargs: Additional arguments

        Returns:
            UnifiedActionResult
        """
        audit_id = self._log_action_start("click", target, mode, task_id)

        try:
            if mode == TaskTarget.AUTO:
                mode = self.default_mode

            if mode == TaskTarget.BROWSER:
                result = await self.browser_specialist.click(
                    target=target,
                    task_id=task_id,
                    **kwargs
                )
                automation_mode = AutomationMode.BROWSER
            else:
                result = await self.desktop_specialist.click_element(
                    description=target,
                    task_id=task_id,
                    **kwargs
                )
                automation_mode = AutomationMode.DESKTOP

            self._log_action_complete(audit_id, result.status.value)

            return UnifiedActionResult(
                action_type=result.action_type,
                status=result.status,
                target_mode=automation_mode,
                specialist=mode.value if mode != TaskTarget.AUTO else "auto",
                target=target,
                duration_ms=result.duration_ms,
                confidence=getattr(result, 'confidence', 1.0),
                data=result.data,
                error=result.error,
                screenshot_path=getattr(result, 'screenshot_path', None),
                audit_id=audit_id
            )

        except Exception as e:
            self._log_action_complete(audit_id, "FAILED", str(e))
            return UnifiedActionResult(
                action_type=ActionType.CLICK,
                status=ActionStatus.FAILED,
                target_mode=AutomationMode.BROWSER,
                specialist=mode.value if mode != TaskTarget.AUTO else "auto",
                target=target,
                error=str(e),
                audit_id=audit_id
            )

    async def type_text(
        self,
        text: str,
        target: Optional[str] = None,
        mode: TaskTarget = TaskTarget.AUTO,
        task_id: Optional[str] = None,
        **kwargs
    ) -> UnifiedActionResult:
        """
        Type text, optionally into specific element.

        Args:
            text: Text to type
            target: Optional element to type into
            mode: Target mode
            task_id: Task ID for logging
            **kwargs: Additional arguments

        Returns:
            UnifiedActionResult
        """
        # Mask text in audit log for compliance
        masked_text = text[:3] + "*" * (len(text) - 3) if len(text) > 3 else "***"
        audit_id = self._log_action_start("type", masked_text, mode, task_id)

        try:
            if mode == TaskTarget.AUTO:
                mode = self.default_mode

            if mode == TaskTarget.BROWSER:
                result = await self.browser_specialist.fill(
                    target=target or "input",
                    text=text,
                    task_id=task_id,
                    **kwargs
                )
                automation_mode = AutomationMode.BROWSER
            else:
                result = await self.desktop_specialist.type_text(
                    text=text,
                    target=target,
                    task_id=task_id,
                    **kwargs
                )
                automation_mode = AutomationMode.DESKTOP

            self._log_action_complete(audit_id, result.status.value)

            return UnifiedActionResult(
                action_type=result.action_type,
                status=result.status,
                target_mode=automation_mode,
                specialist=mode.value if mode != TaskTarget.AUTO else "auto",
                target=target,
                duration_ms=result.duration_ms,
                data={"text_length": len(text)},  # Don't include actual text
                error=result.error,
                audit_id=audit_id
            )

        except Exception as e:
            self._log_action_complete(audit_id, "FAILED", str(e))
            return UnifiedActionResult(
                action_type=ActionType.FILL,
                status=ActionStatus.FAILED,
                target_mode=AutomationMode.BROWSER,
                specialist=mode.value if mode != TaskTarget.AUTO else "auto",
                target=target,
                error=str(e),
                audit_id=audit_id
            )

    async def screenshot(
        self,
        mode: TaskTarget = TaskTarget.AUTO,
        region: Optional[tuple] = None,
        task_id: Optional[str] = None,
        **kwargs
    ) -> UnifiedActionResult:
        """
        Take screenshot.

        Args:
            mode: Target mode
            region: Optional region (for desktop)
            task_id: Task ID for logging
            **kwargs: Additional arguments

        Returns:
            UnifiedActionResult with screenshot path
        """
        audit_id = self._log_action_start("screenshot", "screen", mode, task_id)

        try:
            if mode == TaskTarget.AUTO:
                mode = self.default_mode

            if mode == TaskTarget.BROWSER:
                result = await self.browser_specialist.screenshot(
                    task_id=task_id,
                    **kwargs
                )
                automation_mode = AutomationMode.BROWSER
            else:
                result = await self.desktop_specialist.screenshot(
                    region=region,
                    task_id=task_id,
                    **kwargs
                )
                automation_mode = AutomationMode.DESKTOP

            self._log_action_complete(audit_id, result.status.value)

            return UnifiedActionResult(
                action_type=ActionType.SCREENSHOT,
                status=result.status,
                target_mode=automation_mode,
                specialist=mode.value if mode != TaskTarget.AUTO else "auto",
                duration_ms=result.duration_ms,
                data=result.data,
                error=result.error,
                screenshot_path=result.screenshot_path,
                audit_id=audit_id
            )

        except Exception as e:
            self._log_action_complete(audit_id, "FAILED", str(e))
            return UnifiedActionResult(
                action_type=ActionType.SCREENSHOT,
                status=ActionStatus.FAILED,
                target_mode=AutomationMode.BROWSER,
                specialist=mode.value if mode != TaskTarget.AUTO else "auto",
                error=str(e),
                audit_id=audit_id
            )

    async def press_key(
        self,
        key: str,
        modifiers: Optional[List[str]] = None,
        mode: TaskTarget = TaskTarget.AUTO,
        task_id: Optional[str] = None
    ) -> UnifiedActionResult:
        """
        Press key or key combination.

        Args:
            key: Key to press
            modifiers: Optional modifier keys
            mode: Target mode
            task_id: Task ID for logging

        Returns:
            UnifiedActionResult
        """
        key_desc = "+".join(modifiers + [key]) if modifiers else key
        audit_id = self._log_action_start("key", key_desc, mode, task_id)

        try:
            if mode == TaskTarget.AUTO:
                mode = self.default_mode

            if mode == TaskTarget.BROWSER:
                result = await self.browser_specialist.keyboard(
                    key=key,
                    modifiers=modifiers,
                    task_id=task_id
                )
                automation_mode = AutomationMode.BROWSER
            else:
                result = await self.desktop_specialist.press_key(
                    key=key,
                    modifiers=modifiers,
                    task_id=task_id
                )
                automation_mode = AutomationMode.DESKTOP

            self._log_action_complete(audit_id, result.status.value)

            return UnifiedActionResult(
                action_type=result.action_type,
                status=result.status,
                target_mode=automation_mode,
                specialist=mode.value if mode != TaskTarget.AUTO else "auto",
                target=key_desc,
                duration_ms=result.duration_ms,
                data=result.data,
                error=result.error,
                audit_id=audit_id
            )

        except Exception as e:
            self._log_action_complete(audit_id, "FAILED", str(e))
            return UnifiedActionResult(
                action_type=ActionType.KEYBOARD,
                status=ActionStatus.FAILED,
                target_mode=AutomationMode.BROWSER,
                specialist=mode.value if mode != TaskTarget.AUTO else "auto",
                target=key_desc,
                error=str(e),
                audit_id=audit_id
            )

    async def perceive(
        self,
        goal: str,
        mode: TaskTarget = TaskTarget.AUTO,
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Perceive current state (browser page or desktop screen).

        Args:
            goal: What we're trying to understand
            mode: Target mode
            task_id: Task ID for logging
            context: Additional context

        Returns:
            Perception results
        """
        if mode == TaskTarget.AUTO:
            mode = self.default_mode

        if mode == TaskTarget.BROWSER:
            # Use perception router for browser
            perception = await self.browser_specialist.perception_router.perceive(
                goal=goal,
                context=context
            )
            return perception.to_dict()
        else:
            # Use desktop perceiver
            return await self.desktop_specialist.perceive_screen(
                goal=goal,
                task_id=task_id
            )

    async def execute_action(
        self,
        action_type: str,
        params: Dict[str, Any],
        mode: TaskTarget = TaskTarget.AUTO,
        task_id: Optional[str] = None
    ) -> UnifiedActionResult:
        """
        Execute arbitrary action by type.

        Args:
            action_type: Type of action (click, type, navigate, etc.)
            params: Action parameters
            mode: Target mode
            task_id: Task ID for logging

        Returns:
            UnifiedActionResult
        """
        action_map = {
            "navigate": self.navigate,
            "click": self.click,
            "type": self.type_text,
            "screenshot": self.screenshot,
            "key": self.press_key,
            "perceive": self.perceive,
        }

        handler = action_map.get(action_type.lower())
        if not handler:
            return UnifiedActionResult(
                action_type=ActionType.NAVIGATE,
                status=ActionStatus.FAILED,
                target_mode=AutomationMode.BROWSER,
                specialist="unknown",
                error=f"Unknown action type: {action_type}"
            )

        return await handler(mode=mode, task_id=task_id, **params)

    def get_available_modes(self) -> List[str]:
        """Get list of available automation modes"""
        return self._capabilities.available_modes.copy()

    def _log_action_start(
        self,
        action: str,
        target: str,
        mode: TaskTarget,
        task_id: Optional[str]
    ) -> str:
        """Log action start and return audit ID"""
        import uuid
        audit_id = str(uuid.uuid4())[:8]

        self.audit_logger.log_browser_action(
            action=f"unified_{action}_start",
            status="IN_PROGRESS",
            task_id=task_id,
            resource=f"{mode.value}:{target}",
            additional_data={"audit_id": audit_id}
        )

        return audit_id

    def _log_action_complete(
        self,
        audit_id: str,
        status: str,
        error: Optional[str] = None
    ):
        """Log action completion"""
        self.audit_logger.log_browser_action(
            action=f"unified_action_complete",
            status=status,
            task_id=audit_id,
            resource=error or "success"
        )

    def close(self):
        """Close all specialists"""
        if self._desktop_specialist:
            self._desktop_specialist.close()
        if self._file_specialist:
            self._file_specialist.close()
        logger.info("UnifiedSpecialist closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
