"""
Spectacles Security Module
Secrets management, PII filtering, and audit logging
"""

from .secrets_vault import SecretsVault, get_secrets_vault
from .pii_filter import PIIFilter
from .audit import AuditLogger, get_audit_logger

__all__ = [
    "SecretsVault",
    "get_secrets_vault",
    "PIIFilter",
    "AuditLogger",
    "get_audit_logger",
]
