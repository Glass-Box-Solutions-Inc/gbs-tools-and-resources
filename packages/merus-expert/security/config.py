# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Security Configuration
SOC2-compliant settings and configuration management
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class SecurityConfig:
    """
    Security configuration for SOC2 compliance.

    Loads settings from environment variables with sensible defaults.
    """

    # Audit logging
    audit_retention_days: int = 90
    enable_audit_log: bool = True

    # Session management
    session_timeout_min: int = 30
    max_session_hours: int = 8

    # Screenshot management
    screenshot_retention_hr: int = 24
    encrypt_screenshots: bool = False

    # Credentials
    use_secret_manager: bool = False

    # Database
    db_path: str = "./knowledge/db/merus_knowledge.db"

    # Logging
    log_level: str = "INFO"
    log_file: str = "./logs/merus_agent.log"
    structured_logging: bool = True

    # MerusCase
    meruscase_email: Optional[str] = None
    meruscase_password: Optional[str] = None
    meruscase_base_url: str = "https://meruscase.com"
    meruscase_login_url: str = "https://meruscase.com/users/login"

    # Browserless
    browserless_api_token: Optional[str] = None
    browserless_endpoint: str = "wss://production-sfo.browserless.io"
    use_local_browser: bool = False
    use_headless: bool = True

    # MerusCase API (for hybrid approach)
    meruscase_api_token: Optional[str] = None
    meruscase_api_client_id: Optional[str] = None
    meruscase_api_client_secret: Optional[str] = None
    meruscase_api_base_url: str = "https://api.meruscase.com"
    use_hybrid_mode: bool = True  # Use API for post-creation operations

    # Agent settings
    max_retries: int = 3
    retry_delay_seconds: int = 5
    element_timeout_ms: int = 10000
    navigation_timeout_ms: int = 30000
    dry_run_default: bool = False

    # Specticles Integration (visual analysis, HITL approval, PII blur)
    specticles_enabled: bool = False
    specticles_api_url: str = "http://localhost:8080"
    specticles_api_key: Optional[str] = None
    specticles_timeout_seconds: int = 300
    specticles_require_approval: bool = True
    specticles_use_for_submit: bool = True  # HITL before form submission
    specticles_vlm_fallback: bool = True   # VLM when element not found

    # AI / NLP
    google_api_key: Optional[str] = None  # For Gemini entity extraction in chat

    @classmethod
    def from_env(cls) -> 'SecurityConfig':
        """
        Load configuration from environment variables.

        Returns:
            SecurityConfig instance with values from environment
        """
        return cls(
            # Audit logging
            audit_retention_days=int(os.getenv('MERUS_AUDIT_RETENTION_DAYS', '90')),
            enable_audit_log=os.getenv('MERUS_ENABLE_AUDIT_LOG', 'true').lower() == 'true',

            # Session management
            session_timeout_min=int(os.getenv('MERUS_SESSION_TIMEOUT_MIN', '30')),
            max_session_hours=int(os.getenv('MERUS_MAX_SESSION_HOURS', '8')),

            # Screenshot management
            screenshot_retention_hr=int(os.getenv('MERUS_SCREENSHOT_RETENTION_HR', '24')),
            encrypt_screenshots=os.getenv('MERUS_ENCRYPT_SCREENSHOTS', 'false').lower() == 'true',

            # Credentials
            use_secret_manager=os.getenv('USE_SECRET_MANAGER', 'false').lower() == 'true',

            # Database
            db_path=os.getenv('DB_PATH', './knowledge/db/merus_knowledge.db'),

            # Logging
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            log_file=os.getenv('LOG_FILE', './logs/merus_agent.log'),
            structured_logging=os.getenv('STRUCTURED_LOGGING', 'true').lower() == 'true',

            # MerusCase
            meruscase_email=os.getenv('MERUSCASE_EMAIL'),
            meruscase_password=os.getenv('MERUSCASE_PASSWORD'),
            meruscase_base_url=os.getenv('MERUSCASE_BASE_URL', 'https://meruscase.com'),
            meruscase_login_url=os.getenv('MERUSCASE_LOGIN_URL', 'https://meruscase.com/users/login'),

            # Browserless
            browserless_api_token=os.getenv('BROWSERLESS_API_TOKEN'),
            browserless_endpoint=os.getenv('BROWSERLESS_ENDPOINT', 'wss://production-sfo.browserless.io'),
            use_local_browser=os.getenv('USE_LOCAL_BROWSER', 'false').lower() == 'true',
            use_headless=os.getenv('USE_HEADLESS', 'true').lower() == 'true',

            # MerusCase API (for hybrid approach)
            meruscase_api_token=os.getenv('MERUSCASE_API_TOKEN'),
            meruscase_api_client_id=os.getenv('MERUSCASE_API_CLIENT_ID'),
            meruscase_api_client_secret=os.getenv('MERUSCASE_API_CLIENT_SECRET'),
            meruscase_api_base_url=os.getenv('MERUSCASE_API_BASE_URL', 'https://api.meruscase.com'),
            use_hybrid_mode=os.getenv('USE_HYBRID_MODE', 'true').lower() == 'true',

            # Agent settings
            max_retries=int(os.getenv('MAX_RETRIES', '3')),
            retry_delay_seconds=int(os.getenv('RETRY_DELAY_SECONDS', '5')),
            element_timeout_ms=int(os.getenv('ELEMENT_TIMEOUT_MS', '10000')),
            navigation_timeout_ms=int(os.getenv('NAVIGATION_TIMEOUT_MS', '30000')),
            dry_run_default=os.getenv('DRY_RUN_DEFAULT', 'false').lower() == 'true',

            # Specticles Integration
            specticles_enabled=os.getenv('SPECTICLES_ENABLED', 'false').lower() == 'true',
            specticles_api_url=os.getenv('SPECTICLES_API_URL', 'http://localhost:8080'),
            specticles_api_key=os.getenv('SPECTICLES_API_KEY'),
            specticles_timeout_seconds=int(os.getenv('SPECTICLES_TIMEOUT_SECONDS', '300')),
            specticles_require_approval=os.getenv('SPECTICLES_REQUIRE_APPROVAL', 'true').lower() == 'true',
            specticles_use_for_submit=os.getenv('SPECTICLES_USE_FOR_SUBMIT', 'true').lower() == 'true',
            specticles_vlm_fallback=os.getenv('SPECTICLES_VLM_FALLBACK', 'true').lower() == 'true',

            # AI / NLP
            google_api_key=os.getenv('GOOGLE_API_KEY'),
        )

    def validate(self) -> bool:
        """
        Validate required configuration values.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If required values are missing
        """
        errors = []

        if not self.meruscase_email:
            errors.append("MERUSCASE_EMAIL is required")

        if not self.meruscase_password:
            errors.append("MERUSCASE_PASSWORD is required")

        if not self.browserless_api_token:
            errors.append("BROWSERLESS_API_TOKEN is required")

        if errors:
            raise ValueError(f"Configuration validation failed: {', '.join(errors)}")

        return True
