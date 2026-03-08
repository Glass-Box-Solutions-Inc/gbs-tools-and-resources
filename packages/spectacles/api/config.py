"""
Spectacles Configuration
Pydantic Settings for environment-based configuration
"""

import os
from typing import Optional, List
from pydantic import Field, field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Load order:
    1. Environment variables
    2. .env file
    3. Default values
    """

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )

    # ==========================================================================
    # Core Application
    # ==========================================================================
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=False)
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8080)

    # ==========================================================================
    # GCP Configuration
    # ==========================================================================
    GCP_PROJECT_ID: Optional[str] = Field(default=None)

    # ==========================================================================
    # Browser Automation (Browserless.io)
    # ==========================================================================
    BROWSERLESS_API_TOKEN: Optional[str] = Field(default=None)
    BROWSERLESS_ENDPOINT: str = Field(
        default="wss://production-sfo.browserless.io"
    )
    USE_LOCAL_BROWSER: bool = Field(default=False)

    # ==========================================================================
    # Slack Integration (HITL)
    # ==========================================================================
    SLACK_BOT_TOKEN: Optional[str] = Field(default=None)
    SLACK_APP_TOKEN: Optional[str] = Field(default=None)  # For Socket Mode
    SLACK_APPROVAL_CHANNEL: str = Field(default="#spectacles-approvals")
    SLACK_SIGNING_SECRET: Optional[str] = Field(default=None)

    # ==========================================================================
    # Claude Code Remote Control
    # ==========================================================================
    CLAUDE_CODE_ENABLED: bool = Field(
        default=False,
        description="Enable Claude Code remote control features (Mode 2)"
    )
    CLAUDE_CODE_ADMIN_USERS: Optional[str] = Field(
        default=None,
        description="Comma-separated list of Slack user IDs authorized to control Claude Code"
    )
    CLAUDE_CODE_MAX_SESSIONS: int = Field(
        default=3,
        description="Maximum concurrent Claude Code sessions"
    )

    # ==========================================================================
    # AI / Vision & Reasoning (Gemini 2.5 Flash + 3.0)
    # ==========================================================================
    GOOGLE_AI_API_KEY: Optional[str] = Field(default=None)

    # Vision model - fast, cheap, excellent multimodal understanding
    VLM_MODEL: str = Field(default="gemini-2.5-flash")
    VLM_TIMEOUT_SECONDS: int = Field(default=30)

    # Reasoning model - strategic planning, complex decision-making
    REASONING_MODEL: str = Field(default="gemini-3.0")
    REASONING_TIMEOUT_SECONDS: int = Field(default=60)

    # ==========================================================================
    # Vector Database (Pinecone - Long-term Memory)
    # ==========================================================================
    PINECONE_API_KEY: Optional[str] = Field(default=None)
    PINECONE_INDEX: str = Field(default="spectacles-memory")
    PINECONE_ENVIRONMENT: str = Field(default="us-east-1")

    # ==========================================================================
    # Database
    # ==========================================================================
    DB_PATH: str = Field(default="./spectacles.db")
    DATABASE_URL: Optional[str] = Field(default=None)  # For PostgreSQL

    # ==========================================================================
    # Security
    # ==========================================================================
    ENCRYPTION_KEY: Optional[str] = Field(default=None)
    SECRET_KEY: str = Field(default="change-me-in-production")

    # ==========================================================================
    # API Key Authentication (opt-in via env var)
    # Set API_KEY_AUTH_ENABLED=true and SPECTACLES_API_KEY=<secret> in Cloud Run
    # to require X-API-Key header on all non-health endpoints.
    # ==========================================================================
    API_KEY_AUTH_ENABLED: bool = Field(default=False)
    SPECTACLES_API_KEY: Optional[str] = Field(default=None)

    # ==========================================================================
    # Session Management
    # ==========================================================================
    SESSION_TIMEOUT_MIN: int = Field(default=30)
    MAX_SESSION_HOURS: int = Field(default=8)

    # ==========================================================================
    # Screenshot Management
    # ==========================================================================
    SCREENSHOT_RETENTION_HR: int = Field(default=24)
    ENCRYPT_SCREENSHOTS: bool = Field(default=False)
    SCREENSHOT_DIR: str = Field(default="./screenshots")

    # ==========================================================================
    # Audit & Compliance
    # ==========================================================================
    AUDIT_RETENTION_DAYS: int = Field(default=90)

    # ==========================================================================
    # Browser Timeouts & Retries
    # ==========================================================================
    MAX_RETRIES: int = Field(default=3)
    RETRY_DELAY_SECONDS: int = Field(default=5)
    ELEMENT_TIMEOUT_MS: int = Field(default=10000)
    NAVIGATION_TIMEOUT_MS: int = Field(default=30000)

    # ==========================================================================
    # HITL Settings
    # ==========================================================================
    HITL_APPROVAL_TIMEOUT_SECONDS: int = Field(default=300)  # 5 minutes
    HITL_DEFAULT_REQUIRE_APPROVAL: bool = Field(default=True)

    # ==========================================================================
    # Rate Limiting
    # ==========================================================================
    RATE_LIMIT_REQUESTS: int = Field(default=60)
    RATE_LIMIT_PERIOD_SECONDS: int = Field(default=60)

    # ==========================================================================
    # Perception Settings (Phase 2)
    # ==========================================================================
    PERCEPTION_MODE: str = Field(default="hybrid")  # per_action, continuous, hybrid, on_demand
    PERCEPTION_INTERVAL_MS: int = Field(default=2000)  # For continuous mode
    VLM_BUDGET_PER_TASK: int = Field(default=10)  # Max VLM calls per task
    DOM_CONFIDENCE_THRESHOLD: float = Field(default=0.7)  # Below this, use VLM
    PERCEPTION_CACHE_TTL_MS: int = Field(default=1000)  # DOM cache validity
    DETECT_PAGE_CHANGES: bool = Field(default=True)

    # ==========================================================================
    # Desktop Automation Settings (Phase 3 - VM only)
    # ==========================================================================
    ENABLE_DESKTOP_AUTOMATION: bool = Field(default=False)  # Disabled by default
    PYAUTOGUI_FAILSAFE: bool = Field(default=True)  # Emergency stop at corners
    PYAUTOGUI_PAUSE: float = Field(default=0.1)  # Pause between actions
    OCR_LANGUAGE: str = Field(default="en")

    # ==========================================================================
    # File System Settings (Phase 5)
    # ==========================================================================
    ENABLE_FILE_OPERATIONS: bool = Field(default=False)  # Disabled by default
    ALLOWED_FILE_PATHS: str = Field(
        default="~/Documents,~/Downloads,/tmp/spectacles"
    )  # Comma-separated
    MAX_FILE_SIZE_MB: int = Field(default=100)
    ALLOW_FILE_DELETE: bool = Field(default=False)  # Extra protection

    # ==========================================================================
    # Validators
    # ==========================================================================

    @field_validator('SECRET_KEY')
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        if info.data.get('ENVIRONMENT') == 'production' and v == 'change-me-in-production':
            raise ValueError('SECRET_KEY must be changed in production')
        return v

    @field_validator('BROWSERLESS_API_TOKEN')
    @classmethod
    def validate_browserless_token(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        if not info.data.get('USE_LOCAL_BROWSER') and not v:
            # Only warn, don't error - might be set later
            pass
        return v

    # ==========================================================================
    # Computed Properties
    # ==========================================================================

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def has_slack(self) -> bool:
        return bool(self.SLACK_BOT_TOKEN and self.SLACK_APP_TOKEN)

    @property
    def has_vlm(self) -> bool:
        return bool(self.GOOGLE_AI_API_KEY)

    @property
    def has_pinecone(self) -> bool:
        return bool(self.PINECONE_API_KEY)

    @property
    def has_browserless(self) -> bool:
        return bool(self.BROWSERLESS_API_TOKEN)

    @property
    def allowed_file_paths_list(self) -> List[str]:
        """Parse ALLOWED_FILE_PATHS into list"""
        import os
        paths = [p.strip() for p in self.ALLOWED_FILE_PATHS.split(",")]
        # Expand ~ to home directory
        return [os.path.expanduser(p) for p in paths]

    @property
    def has_desktop_capabilities(self) -> bool:
        """Check if desktop automation is enabled and available"""
        if not self.ENABLE_DESKTOP_AUTOMATION:
            return False
        # Check for display
        import os
        has_display = bool(os.environ.get('DISPLAY')) or os.name == 'nt'
        return has_display

    def validate_required_for_production(self) -> List[str]:
        """
        Validate required settings for production.

        Returns:
            List of missing required settings
        """
        missing = []

        if not self.GCP_PROJECT_ID:
            missing.append("GCP_PROJECT_ID")
        if not self.has_browserless and not self.USE_LOCAL_BROWSER:
            missing.append("BROWSERLESS_API_TOKEN (or USE_LOCAL_BROWSER=true)")
        if not self.has_slack:
            missing.append("SLACK_BOT_TOKEN and SLACK_APP_TOKEN")
        if not self.has_vlm:
            missing.append("GOOGLE_AI_API_KEY")
        if not self.ENCRYPTION_KEY:
            missing.append("ENCRYPTION_KEY")

        return missing


# Singleton settings instance
settings = Settings()
