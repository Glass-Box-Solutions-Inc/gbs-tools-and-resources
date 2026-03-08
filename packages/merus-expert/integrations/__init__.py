"""
Merus Expert Integrations

External service integrations for enhanced automation capabilities.
"""

from integrations.specticles_client import (
    SpecticlesClient,
    SpecticlesConfig,
    TaskResult,
    create_client_from_config
)

__all__ = [
    'SpecticlesClient',
    'SpecticlesConfig',
    'TaskResult',
    'create_client_from_config'
]
