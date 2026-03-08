"""
Spectacles Filesystem Module
Sandboxed file operations with audit logging

SOC2/HIPAA Compliant with path restrictions and full audit trails.
"""

from .client import FileSystemClient

__all__ = ["FileSystemClient"]
